"""
Zoner - Region of Interest (ROI) Selector
=========================================
A premium, highly interactive utility to select and edit polygonal Regions of Interest (ROIs) 
from images, video frames, or video files. 
"""

import cv2
import numpy as np
import json
import os
import sys
import platform

# Check if the OS is Windows to enable custom OS grab cursors
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import ctypes
    # Standard Windows Cursor IDs
    IDC_ARROW = 32512
    IDC_HAND = 32649  # Pointing hand cursor
    IDC_SIZEALL = 32646  # Grab/move cursor (4-directional arrow)
    try:
        h_arrow = ctypes.windll.user32.LoadCursorW(0, IDC_ARROW)
        h_hand = ctypes.windll.user32.LoadCursorW(0, IDC_HAND)
        h_grab = ctypes.windll.user32.LoadCursorW(0, IDC_SIZEALL)
    except Exception:
        IS_WINDOWS = False

class ZoneSelector:
    def __init__(self, source, window_name="Zoner - Select Region", max_width=1280, max_height=720):
        """
        Initialize the interactive Zone Selector.
        
        Args:
            source: Path to an image/video file, or a NumPy frame array.
            window_name (str): Title of the OpenCV window.
            max_width (int): Maximum width of the display window.
            max_height (int): Maximum height of the display window.
        """
        self.window_name = window_name
        self.source_path = source if isinstance(source, str) else "frame"
        
        # Load frame
        self.frame = self._load_frame(source)
        if self.frame is None:
            raise ValueError("Could not load frame from source.")
            
        self.orig_h, self.orig_w = self.frame.shape[:2]
        
        # Determine scale factor to fit display limits
        self.scale = min(max_width / self.orig_w, max_height / self.orig_h, 1.0)
        self.display_w = int(self.orig_w * self.scale)
        self.display_h = int(self.orig_h * self.scale)
        
        # Multiple zones storage: list of dicts {'name': str, 'points': [(x, y), ...]}
        self.zones = []
        self.current_points = []  # Active polygon being drawn
        
        # Zoom parameters
        self.zoom_factor = 1.0
        self.zoom_center = (self.orig_w / 2.0, self.orig_h / 2.0)  # In original coordinates
        
        # Interactivity states
        self.dragging = False
        self.selected_zone_idx = -1  # -2: current_points, >=0: saved zone, -1: none
        self.selected_point_idx = -1
        self.mouse_pos = (0, 0)      # Mouse position in original coordinates
        
        self.snap_dist = 12          # Snap radius in display pixels
        self.line_click_thresh = 8.0  # Click threshold to insert point on a line (display pixels)
        self.history = []            # Undo history for current drawing
        
        # Load existing JSON config if it exists
        self.json_filename = self._get_json_filename()
        self._load_from_json(silent=True)

    def _load_frame(self, source):
        if isinstance(source, np.ndarray):
            return source.copy()
        elif isinstance(source, str):
            if not os.path.exists(source):
                return None
            img = cv2.imread(source)
            if img is not None:
                return img
            cap = cv2.VideoCapture(source)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret:
                    return frame
        return None

    def _get_json_filename(self):
        if isinstance(self.source_path, str) and self.source_path != "frame":
            base, _ = os.path.splitext(self.source_path)
            return f"{base}_zones.json"
        return "zones.json"

    def _save_to_json(self):
        data = {
            "source": self.source_path,
            "dimensions": {"width": self.orig_w, "height": self.orig_h},
            "zones": [
                {"name": z["name"], "points": [list(pt) for pt in z["points"]]}
                for z in self.zones
            ]
        }
        try:
            with open(self.json_filename, "w") as f:
                json.dump(data, f, indent=4)
            print(f"[INFO] Exported {len(self.zones)} zones to {self.json_filename}")
        except Exception as e:
            print(f"[ERROR] Failed to save JSON: {e}")

    def _load_from_json(self, silent=False):
        if not os.path.exists(self.json_filename):
            if not silent:
                print(f"[INFO] No existing zone file '{self.json_filename}' found.")
            return
        try:
            with open(self.json_filename, "r") as f:
                data = json.load(f)
            self.zones = []
            for z in data.get("zones", []):
                self.zones.append({
                    "name": z["name"],
                    "points": [tuple(pt) for pt in z["points"]]
                })
            if not silent:
                print(f"[INFO] Imported {len(self.zones)} zones from {self.json_filename}")
        except Exception as e:
            print(f"[ERROR] Failed to load JSON: {e}")

    def _finish_current_zone(self):
        if len(self.current_points) < 3:
            print("[WARN] Need at least 3 points to close a polygon.")
            return
            
        zone_name = f"Zone_{len(self.zones) + 1}"
        self.zones.append({
            "name": zone_name,
            "points": list(self.current_points)
        })
        print(f"[EVENT] Saved '{zone_name}' with {len(self.current_points)} corners.")
        self.current_points = []
        self.history = []

    def _get_segment_dist(self, a, b, click_pt):
        """
        Calculates the distance from a click point to a line segment a-b in display coordinates.
        Returns (distance, projection_factor_t)
        """
        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)
        c_arr = np.array(click_pt, dtype=np.float32)
        
        ab = b_arr - a_arr
        ac = c_arr - a_arr
        
        ab_len_sq = np.sum(ab**2)
        if ab_len_sq == 0:
            return np.linalg.norm(c_arr - a_arr), 0.0
            
        t = np.dot(ac, ab) / ab_len_sq
        t = max(0.0, min(1.0, t))
        
        closest = a_arr + t * ab
        dist = np.linalg.norm(c_arr - closest)
        return dist, t

    def draw(self):
        cv2.namedWindow(self.window_name)
        
        def mouse_handler(event, x, y, flags, param):
            # Compute current crop boundaries on original image to map coordinates correctly
            w_crop_orig = self.orig_w / self.zoom_factor
            h_crop_orig = self.orig_h / self.zoom_factor
            x_min_orig = max(0.0, min(self.zoom_center[0] - w_crop_orig / 2.0, self.orig_w - w_crop_orig))
            y_min_orig = max(0.0, min(self.zoom_center[1] - h_crop_orig / 2.0, self.orig_h - h_crop_orig))
            
            # Map window (x, y) to original coordinates
            x_orig = int(x_min_orig + x / (self.scale * self.zoom_factor))
            y_orig = int(y_min_orig + y / (self.scale * self.zoom_factor))
            x_bounded = max(0, min(x_orig, self.orig_w - 1))
            y_bounded = max(0, min(y_orig, self.orig_h - 1))

            # Helper to check distance from original coordinates to window cursor (x, y)
            def get_dist(p1):
                x_win = (p1[0] - x_min_orig) * self.scale * self.zoom_factor
                y_win = (p1[1] - y_min_orig) * self.scale * self.zoom_factor
                return np.hypot(x_win - x, y_win - y)

            if event == cv2.EVENT_LBUTTONDOWN:
                # 1. Snap-close if clicking on the first point of the current zone
                if len(self.current_points) >= 3 and get_dist(self.current_points[0]) < self.snap_dist:
                    self._finish_current_zone()
                    return

                # 2. Check if clicking on active drawing points to drag
                for idx, pt in enumerate(self.current_points):
                    if get_dist(pt) < self.snap_dist:
                        self.selected_zone_idx = -2
                        self.selected_point_idx = idx
                        self.dragging = True
                        return
                
                # 3. Check if clicking on saved zones points to drag
                for z_idx, zone in enumerate(self.zones):
                    for p_idx, pt in enumerate(zone["points"]):
                        if get_dist(pt) < self.snap_dist:
                            self.selected_zone_idx = z_idx
                            self.selected_point_idx = p_idx
                            self.dragging = True
                            return
                
                # 4. Check if clicking on a line segment to insert a point
                # Check active drawing segments
                if len(self.current_points) >= 2:
                    # Check lines between sequential points
                    for i in range(len(self.current_points) - 1):
                        p1_disp = ((self.current_points[i][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (self.current_points[i][1] - y_min_orig) * self.scale * self.zoom_factor)
                        p2_disp = ((self.current_points[i+1][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (self.current_points[i+1][1] - y_min_orig) * self.scale * self.zoom_factor)
                        dist, t = self._get_segment_dist(p1_disp, p2_disp, (x, y))
                        if dist < self.line_click_thresh and 0.05 < t < 0.95:
                            self.history.append(list(self.current_points))
                            self.current_points.insert(i + 1, (x_bounded, y_bounded))
                            print(f"[EVENT] Inserted point at segment index {i+1} on active drawing.")
                            return
                    # Check loop preview line (last to first) if drawing is closed preview
                    if len(self.current_points) >= 3:
                        p1_disp = ((self.current_points[-1][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (self.current_points[-1][1] - y_min_orig) * self.scale * self.zoom_factor)
                        p2_disp = ((self.current_points[0][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (self.current_points[0][1] - y_min_orig) * self.scale * self.zoom_factor)
                        dist, t = self._get_segment_dist(p1_disp, p2_disp, (x, y))
                        if dist < self.line_click_thresh and 0.05 < t < 0.95:
                            self.history.append(list(self.current_points))
                            self.current_points.append((x_bounded, y_bounded))
                            print(f"[EVENT] Inserted point at segment loop-end on active drawing.")
                            return

                # Check saved zones segments
                for z_idx, zone in enumerate(self.zones):
                    for i in range(len(zone["points"])):
                        j = (i + 1) % len(zone["points"])
                        p1_disp = ((zone["points"][i][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (zone["points"][i][1] - y_min_orig) * self.scale * self.zoom_factor)
                        p2_disp = ((zone["points"][j][0] - x_min_orig) * self.scale * self.zoom_factor, 
                                   (zone["points"][j][1] - y_min_orig) * self.scale * self.zoom_factor)
                        dist, t = self._get_segment_dist(p1_disp, p2_disp, (x, y))
                        if dist < self.line_click_thresh and 0.05 < t < 0.95:
                            zone["points"].insert(i + 1, (x_bounded, y_bounded))
                            print(f"[EVENT] Inserted point at segment index {i+1} on zone '{zone['name']}'.")
                            return

                # 5. Otherwise, add a new point to the end of active drawing
                self.history.append(list(self.current_points))
                self.current_points.append((x_bounded, y_bounded))
                
            elif event == cv2.EVENT_MOUSEMOVE:
                self.mouse_pos = (x_bounded, y_bounded)
                
                # Dynamic Windows Cursor Control (Arrow/Hand/Grab)
                if IS_WINDOWS:
                    hovering_point = False
                    for pt in self.current_points:
                        if get_dist(pt) < self.snap_dist:
                            hovering_point = True
                            break
                    if not hovering_point:
                        for zone in self.zones:
                            for pt in zone["points"]:
                                if get_dist(pt) < self.snap_dist:
                                    hovering_point = True
                                    break
                    
                    if self.dragging:
                        ctypes.windll.user32.SetCursor(h_grab)
                    elif hovering_point:
                        ctypes.windll.user32.SetCursor(h_hand)
                    else:
                        ctypes.windll.user32.SetCursor(h_arrow)

                if self.dragging:
                    if self.selected_zone_idx == -2:
                        self.current_points[self.selected_point_idx] = (x_bounded, y_bounded)
                    elif self.selected_zone_idx >= 0:
                        self.zones[self.selected_zone_idx]["points"][self.selected_point_idx] = (x_bounded, y_bounded)

            elif event == cv2.EVENT_LBUTTONUP:
                self.dragging = False
                self.selected_zone_idx = -1
                self.selected_point_idx = -1

            elif event == cv2.EVENT_RBUTTONDOWN:
                # Right-click deletes hovered points
                for idx, pt in enumerate(self.current_points):
                    if get_dist(pt) < self.snap_dist:
                        self.history.append(list(self.current_points))
                        self.current_points.pop(idx)
                        return
                        
                for z_idx, zone in enumerate(self.zones):
                    for p_idx, pt in enumerate(zone["points"]):
                        if get_dist(pt) < self.snap_dist:
                            zone["points"].pop(p_idx)
                            if len(zone["points"]) < 3:
                                self.zones.pop(z_idx)
                            return
                            
            elif event == cv2.EVENT_MOUSEWHEEL:
                mx_orig = x_min_orig + x / (self.scale * self.zoom_factor)
                my_orig = y_min_orig + y / (self.scale * self.zoom_factor)
                
                if flags > 0:
                    self.zoom_factor = min(self.zoom_factor + 0.2, 8.0)
                else:
                    self.zoom_factor = max(self.zoom_factor - 0.2, 1.0)
                    
                if self.zoom_factor > 1.0:
                    self.zoom_center = (mx_orig, my_orig)
                else:
                    self.zoom_center = (self.orig_w / 2.0, self.orig_h / 2.0)

        cv2.setMouseCallback(self.window_name, mouse_handler)

        while True:
            # 1. Compute crop boundaries based on zoom factor and zoom center
            w_crop_orig = self.orig_w / self.zoom_factor
            h_crop_orig = self.orig_h / self.zoom_factor
            x_min_orig = max(0.0, min(self.zoom_center[0] - w_crop_orig / 2.0, self.orig_w - w_crop_orig))
            y_min_orig = max(0.0, min(self.zoom_center[1] - h_crop_orig / 2.0, self.orig_h - h_crop_orig))
            x_max_orig = x_min_orig + w_crop_orig
            y_max_orig = y_min_orig + h_crop_orig
            
            # Crop original frame and resize to display window size
            cropped_orig = self.frame[int(y_min_orig):int(y_max_orig), int(x_min_orig):int(x_max_orig)]
            display_frame = cv2.resize(cropped_orig, (self.display_w, self.display_h))
            
            # Helper to convert original coordinate to window display pixel coordinate
            def to_win(pt):
                x_win = int((pt[0] - x_min_orig) * self.scale * self.zoom_factor)
                y_win = int((pt[1] - y_min_orig) * self.scale * self.zoom_factor)
                return (x_win, y_win)

            # Check distance in window space for mouse hovering
            def is_hovered(pt):
                pt_win = to_win(pt)
                mx_win, my_win = to_win(self.mouse_pos)
                return np.hypot(pt_win[0] - mx_win, pt_win[1] - my_win) < self.snap_dist

            # Draw Saved Zones
            for z_idx, zone in enumerate(self.zones):
                pts_disp = np.array([to_win(pt) for pt in zone["points"]], dtype=np.int32)
                
                overlay = display_frame.copy()
                cv2.fillPoly(overlay, [pts_disp], color=(0, 255, 0))
                cv2.addWeighted(overlay, 0.2, display_frame, 0.8, 0, display_frame)
                
                cv2.polylines(display_frame, [pts_disp], isClosed=True, color=(0, 200, 0), thickness=2)
                
                for pt_orig in zone["points"]:
                    pt_disp = to_win(pt_orig)
                    if is_hovered(pt_orig):
                        # Highlight grab-able point on hover: larger and distinct color (orange)
                        cv2.circle(display_frame, pt_disp, 7, (0, 165, 255), -1)
                        cv2.circle(display_frame, pt_disp, 8, (255, 255, 255), 1)
                    else:
                        cv2.circle(display_frame, pt_disp, 4, (0, 255, 0), -1)
                
                centroid = np.mean(pts_disp, axis=0).astype(int)
                cv2.putText(display_frame, zone["name"], (centroid[0] - 30, centroid[1]), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            # Draw Active/Current Polygon
            if len(self.current_points) > 0:
                pts_disp = np.array([to_win(pt) for pt in self.current_points], dtype=np.int32)
                
                cv2.polylines(display_frame, [pts_disp], isClosed=False, color=(0, 215, 255), thickness=2)
                
                if len(self.current_points) >= 3:
                    cv2.line(display_frame, tuple(pts_disp[-1]), tuple(pts_disp[0]), (0, 255, 255), 1, cv2.LINE_AA)
                    
                for idx, pt_orig in enumerate(self.current_points):
                    pt_disp = to_win(pt_orig)
                    if is_hovered(pt_orig):
                        # Highlight active point on hover
                        cv2.circle(display_frame, pt_disp, 8, (0, 165, 255), -1)
                        cv2.circle(display_frame, pt_disp, 9, (255, 255, 255), 1)
                    else:
                        cv2.circle(display_frame, pt_disp, 5, (0, 215, 255), -1)
                    cv2.putText(display_frame, str(idx + 1), (pt_disp[0] + 8, pt_disp[1] - 8), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 215, 255), 1)

            # Draw cursor coordinate display next to mouse pointer
            mx_win, my_win = to_win(self.mouse_pos)
            if 0 <= mx_win < self.display_w and 0 <= my_win < self.display_h:
                cv2.putText(display_frame, f"X:{self.mouse_pos[0]} Y:{self.mouse_pos[1]}", 
                            (mx_win + 15, my_win + 15), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

            # HUD Overlay Panel
            hud_height = 85
            overlay = display_frame.copy()
            cv2.rectangle(overlay, (0, self.display_h - hud_height), (self.display_w, self.display_h), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, display_frame, 0.3, 0, display_frame)
            
            cv2.putText(display_frame, "Controls: L-Click: Add/Drag (Click Line to Insert) | R-Click: Delete Point | Z: Undo", 
                        (10, self.display_h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(display_frame, "          ENTER: Save Zone / Exit | S: Export JSON | L: Load JSON | Scroll: Zoom", 
                        (10, self.display_h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
            
            status_text = f"Zones: {len(self.zones)} | Active Points: {len(self.current_points)} | Zoom: {self.zoom_factor:.1f}x"
            cv2.putText(display_frame, status_text, (10, self.display_h - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

            cv2.imshow(self.window_name, display_frame)
            
            if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                break
                
            key = cv2.waitKey(1) & 0xFF
            
            if key == 13:  # ENTER
                if len(self.current_points) > 0:
                    self._finish_current_zone()
                else:
                    break
            elif key == ord('z') or key == 26:  # Z or Ctrl+Z
                if self.history:
                    self.current_points = self.history.pop()
                elif self.current_points:
                    self.current_points.pop()
            elif key == ord('r'):  # Reset
                self.zones = []
                self.current_points = []
                self.history = []
                self.zoom_factor = 1.0
                self.zoom_center = (self.orig_w / 2.0, self.orig_h / 2.0)
            elif key == ord('s'):  # Save
                self._save_to_json()
            elif key == ord('l'):  # Load
                self._load_from_json()
            elif key == ord('q'):  # Quit
                break

        cv2.destroyAllWindows()
        for _ in range(5):
            cv2.waitKey(1)
            
        return self.zones

def select_zone(video_path: str, num_corners: int = None, window_name: str = "Select Zone") -> np.ndarray:
    """
    Backwards compatibility function. Launches the interactive ZoneSelector
    and returns the first defined zone points array.
    """
    selector = ZoneSelector(video_path, window_name=window_name)
    zones = selector.draw()
    if zones:
        return np.array(zones[0]["points"], dtype=np.int32)
    return None

# ZONER 🎯

A premium, highly interactive Python utility to select, edit, and manage polygonal Regions of Interest (ROIs) from images, video frames, or video files.

## Features

- **Left-Click:** Add points
- **Left-Click & Drag:** Grab and move existing points
- **Left-Click on Line:** Insert a new point dynamically between two points
- **Right-Click:** Delete points
- **ENTER:** Save current zone / Exit when drawing is empty
- **Z / Ctrl+Z:** Undo last point
- **R:** Reset all points and zones
- **Scroll Mouse Wheel:** Zoom in and out centering on the cursor
- **Export/Import JSON:** Export with **S**, Import with **L** (saves as `{source}_zones.json` automatically)
- **Auto-Scale:** Auto-scales large frames to fit display size while keeping original resolution coordinates

---

## Installation

Install in editable mode from the project folder:
```bash
pip install -e .
```

---

## How to Use (Different Ways)

`Zoner` is designed to be highly versatile. You can initialize it using video files, image files, or raw NumPy frame arrays.

### 1. Direct Video File Path (Default: Loads First Frame)
Ideal for quick setups when you just want to draw zones on the first frame of a video.
```python
from zoner import ZoneSelector

# Load video directly (automatically reads frame 0)
selector = ZoneSelector("PETS2009.avi")
zones = selector.draw()

# Get results
for zone in zones:
    print(f"Zone: {zone['name']}, Coordinates: {zone['points']}")
```

### 2. Specific Video Frame (By Frame Index)
Perfect if the first frame of your video is black or lacks context, and you want to choose a specific frame index (e.g., frame 150) to draw your zones.
```python
import cv2
from zoner import ZoneSelector

# 1. Capture the exact frame
cap = cv2.VideoCapture("PETS2009.avi")
cap.set(cv2.CAP_PROP_POS_FRAMES, 150)  # Jump to frame 150
ret, frame = cap.read()
cap.release()

if ret:
    # 2. Pass the NumPy frame array to ZoneSelector
    selector = ZoneSelector(frame, window_name="Select Zones on Frame 150")
    
    # 3. Specify custom JSON filename to link it with the video name
    selector.json_filename = "PETS2009_zones.json"
    
    zones = selector.draw()
```

### 3. Specific Time Position in Video (By Seconds)
Useful when you want to jump to a specific time slot (e.g., 5.5 seconds) in the video.
```python
import cv2
from zoner import ZoneSelector

cap = cv2.VideoCapture("PETS2009.avi")
fps = cap.get(cv2.CAP_PROP_FPS)

# Calculate frame number for 5.5 seconds
frame_num = int(5.5 * fps)

cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ret, frame = cap.read()
cap.release()

if ret:
    selector = ZoneSelector(frame, window_name="Select Zones at 5.5 Seconds")
    selector.json_filename = "PETS2009_zones.json"
    zones = selector.draw()
```

### 4. Direct Image File Path
Useful for static image analysis.
```python
from zoner import ZoneSelector

# Load an image path
selector = ZoneSelector("workstation_layout.jpg")
zones = selector.draw()
```

### 5. Running from Command Line
You can test the module instantly from the command line:
```bash
python -m zoner.selector
```
*(This starts a test session on the default `PETS2009.avi` video).*

---

## Why `pyzoner`? (Comparison)

| Feature | `roipoly` | `cv2.selectROI` | `labelme` | **`pyzoner`** |
|---|:---:|:---:|:---:|:---:|
| Polygon drawing | ✅ | ❌ | ✅ | ✅ |
| Drag to edit points | ❌ | ❌ | ✅ | ✅ |
| Insert point on line click | ❌ | ❌ | ❌ | ✅ |
| Scroll-wheel zoom | ❌ | ❌ | ✅ | ✅ |
| Undo (Ctrl+Z) | ❌ | ❌ | ✅ | ✅ |
| Grab cursor on hover | ❌ | ❌ | ❌ | ✅ |
| Hover highlight feedback | ❌ | ❌ | ❌ | ✅ |
| JSON save / load | ❌ | ❌ | ✅ | ✅ |
| Video frame support | ❌ | ❌ | ❌ | ✅ |
| Multiple named zones | ❌ | ❌ | ✅ | ✅ |
| Returns NumPy arrays | ✅ | ✅ | ❌ | ✅ |
| Lightweight (3 lines of code) | ✅ | ✅ | ❌ | ✅ |
| **Install size** | ~50 KB | built-in | ~50 MB+ | **~15 KB** |

> **`pyzoner`** fills the sweet spot between *"too simple"* (`selectROI`) and *"too heavy"* (`labelme`).  
> It's the lightest full-featured interactive zone selector for computer vision pipelines.

# ZONER 🎯

A premium, highly interactive Python utility to select, edit, and manage polygonal Regions of Interest (ROIs) from images, video frames, or video files.

## Features

- **Left-Click:** Add points / Left-click and Drag points to edit positions
- **Right-Click:** Delete points
- **ENTER:** Save current zone / Exit when drawing is empty
- **Z / Ctrl+Z:** Undo last point
- **R:** Reset all points and zones
- **Export/Import JSON:** Export with **S**, Import with **L** (saves as `{source}_zones.json` automatically)
- **Auto-Scale:** Auto-scales large frames to fit display size while keeping original resolution coordinates

## Installation

Install in editable mode from the project folder:
```bash
pip install -e .
```

## Quick Start

```python
from zoner import ZoneSelector

# Initialize with video or image path
selector = ZoneSelector("PETS2009.avi")

# Run drawing loop
zones = selector.draw()

# Get results (saved automatically to PETS2009_zones.json)
for zone in zones:
    print(f"Zone Name: {zone['name']}, Points: {zone['points']}")
```

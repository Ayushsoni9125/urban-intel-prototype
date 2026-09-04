"""
reset_demo.py
--------------
Run this before every demo to wipe all previous data.
Gives a clean slate so the dashboard starts at zero.

Usage:
  source .venv/bin/activate
  python reset_demo.py
"""

import os
import json

ROOT = os.path.dirname(os.path.abspath(__file__))

FILES_TO_CLEAR = [
    os.path.join(ROOT, "shared", "live-alerts.json"),
    os.path.join(ROOT, "shared", "traffic-data.json"),
]

IMAGES_DIR = os.path.join(ROOT, "detection", "output", "alerts")

print("\n🔄 Resetting demo data...\n")

# Clear JSON files
for f in FILES_TO_CLEAR:
    with open(f, "w") as fp:
        json.dump([], fp)
    print(f"  ✓ Cleared: {f}")

# Clear evidence images
if os.path.exists(IMAGES_DIR):
    removed = 0
    for img in os.listdir(IMAGES_DIR):
        if img.endswith((".jpg", ".png")):
            os.remove(os.path.join(IMAGES_DIR, img))
            removed += 1
    print(f"  ✓ Removed {removed} evidence image(s) from: {IMAGES_DIR}")

print("\n✅ Reset complete. Dashboard will now show zeros.\n")
print("Run detection to populate data:")
print("  python detection/pothole_detection.py detection/videos/pothole_video.mp4")
print("  python detection/vehicle_detection.py detection/videos/traffic_video.mp4\n")

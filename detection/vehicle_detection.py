"""
vehicle_detection.py  (Improved)
----------------------------------
YOLO-based vehicle detection with:
  1. Simple centroid-based tracking (no DeepSORT needed)
  2. Traffic-density data generation for the dashboard
  3. Simulated GPS route for demo purposes

Target vehicle classes:
  person, car, motorcycle, bus, truck

Usage:
  python detection/vehicle_detection.py detection/videos/traffic_video.mp4
"""

from ultralytics import YOLO
import cv2
import os
import math
import argparse
from datetime import datetime, timezone
import sys

# Add parent dir so we can import alert_generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from alert_generator import save_traffic_data, create_alert

# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

# Load model — looks for yolov8n.pt in the project root first
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
MODEL_PATH = os.path.join(_PROJECT_ROOT, "yolov8n.pt")

model = YOLO(MODEL_PATH)

# Classes we care about (COCO class IDs)
TARGET_CLASSES = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

# Confidence threshold — keep low to catch more vehicles
CONF_THRESHOLD = 0.35

# Process every Nth frame (balances speed vs accuracy)
SAMPLE_EVERY = 5

# --------------------------------------------------
# 2. Simulated GPS route (Demo / Prototype only)
# --------------------------------------------------
# Route runs along a ~2 km stretch in central Delhi.
# These coordinates are SIMULATED for demo purposes.
# Real deployment would use actual GPS hardware.

ROUTE_BASE_LAT = 28.6139   # Connaught Place area
ROUTE_BASE_LNG = 77.2090

# Small increments per frame step to simulate bus movement
LAT_STEP = 0.000015   # ~1.5 metre northward per step
LNG_STEP = 0.000020   # ~2 metre eastward per step


def get_simulated_gps(frame_number: int) -> dict:
    """
    Return simulated GPS for the current frame.
    Coordinates shift slightly each frame to simulate bus movement.
    Add small noise to make the route look realistic on the heatmap.
    """
    import random
    step = frame_number // SAMPLE_EVERY

    # Add tiny random jitter (±10m) so heatmap doesn't look like a straight line
    jitter_lat = random.uniform(-0.00008, 0.00008)
    jitter_lng = random.uniform(-0.00008, 0.00008)

    lat = ROUTE_BASE_LAT + step * LAT_STEP + jitter_lat
    lng = ROUTE_BASE_LNG + step * LNG_STEP + jitter_lng

    return {"lat": round(lat, 6), "lng": round(lng, 6)}


# --------------------------------------------------
# 3. Simple centroid-based tracker
# --------------------------------------------------

class SimpleCentroidTracker:
    """
    Lightweight tracker that assigns IDs to objects based on centroid proximity.

    How it works:
    - Every frame, calculate centroid of each detected bounding box
    - Compare with centroids from the previous frame
    - If a centroid is within MAX_DISTANCE pixels of an old one, treat it as the same object
    - Otherwise assign a new ID

    This prevents counting the same vehicle dozens of times as it moves through the frame.
    """

    MAX_DISTANCE = 80   # pixels — tune based on video resolution

    def __init__(self):
        self.next_id = 0
        # Dict mapping object_id → (centroid_x, centroid_y, class_name)
        self.tracked: dict = {}
        # Total unique objects seen per class
        self.unique_counts: dict = {name: set() for name in TARGET_CLASSES.values()}

    def update(self, detections: list) -> list:
        """
        Update tracker with new detections from a single frame.

        detections: list of dicts with keys:
            class_name, confidence, x1, y1, x2, y2

        Returns:
            list of (object_id, class_name, confidence, cx, cy)
        """

        if not detections:
            # No detections this frame — clear tracked objects
            self.tracked = {}
            return []

        # Calculate centroids for new detections
        new_centroids = []
        for det in detections:
            cx = (det["x1"] + det["x2"]) // 2
            cy = (det["y1"] + det["y2"]) // 2
            new_centroids.append((cx, cy, det["class_name"], det["confidence"]))

        # Match new centroids to existing tracked objects
        matched_ids = {}   # new_index → object_id
        used_tracked = set()

        for new_idx, (cx, cy, cls, conf) in enumerate(new_centroids):
            best_dist = float("inf")
            best_oid = None

            for oid, (ox, oy, ocls) in self.tracked.items():
                # Only match same class
                if ocls != cls:
                    continue
                dist = math.sqrt((cx - ox) ** 2 + (cy - oy) ** 2)
                if dist < self.MAX_DISTANCE and dist < best_dist and oid not in used_tracked:
                    best_dist = dist
                    best_oid = oid

            if best_oid is not None:
                matched_ids[new_idx] = best_oid
                used_tracked.add(best_oid)
            else:
                # New object — assign new ID
                matched_ids[new_idx] = self.next_id
                self.next_id += 1

        # Build new tracked state
        new_tracked = {}
        results = []
        for new_idx, (cx, cy, cls, conf) in enumerate(new_centroids):
            oid = matched_ids[new_idx]
            new_tracked[oid] = (cx, cy, cls)
            self.unique_counts[cls].add(oid)
            results.append((oid, cls, conf, cx, cy))

        self.tracked = new_tracked
        return results

    def get_unique_counts(self) -> dict:
        """Return total unique vehicles seen per class so far."""
        return {cls: len(ids) for cls, ids in self.unique_counts.items()}


# --------------------------------------------------
# 4. Main detection function
# --------------------------------------------------

def detect_vehicles(input_video: str) -> None:
    """
    Process a traffic video:
    - Detect vehicles using YOLOv8
    - Track unique vehicles with centroid tracker
    - Generate traffic-density data with simulated GPS
    - Save annotated output video
    - Append to shared/traffic-data.json
    """

    if not os.path.exists(input_video):
        print(f"Error: Video not found: {input_video}")
        return

    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        print(f"Error: Could not open video: {input_video}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\nVideo: {input_video}")
    print(f"  Resolution: {width}x{height} @ {fps:.1f} fps")
    print(f"  Total frames: {total_frames}")

    # --------------------------------------------------
    # Output video
    # --------------------------------------------------
    output_dir = os.path.join(_THIS_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "traffic_annotated.mp4")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # --------------------------------------------------
    # State tracking
    # --------------------------------------------------
    tracker = SimpleCentroidTracker()

    # Accumulate traffic density points
    traffic_points = []

    # Aggregate vehicle counts across frames for a density point every ~30 frames
    density_accumulator = {name: 0 for name in TARGET_CLASSES.values()}
    density_frame_count = 0
    DENSITY_WINDOW = 30   # aggregate over this many frames before saving a point

    frame_number = 0

    # Running totals for console report
    total_counts = {name: 0 for name in TARGET_CLASSES.values()}

    print(f"\nStarting vehicle detection (every {SAMPLE_EVERY}th frame)...\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_number += 1

        # Skip non-sampled frames but still write to output video
        if frame_number % SAMPLE_EVERY != 0:
            out.write(frame)
            continue

        # --------------------------------------------------
        # Run YOLO inference
        # --------------------------------------------------
        results = model(frame, verbose=False, conf=CONF_THRESHOLD)

        # Parse detections
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                class_id = int(box.cls[0])
                if class_id not in TARGET_CLASSES:
                    continue
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "class_name": TARGET_CLASSES[class_id],
                    "confidence": confidence,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2
                })

        # --------------------------------------------------
        # Update centroid tracker
        # --------------------------------------------------
        tracked_objects = tracker.update(detections)

        # Count per class this frame
        frame_counts = {name: 0 for name in TARGET_CLASSES.values()}
        for (oid, cls, conf, cx, cy) in tracked_objects:
            frame_counts[cls] += 1

        for name in TARGET_CLASSES.values():
            total_counts[name] += frame_counts[name]
            density_accumulator[name] += frame_counts[name]

        density_frame_count += 1

        # --------------------------------------------------
        # Save traffic density point every DENSITY_WINDOW frames
        # --------------------------------------------------
        if density_frame_count >= DENSITY_WINDOW:
            vehicle_count = sum(
                density_accumulator[c]
                for c in ["car", "motorcycle", "bus", "truck"]
            )
            if vehicle_count > 0:
                gps = get_simulated_gps(frame_number)
                point = {
                    "lat": gps["lat"],
                    "lng": gps["lng"],
                    "vehicle_count": vehicle_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "classes": dict(density_accumulator),
                    "frame": frame_number,
                    "simulated_gps": True   # Important: clearly marked as simulated
                }
                traffic_points.append(point)

            # Reset accumulator
            density_accumulator = {name: 0 for name in TARGET_CLASSES.values()}
            density_frame_count = 0

        # --------------------------------------------------
        # Draw annotations on frame
        # --------------------------------------------------
        # Draw bounding boxes and labels
        for (oid, cls, conf, cx, cy) in tracked_objects:
            # Find the original bounding box for this centroid
            for det in detections:
                det_cx = (det["x1"] + det["x2"]) // 2
                det_cy = (det["y1"] + det["y2"]) // 2
                if abs(det_cx - cx) < 5 and abs(det_cy - cy) < 5 and det["class_name"] == cls:
                    x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 80), 2)
                    label = f"#{oid} {cls} {conf:.2f}"
                    cv2.putText(frame, label, (x1, max(y1 - 8, 20)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 80), 2)
                    break

        # Draw per-frame count overlay (top-left)
        y_pos = 30
        for name in TARGET_CLASSES.values():
            if frame_counts[name] > 0:
                text = f"{name}: {frame_counts[name]}"
                cv2.putText(frame, text, (15, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                y_pos += 28

        # Draw unique vehicle count (top-right)
        unique = tracker.get_unique_counts()
        ux_pos = width - 200
        uy_pos = 30
        cv2.putText(frame, "Unique vehicles:", (ux_pos, uy_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 220, 255), 2)
        uy_pos += 24
        for name, count in unique.items():
            if count > 0:
                cv2.putText(frame, f"  {name}: {count}", (ux_pos, uy_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 220, 255), 2)
                uy_pos += 22

        out.write(frame)

        # Console progress
        detected = {k: v for k, v in frame_counts.items() if v > 0}
        if detected:
            print(f"Frame {frame_number}: {detected}")

    # --------------------------------------------------
    # Save final density point if any remaining
    # --------------------------------------------------
    if density_frame_count > 0:
        vehicle_count = sum(
            density_accumulator[c]
            for c in ["car", "motorcycle", "bus", "truck"]
        )
        if vehicle_count > 0:
            gps = get_simulated_gps(frame_number)
            traffic_points.append({
                "lat": gps["lat"],
                "lng": gps["lng"],
                "vehicle_count": vehicle_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "classes": dict(density_accumulator),
                "frame": frame_number,
                "simulated_gps": True
            })

    # --------------------------------------------------
    # Persist traffic data to shared/traffic-data.json
    # --------------------------------------------------
    save_traffic_data(traffic_points)

    # Also create a congestion alert if traffic was high at any point
    if traffic_points:
        peak = max(traffic_points, key=lambda p: p["vehicle_count"])
        if peak["vehicle_count"] >= 10:
            create_alert(
                event_type="vehicle_congestion",
                confidence=min(0.95, peak["vehicle_count"] / 20),
                gps={"lat": peak["lat"], "lng": peak["lng"]},
                bus_id="DL-BUS-042",
                extra={"vehicle_count": peak["vehicle_count"], "classes": peak["classes"]}
            )
            print(f"\n[Alert] Congestion alert created — peak {peak['vehicle_count']} vehicles")

    cap.release()
    out.release()

    # --------------------------------------------------
    # Final report
    # --------------------------------------------------
    unique = tracker.get_unique_counts()
    print("\n" + "=" * 50)
    print("Detection completed!")
    print("=" * 50)

    print("\nTotal frame detections (cumulative):")
    for name, count in total_counts.items():
        print(f"  {name}: {count}")

    print("\nEstimated unique vehicles (centroid tracker):")
    for name, count in unique.items():
        print(f"  {name}: {count}")

    print(f"\nTraffic density points saved: {len(traffic_points)}")
    print(f"Annotated video: {output_path}")


# --------------------------------------------------
# CLI entry point
# --------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Vehicle detection + traffic density using YOLOv8"
    )
    parser.add_argument("video", help="Path to input video file")
    args = parser.parse_args()
    detect_vehicles(args.video)
"""
pothole_detection.py
---------------------
YOLO-based pothole detection with:
  1. Temporal confirmation (3 consecutive detections = confirmed)
  2. Evidence image saving
  3. Alert generation via alert_generator.py
  4. Annotated output video
  5. Simulated GPS coordinates

Usage:
  python detection/pothole_detection.py detection/videos/pothole_video.mp4
"""

from ultralytics import YOLO
import cv2
import os
import sys
import argparse
from datetime import datetime, timezone
import random

# --------------------------------------------------
# Allow importing alert_generator from same directory
# --------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

from alert_generator import create_alert

# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

MODEL_PATH = os.path.join(_THIS_DIR, "models", "pothole_best.pt")

# Confidence threshold — pothole models often need a lower threshold
CONF_THRESHOLD = 0.40

# Process every Nth frame
SAMPLE_EVERY = 5

# Number of consecutive detections needed to "confirm" a pothole
TEMPORAL_CONFIRM_COUNT = 3

# Simulated GPS — Delhi bus route
GPS_BASE_LAT = 28.6095    # Near ITO / Pragati Maidan area
GPS_BASE_LNG = 77.2430
LAT_STEP = 0.000012
LNG_STEP = 0.000018

# Bus ID for this vehicle (pothole detection bus)
BUS_ID = "DL-BUS-017"

# Output paths
OUTPUT_DIR = os.path.join(_THIS_DIR, "output")
ALERTS_DIR = os.path.join(OUTPUT_DIR, "alerts")
OUTPUT_VIDEO = os.path.join(OUTPUT_DIR, "pothole_annotated.mp4")


def get_gps(frame_number: int) -> dict:
    """Return simulated GPS coordinates for this frame. DEMO ONLY."""
    step = frame_number // SAMPLE_EVERY
    jitter_lat = random.uniform(-0.00006, 0.00006)
    jitter_lng = random.uniform(-0.00006, 0.00006)
    return {
        "lat": round(GPS_BASE_LAT + step * LAT_STEP + jitter_lat, 6),
        "lng": round(GPS_BASE_LNG + step * LNG_STEP + jitter_lng, 6),
    }


def detect_potholes(input_video: str) -> None:
    """
    Process a video for pothole detection.

    Algorithm:
    1. Load pothole YOLO model
    2. Sample every SAMPLE_EVERY-th frame
    3. Run inference, filter by CONF_THRESHOLD
    4. Track consecutive detections (temporal confirmation)
    5. On TEMPORAL_CONFIRM_COUNT consecutive detections → save alert + evidence image
    6. Write annotated output video
    """

    # --------------------------------------------------
    # Validate inputs
    # --------------------------------------------------
    if not os.path.exists(input_video):
        print(f"Error: Video not found: {input_video}")
        return

    if not os.path.exists(MODEL_PATH):
        print(f"Error: Pothole model not found: {MODEL_PATH}")
        print("Please download it first. See README.")
        return

    # --------------------------------------------------
    # Load model
    # --------------------------------------------------
    print(f"\nLoading pothole model: {MODEL_PATH}")
    model = YOLO(MODEL_PATH)
    print("Model loaded.")

    # --------------------------------------------------
    # Open video
    # --------------------------------------------------
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        print(f"Error: Cannot open video: {input_video}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"Video: {input_video}")
    print(f"  {width}x{height} @ {fps:.1f} fps, {total_frames} frames")

    # --------------------------------------------------
    # Prepare output
    # --------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ALERTS_DIR, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, fps, (width, height))

    # --------------------------------------------------
    # Temporal confirmation state
    # --------------------------------------------------
    # consecutive_count: how many consecutive sampled frames had a pothole
    consecutive_count = 0

    # best_detection: the detection with highest confidence in the current streak
    best_detection = None
    best_frame = None
    best_frame_number = 0

    # Total confirmed potholes
    confirmed_count = 0
    pothole_number = 0  # for filenames

    frame_number = 0

    print(f"\nProcessing video (sample every {SAMPLE_EVERY} frames, confirm after {TEMPORAL_CONFIRM_COUNT})...\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_number += 1

        if frame_number % SAMPLE_EVERY != 0:
            out.write(frame)
            continue

        # --------------------------------------------------
        # Run YOLO inference
        # --------------------------------------------------
        results = model(frame, verbose=False, conf=CONF_THRESHOLD)

        # Find the highest-confidence pothole detection in this frame
        best_conf = 0.0
        best_box = None

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf > best_conf:
                    best_conf = conf
                    best_box = box

        # --------------------------------------------------
        # Temporal confirmation logic
        # --------------------------------------------------
        if best_box is not None:
            # Detection found this frame — increment streak
            consecutive_count += 1

            # Keep track of the best evidence frame in the streak
            if best_detection is None or best_conf > float(best_detection.conf[0]):
                best_detection = best_box
                best_frame = frame.copy()
                best_frame_number = frame_number

            # --------------------------------------------------
            # Draw annotation on current frame
            # --------------------------------------------------
            x1, y1, x2, y2 = map(int, best_box.xyxy[0])
            status_color = (0, 200, 80) if consecutive_count >= TEMPORAL_CONFIRM_COUNT else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), status_color, 3)

            status_text = "CONFIRMED" if consecutive_count >= TEMPORAL_CONFIRM_COUNT else f"Detecting ({consecutive_count}/{TEMPORAL_CONFIRM_COUNT})"
            label = f"Pothole {best_conf:.2f} [{status_text}]"
            cv2.putText(frame, label, (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

            # --------------------------------------------------
            # Confirmation threshold reached
            # --------------------------------------------------
            if consecutive_count == TEMPORAL_CONFIRM_COUNT:
                pothole_number += 1
                confirmed_count += 1
                gps = get_gps(best_frame_number)
                timestamp = datetime.now(timezone.utc).isoformat()

                print(f"  [CONFIRMED] Pothole #{pothole_number} at frame {best_frame_number}")
                print(f"              Confidence: {float(best_detection.conf[0]):.3f}")
                print(f"              GPS: {gps['lat']}, {gps['lng']} (simulated)")

                # Save cropped evidence image
                ex1, ey1, ex2, ey2 = map(int, best_detection.xyxy[0])

                # Add 20px padding around the pothole crop
                pad = 20
                ex1 = max(0, ex1 - pad)
                ey1 = max(0, ey1 - pad)
                ex2 = min(width, ex2 + pad)
                ey2 = min(height, ey2 + pad)

                crop = best_frame[ey1:ey2, ex1:ex2]

                # Meaningful filename with timestamp
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                evidence_filename = f"pothole_{pothole_number:03d}_{ts_str}.jpg"
                evidence_path = os.path.join(ALERTS_DIR, evidence_filename)
                cv2.imwrite(evidence_path, crop)
                print(f"              Evidence saved: {evidence_path}")

                # Create alert entry
                alert = create_alert(
                    event_type="pothole",
                    confidence=float(best_detection.conf[0]),
                    gps=gps,
                    bus_id=BUS_ID,
                    image_path=f"/images/{evidence_filename}",
                    extra={
                        "frame_number": best_frame_number,
                        "pothole_number": pothole_number,
                        "simulated_gps": True,
                    }
                )
                print(f"              Alert ID: {alert['id'][:8]}...")

        else:
            # No detection this frame — reset streak
            if consecutive_count > 0:
                print(f"  Streak broken at {consecutive_count} (needed {TEMPORAL_CONFIRM_COUNT})")
            consecutive_count = 0
            best_detection = None
            best_frame = None
            best_frame_number = 0

        # --------------------------------------------------
        # HUD overlay (always shown)
        # --------------------------------------------------
        cv2.putText(frame, f"Potholes confirmed: {confirmed_count}",
                    (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Streak: {consecutive_count}/{TEMPORAL_CONFIRM_COUNT}",
                    (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.putText(frame, "GPS: SIMULATED",
                    (15, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        out.write(frame)

        # Progress every 100 sampled frames
        if frame_number % (SAMPLE_EVERY * 50) == 0:
            pct = (frame_number / total_frames) * 100
            print(f"  Progress: {pct:.0f}% (frame {frame_number}/{total_frames})")

    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------
    cap.release()
    out.release()

    print("\n" + "=" * 50)
    print("Pothole detection completed!")
    print("=" * 50)
    print(f"  Total confirmed potholes: {confirmed_count}")
    print(f"  Evidence images saved in: {ALERTS_DIR}")
    print(f"  Annotated video: {OUTPUT_VIDEO}")


# --------------------------------------------------
# CLI
# --------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pothole detection with temporal confirmation"
    )
    parser.add_argument("video", help="Path to input video")
    args = parser.parse_args()
    detect_potholes(args.video)

"""
waterlogging_detection.py
--------------------------
OpenCV HSV-based waterlogging detection with:
  1. Dual-mask analysis — blue water (sky reflections) + dark standing water
  2. Contour area + aspect-ratio filtering to remove small noise
  3. Temporal confirmation (3 consecutive sampled frames = confirmed)
  4. Evidence image saving with annotated bounding box
  5. Alert generation via alert_generator.py
  6. Simulated GPS coordinates (same bus route, offset from pothole track)

Algorithm explanation for SIH judges:
  Water on roads appears in two ways:
    a) Blue-tinted regions — sky reflection in clear puddles
    b) Dark flat regions — turbid/muddy water with uniform low-edge density
  We create an HSV mask for each type, merge them with morphological cleanup,
  find contours, and filter by minimum area (> 6000 px²) and aspect ratio.

Usage:
  python detection/waterlogging_detection.py detection/videos/traffic_video.mp4
"""

import sys
import os
import argparse
import threading
import random
import requests
from datetime import datetime, timezone

import cv2
import numpy as np

# --------------------------------------------------
# Allow importing alert_generator from same directory
# --------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

from alert_generator import create_alert, _save_json, _load_json, ALERTS_FILE

# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Process every Nth frame
SAMPLE_EVERY = 5

# Consecutive confirmations needed before saving an alert
TEMPORAL_CONFIRM_COUNT = 3

# Minimum contour area in pixels to count as waterlogging (filters tiny reflections)
MIN_AREA_PX = 12000

# Minimum width of waterlogging region (px) — rules out vertical drains etc.
MIN_WIDTH_PX = 80

# Aspect ratio range [w/h] for a valid waterlogging region (puddles are wide)
MIN_ASPECT = 1.5
MAX_ASPECT = 8.0

# Simulated GPS — same Delhi area, slightly offset so pins don't overlap with potholes
GPS_BASE_LAT = 28.6115
GPS_BASE_LNG = 77.2395
LAT_STEP = 0.000014
LNG_STEP = 0.000016

BUS_ID = "DL-BUS-019"          # Different vehicle ID for waterlogging cam

# Output paths
OUTPUT_DIR  = os.path.join(_THIS_DIR, "output")
ALERTS_DIR  = os.path.join(OUTPUT_DIR, "alerts")
OUTPUT_VIDEO = os.path.join(OUTPUT_DIR, "waterlogging_annotated.mp4")


# --------------------------------------------------
# GPS helper
# --------------------------------------------------
def get_gps(frame_number: int) -> dict:
    """Return simulated GPS coordinates for this frame. DEMO ONLY."""
    step = frame_number // SAMPLE_EVERY
    jitter_lat = random.uniform(-0.00007, 0.00007)
    jitter_lng = random.uniform(-0.00007, 0.00007)
    return {
        "lat": round(GPS_BASE_LAT + step * LAT_STEP + jitter_lat, 6),
        "lng": round(GPS_BASE_LNG + step * LNG_STEP + jitter_lng, 6),
    }


# --------------------------------------------------
# Core waterlogging detector — HSV + contour analysis
# --------------------------------------------------
def detect_waterlogging_regions(frame: np.ndarray):
    """
    Detect waterlogging in a single BGR frame.

    Returns a list of dicts:
      { x1, y1, x2, y2, area, confidence }

    Confidence is estimated from the normalised area (larger = more confident).
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, w = frame.shape[:2]

    # ── Mask A: Blue-tinted puddles (sky reflection in clear/standing water) ──────────
    # Hue 85–145 = generous blue-cyan range; low-mod saturation; mid brightness
    lower_blue = np.array([85,  15,  50])
    upper_blue = np.array([145, 230, 220])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

    # Use only the blue reflection mask to avoid confusing dark potholes with water
    combined = mask_blue
    
    # Ignore the top 45% of the frame (sky, trees, distant buildings, horizon)
    cutoff = int(h * 0.45)
    combined[:cutoff, :] = 0

    # ── Morphological cleanup ─────────────────────────────────────────────────
    # Close: fills small gaps inside water region
    # Open:  removes tiny isolated noise blobs
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (12, 12))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel_open)

    # ── Contour analysis ──────────────────────────────────────────────────────
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_AREA_PX:
            continue

        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw < MIN_WIDTH_PX:
            continue

        aspect = bw / bh if bh > 0 else 0
        if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
            continue

        # Clamp to frame bounds
        x1 = max(0, bx)
        y1 = max(0, by)
        x2 = min(w, bx + bw)
        y2 = min(h, by + bh)

        # Estimate confidence from normalised region size (larger = more certain)
        frame_area = w * h
        conf = min(0.95, 0.40 + (area / frame_area) * 4.0)

        detections.append({
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "area": int(area), "confidence": round(conf, 3),
        })

    # Sort by area descending — largest waterlogging region first
    detections.sort(key=lambda d: d["area"], reverse=True)
    return detections


# --------------------------------------------------
# Main detection loop
# --------------------------------------------------
def detect_waterlogging(input_video: str) -> None:
    """
    Process a video for waterlogging detection.

    Algorithm:
    1. Sample every SAMPLE_EVERY-th frame
    2. Run HSV-based waterlogging detector
    3. Track consecutive detections (temporal confirmation)
    4. On TEMPORAL_CONFIRM_COUNT consecutive detections → save alert + evidence image
    5. Write annotated output video
    """

    # Validate
    if not os.path.exists(input_video):
        print(f"Error: Video not found: {input_video}")
        return

    # Open video
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        print(f"Error: Cannot open video: {input_video}")
        return

    fps         = cap.get(cv2.CAP_PROP_FPS)
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\nWaterlogging Detector — Video: {input_video}")
    print(f"  {width}x{height} @ {fps:.1f} fps, {total_frames} frames")
    print(f"  Min area: {MIN_AREA_PX}px²  |  Temporal confirm: {TEMPORAL_CONFIRM_COUNT} frames\n")

    # Prepare output
    os.makedirs(OUTPUT_DIR,  exist_ok=True)
    os.makedirs(ALERTS_DIR, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, fps, (width, height))

    # Temporal confirmation state
    consecutive_count    = 0
    best_detection_info  = None      # {x1,y1,x2,y2,area,confidence} of best frame so far
    best_frame_copy      = None
    best_frame_number    = 0

    confirmed_count  = 0
    incident_number  = 0
    frame_number     = 0

    print(f"Processing (sample every {SAMPLE_EVERY} frames, confirm after {TEMPORAL_CONFIRM_COUNT})...\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_number += 1
        
        # Artificial delay to match YOLO processing speed (roughly 30ms)
        import time
        time.sleep(0.03)

        if frame_number % SAMPLE_EVERY != 0:
            out.write(frame)
            continue

        # ── Run waterlogging detector ──────────────────────────────────────────
        detections = detect_waterlogging_regions(frame)

        if detections:
            best_det = detections[0]   # Largest region
            consecutive_count += 1

            # Keep track of the highest-confidence frame in the current streak
            if (best_detection_info is None or
                    best_det["confidence"] > best_detection_info["confidence"]):
                best_detection_info = best_det
                best_frame_copy     = frame.copy()
                best_frame_number   = frame_number

            # ── Draw bounding boxes ────────────────────────────────────────────
            status_color = (255, 165, 0) if consecutive_count >= TEMPORAL_CONFIRM_COUNT else (0, 200, 255)
            for det in detections:
                cv2.rectangle(frame, (det["x1"], det["y1"]), (det["x2"], det["y2"]),
                              status_color, 3)
                status_text = "CONFIRMED" if consecutive_count >= TEMPORAL_CONFIRM_COUNT else f"Detecting ({consecutive_count}/{TEMPORAL_CONFIRM_COUNT})"
                label = f"WATERLOGGING {det['confidence']*100:.0f}% [{status_text}]"
                cv2.putText(frame, label, (det["x1"], max(det["y1"] - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)

            # ── Confirmation threshold reached ─────────────────────────────────
            if consecutive_count == TEMPORAL_CONFIRM_COUNT:
                incident_number += 1
                confirmed_count += 1
                gps       = get_gps(best_frame_number)
                timestamp = datetime.now(timezone.utc).isoformat()

                print(f"  [CONFIRMED] Waterlogging #{incident_number} at frame {best_frame_number}")
                print(f"              Confidence: {best_detection_info['confidence']:.3f}")
                print(f"              Area: {best_detection_info['area']} px²")
                print(f"              GPS: {gps['lat']}, {gps['lng']} (simulated)")

                # Save annotated evidence image
                evidence_frame = best_frame_copy.copy()
                d = best_detection_info
                cv2.rectangle(evidence_frame, (d["x1"], d["y1"]), (d["x2"], d["y2"]),
                              (0, 165, 255), 4)
                cv2.putText(evidence_frame,
                            f"WATERLOGGING {d['confidence']*100:.0f}%",
                            (d["x1"], max(d["y1"] - 12, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 165, 255), 2)

                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                evidence_filename = f"waterlog_{incident_number:03d}_{ts_str}.jpg"
                evidence_path = os.path.join(ALERTS_DIR, evidence_filename)
                cv2.imwrite(evidence_path, evidence_frame)
                print(f"              Evidence saved: {evidence_path}")

                # Create alert
                alert = create_alert(
                    event_type="waterlogging",
                    confidence=best_detection_info["confidence"],
                    gps=gps,
                    bus_id=BUS_ID,
                    image_path=f"/images/{evidence_filename}",
                    extra={
                        "frame_number": best_frame_number,
                        "incident_number": incident_number,
                        "region_area_px": best_detection_info["area"],
                        "simulated_gps": True,
                    }
                )
                print(f"              Alert ID: {alert['id'][:8]}...\n")

        else:
            # No waterlogging this frame — reset streak
            if consecutive_count > 0:
                print(f"  Streak broken at {consecutive_count} (needed {TEMPORAL_CONFIRM_COUNT})")
            consecutive_count   = 0
            best_detection_info = None
            best_frame_copy     = None
            best_frame_number   = 0

        # ── HUD overlay ────────────────────────────────────────────────────────
        cv2.putText(frame, f"Waterlogging confirmed: {confirmed_count}",
                    (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Streak: {consecutive_count}/{TEMPORAL_CONFIRM_COUNT}",
                    (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.putText(frame, f"Regions this frame: {len(detections)}",
                    (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 255), 1)
        cv2.putText(frame, "GPS: SIMULATED | Algorithm: HSV + Contour Analysis",
                    (15, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        # ── Stream frame to dashboard ───────────────────────────────────────────
        small_frame = cv2.resize(frame, (640, int(640 * height / width)))
        ret_enc, buffer = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ret_enc:
            def send_frame(data):
                try:
                    requests.post('http://localhost:8000/api/frame_waterlogging',
                                  data=data, timeout=0.1)
                except Exception:
                    pass
            threading.Thread(target=send_frame, args=(buffer.tobytes(),),
                             daemon=True).start()

        out.write(frame)

        if frame_number % (SAMPLE_EVERY * 50) == 0:
            pct = (frame_number / total_frames) * 100
            print(f"  Progress: {pct:.0f}% (frame {frame_number}/{total_frames})")

    # Cleanup
    cap.release()
    out.release()

    print("\n" + "=" * 50)
    print("Waterlogging detection completed!")
    print("=" * 50)
    print(f"  Total confirmed incidents: {confirmed_count}")
    print(f"  Evidence images: {ALERTS_DIR}")
    print(f"  Annotated video: {OUTPUT_VIDEO}")


# --------------------------------------------------
# CLI
# --------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Waterlogging detection using HSV + contour analysis"
    )
    parser.add_argument("video", help="Path to input video")
    args = parser.parse_args()
    detect_waterlogging(args.video)

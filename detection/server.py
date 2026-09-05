"""
server.py
----------
FastAPI backend for the Urban Road Intelligence Platform.

Endpoints:
  GET /api/health        — System status
  GET /api/alerts        — All alerts from shared/live-alerts.json
  GET /api/traffic       — Traffic density data from shared/traffic-data.json
  GET /images/{filename} — Serve evidence images from detection/output/alerts/

Run with:
  source .venv/bin/activate
  uvicorn detection.server:app --reload --port 8000
  OR:
  python detection/server.py
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import asyncio
from fastapi import Request
import subprocess
import cv2
import numpy as np

# YOLO model for live mobile detection
try:
    from ultralytics import YOLO as _YOLO
    _POTHOLE_MODEL_PATH = _THIS_DIR if False else None  # resolved after _THIS_DIR is defined
except ImportError:
    _YOLO = None


# --------------------------------------------------
# Paths
# --------------------------------------------------
_THIS_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent

ALERTS_FILE = _PROJECT_ROOT / "shared" / "live-alerts.json"
TRAFFIC_FILE = _PROJECT_ROOT / "shared" / "traffic-data.json"
IMAGES_DIR = _THIS_DIR / "output" / "alerts"
VIDEOS_DIR = _THIS_DIR / "videos"
CAPTURE_PAGE = _THIS_DIR / "capture.html"

# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

# Load YOLO pothole model for mobile live detection
_POTHOLE_MODEL_PATH = _THIS_DIR / "models" / "pothole_best.pt"
_mobile_model = None
if _YOLO is not None and _POTHOLE_MODEL_PATH.exists():
    try:
        _mobile_model = _YOLO(str(_POTHOLE_MODEL_PATH))
        print("[Mobile] Pothole model loaded for live camera detection.")
    except Exception as e:
        print(f"[Mobile] Could not load pothole model: {e}")
else:
    print("[Mobile] No pothole model found — mobile detection disabled.")
(_PROJECT_ROOT / "shared").mkdir(parents=True, exist_ok=True)

# Initialize empty JSON files if missing
for fpath in [ALERTS_FILE, TRAFFIC_FILE]:
    if not fpath.exists():
        fpath.write_text("[]")

# --------------------------------------------------
# FastAPI app
# --------------------------------------------------
app = FastAPI(
    title="Urban Road Intelligence API",
    description="Backend for the Urban Road Intelligence Platform — SIH 2026 Prototype",
    version="1.0.0",
)

# --------------------------------------------------
# CORS — allow the React dev server
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for tunnel access (mobile camera)
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the raw input videos for live dashboard viewing
app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")



# --------------------------------------------------
# Helper: safe JSON load
# --------------------------------------------------
def _load_json(filepath: Path) -> list:
    """Load JSON list from file. Returns empty list on error."""
    try:
        if not filepath.exists():
            return []
        raw = filepath.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not read {filepath}: {e}")
        return []


# --------------------------------------------------
# Video Streaming State
# --------------------------------------------------
def _get_placeholder_frame():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.putText(frame, "SYSTEM IDLE - WAITING FOR LIVE FEED", (90, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    _, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes()

PLACEHOLDER_FRAME = _get_placeholder_frame()
LATEST_FRAME = PLACEHOLDER_FRAME
LATEST_WATERLOGGING_FRAME = PLACEHOLDER_FRAME


# --------------------------------------------------
# Process tracking
# --------------------------------------------------
_running_processes = []

# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.post("/api/reset")
async def reset_demo():
    """Reset the demo state."""
    global LATEST_FRAME, _running_processes
    
    # Kill any running scripts
    for p in _running_processes:
        try:
            p.terminate()
        except:
            pass
    _running_processes.clear()

    # Reset video feed
    LATEST_FRAME = PLACEHOLDER_FRAME
    LATEST_WATERLOGGING_FRAME = PLACEHOLDER_FRAME


    # Call reset_demo.py
    reset_script = _PROJECT_ROOT / "reset_demo.py"
    if reset_script.exists():
        subprocess.run([sys.executable, str(reset_script)], cwd=str(_PROJECT_ROOT))
        
    return {"status": "ok", "message": "Demo reset successful."}

@app.post("/api/start")
async def start_demo():
    """Start the YOLO detection scripts in the background."""
    global _running_processes
    
    # Prevent multiple runs
    if any(p.poll() is None for p in _running_processes):
        return {"status": "error", "message": "Detection is already running."}
        
    _running_processes.clear()

    # Start pothole detection
    p1 = subprocess.Popen(
        [sys.executable, "detection/pothole_detection.py", "detection/videos/pothole_video.mp4"],
        cwd=str(_PROJECT_ROOT)
    )
    # Start traffic/vehicle detection
    p2 = subprocess.Popen(
        [sys.executable, "detection/vehicle_detection.py", "detection/videos/traffic_video.mp4"],
        cwd=str(_PROJECT_ROOT)
    )
    _running_processes.extend([p1, p2])
    return {"status": "ok", "message": "Pothole and vehicle detection started."}


@app.post("/api/frame")
async def update_frame(request: Request):
    """Receive a JPEG frame from the detection script."""
    global LATEST_FRAME
    LATEST_FRAME = await request.body()
    return {"status": "ok"}


@app.post("/api/mobile_frame")
async def mobile_frame(request: Request):
    """
    Receive a JPEG frame + real GPS from the mobile capture page.
    Runs YOLO pothole detection on the frame.
    If a pothole is detected, saves an alert with REAL GPS coordinates.
    Updates the live MJPEG feed.
    """
    global LATEST_FRAME, _mobile_model

    # Parse multipart form data
    form = await request.form()
    image_file = form.get("frame")
    lat = float(form.get("lat", 0.0))
    lng = float(form.get("lng", 0.0))

    if image_file is None:
        raise HTTPException(status_code=400, detail="No frame provided")

    # Read raw JPEG bytes
    raw_bytes = await image_file.read()
    np_arr = np.frombuffer(raw_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image")

    detections = []
    annotated_frame = frame.copy()

    # Run YOLO if model is loaded
    if _mobile_model is not None:
        try:
            results = _mobile_model(frame, verbose=False, conf=0.20)  # lower threshold = more sensitive
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append({"confidence": confidence, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
                    # Draw detection box on frame
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    label = f"POTHOLE {confidence*100:.0f}%"
                    cv2.putText(annotated_frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        except Exception as e:
            print(f"[Mobile] YOLO error: {e}")

    # Overlay GPS, status, and detection mode on frame
    cv2.rectangle(annotated_frame, (0, 0), (annotated_frame.shape[1], 75), (0, 0, 0), -1)  # dark bar
    status_text = f"LIVE MOBILE CAM | GPS: {lat:.5f}, {lng:.5f}"
    cv2.putText(annotated_frame, status_text, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 100), 2)
    detect_text = f"Detections this frame: {len(detections)} | Model: pothole_best.pt"
    cv2.putText(annotated_frame, detect_text, (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    # Encode annotated frame as JPEG and update stream
    _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    LATEST_FRAME = buffer.tobytes()

    # --------------------------------------------------
    # Deduplication — skip if 3+ alerts already near this GPS
    # --------------------------------------------------
    DUPLICATE_THRESHOLD = 3    # max allowed detections per location
    NEARBY_RADIUS_M    = 100   # metres — wider radius to handle GPS jitter

    def _haversine_m(lat1, lng1, lat2, lng2) -> float:
        """Return distance in metres between two GPS points."""
        import math
        R = 6_371_000  # Earth radius in metres
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Save alert and evidence image for each confirmed detection
    saved_alerts = []
    is_duplicate  = False
    nearby_count  = 0

    if detections and lat != 0.0:
        # Load existing alerts once
        try:
            existing = json.loads(ALERTS_FILE.read_text(encoding="utf-8").strip() or "[]")
        except Exception:
            existing = []

        # Count how many pothole alerts are within NEARBY_RADIUS_M
        nearby_alerts = [
            a for a in existing
            if a.get("event_type") == "pothole"
            and a.get("gps")
            and _haversine_m(lat, lng, a["gps"]["lat"], a["gps"]["lng"]) <= NEARBY_RADIUS_M
        ]
        nearby_count = len(nearby_alerts)

        if nearby_count >= DUPLICATE_THRESHOLD:
            # Already detected here enough times — skip saving
            is_duplicate = True
            print(f"[Mobile] Duplicate skipped — {nearby_count} alerts within {NEARBY_RADIUS_M}m of ({lat:.5f}, {lng:.5f})")
        else:
            best = max(detections, key=lambda d: d["confidence"])
            alert_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()

            # Save evidence image
            img_filename = f"mobile_{alert_id[:8]}.jpg"
            img_path = IMAGES_DIR / img_filename
            cv2.imwrite(str(img_path), annotated_frame)

            alert = {
                "id": alert_id,
                "event_type": "pothole",
                "confidence": round(best["confidence"], 3),
                "timestamp": timestamp,
                "gps": {"lat": lat, "lng": lng},
                "bus_id": "MOBILE-CAM",
                "image_path": img_filename,
                "source": "mobile_camera",
            }
            existing.insert(0, alert)
            ALERTS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            saved_alerts.append(alert_id)
            print(f"[Mobile] Pothole saved — GPS: ({lat:.5f}, {lng:.5f}), conf: {best['confidence']:.2f}")

    return {
        "status": "ok",
        "detections": len(detections),
        "alerts_saved": len(saved_alerts),
        "duplicate": is_duplicate,
        "nearby_count": nearby_count,
        "gps": {"lat": lat, "lng": lng},
    }


async def _frame_generator():
    """Generator for MJPEG stream."""
    global LATEST_FRAME
    while True:
        if LATEST_FRAME:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + LATEST_FRAME + b'\r\n')
        await asyncio.sleep(0.05)  # Max 20 fps


@app.get("/api/video_feed")
async def video_feed():
    """Stream live detection frames to the dashboard."""
    return StreamingResponse(_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/capture", response_class=HTMLResponse)
async def mobile_capture_page():
    """Serve the mobile camera capture page."""
    if CAPTURE_PAGE.exists():
        return HTMLResponse(content=CAPTURE_PAGE.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Capture page not found</h1>", status_code=404)


@app.get("/api/health")
async def health():
    """
    System health check.
    Returns status, counts, and server timestamp.
    """
    alerts = _load_json(ALERTS_FILE)
    traffic = _load_json(TRAFFIC_FILE)

    pothole_count = sum(1 for a in alerts if a.get("event_type") == "pothole")
    traffic_count = sum(1 for a in alerts if a.get("event_type") in ("traffic_density", "vehicle_congestion"))
    image_count = len(list(IMAGES_DIR.glob("*.jpg"))) + len(list(IMAGES_DIR.glob("*.png")))

    return {
        "status": "active",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "total_alerts": len(alerts),
            "pothole_alerts": pothole_count,
            "traffic_alerts": traffic_count,
            "traffic_density_points": len(traffic),
            "evidence_images": image_count,
        },
        "note": "GPS coordinates in this prototype are simulated for demo purposes.",
    }


@app.get("/api/alerts")
async def get_alerts():
    """
    Return all alerts from shared/live-alerts.json.
    Sorted by timestamp descending (newest first).
    """
    alerts = _load_json(ALERTS_FILE)

    # Sort newest first
    try:
        alerts.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
    except Exception:
        pass  # Don't fail if sorting breaks

    return JSONResponse(content=alerts)


@app.get("/api/traffic")
async def get_traffic():
    """
    Return traffic density data from shared/traffic-data.json.
    Each point contains lat, lng, vehicle_count, classes, timestamp.
    """
    traffic = _load_json(TRAFFIC_FILE)
    return JSONResponse(content=traffic)


@app.get("/api/stats")
async def get_stats():
    """
    Aggregate statistics for the dashboard summary cards.
    """
    alerts = _load_json(ALERTS_FILE)
    traffic = _load_json(TRAFFIC_FILE)

    pothole_alerts = [a for a in alerts if a.get("event_type") == "pothole"]
    congestion_alerts = [a for a in alerts if a.get("event_type") == "vehicle_congestion"]

    # Total unique vehicles from traffic data
    total_vehicles = sum(p.get("vehicle_count", 0) for p in traffic)

    # Unique bus IDs seen
    bus_ids = set(a.get("bus_id", "") for a in alerts if a.get("bus_id"))

    return {
        "total_road_defects": len(pothole_alerts),
        "potholes_detected": len(pothole_alerts),
        "traffic_events": len(traffic),
        "vehicles_detected": total_vehicles,
        "active_buses": len(bus_ids),
        "congestion_events": len(congestion_alerts),
    }


@app.get("/images/{filename}")
async def serve_image(filename: str):
    """
    Serve evidence images from detection/output/alerts/.
    The React frontend references these as /images/<filename>.
    """
    # Security: prevent path traversal
    safe_name = Path(filename).name
    image_path = IMAGES_DIR / safe_name

    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {safe_name}")

    media_type = "image/jpeg" if safe_name.endswith(".jpg") else "image/png"
    return FileResponse(str(image_path), media_type=media_type)


# --------------------------------------------------
# Frontend Static Files (For Production/Docker)
# --------------------------------------------------
DASHBOARD_DIST = _PROJECT_ROOT / "dashboard" / "dist"
if DASHBOARD_DIST.exists():
    # Mount everything else to the built React app
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIST), html=True), name="frontend")


# --------------------------------------------------
# Run directly
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("\nStarting Urban Road Intelligence API...")
    print("  Alerts file:  ", ALERTS_FILE)
    print("  Traffic file: ", TRAFFIC_FILE)
    print("  Images dir:   ", IMAGES_DIR)
    print("\nAPI docs: http://localhost:8000/docs")
    print("Health:   http://localhost:8000/api/health\n")
    # Clean up processes on exit
    try:
        uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, app_dir=str(_THIS_DIR))
    finally:
        for p in _running_processes:
            try: p.terminate()
            except: pass

# --------------------------------------------------
# Waterlogging Live Endpoints
# --------------------------------------------------

from detection.waterlogging_detection import detect_waterlogging_regions
CAPTURE_WATERLOGGING_PAGE = _THIS_DIR / "capture_waterlogging.html"

async def _waterlogging_frame_generator():
    """Generator for Waterlogging MJPEG stream."""
    global LATEST_WATERLOGGING_FRAME
    while True:
        if LATEST_WATERLOGGING_FRAME:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + LATEST_WATERLOGGING_FRAME + b'\r\n')
        await asyncio.sleep(0.05)

@app.get("/api/video_feed_waterlogging")
async def video_feed_waterlogging():
    """Stream live waterlogging frames to the dashboard."""
    return StreamingResponse(_waterlogging_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/capture_waterlogging", response_class=HTMLResponse)
async def mobile_capture_waterlogging_page():
    """Serve the mobile camera capture page for waterlogging."""
    if CAPTURE_WATERLOGGING_PAGE.exists():
        return HTMLResponse(content=CAPTURE_WATERLOGGING_PAGE.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Capture page not found</h1>", status_code=404)

@app.post("/api/mobile_frame_waterlogging")
async def mobile_frame_waterlogging(request: Request):
    """
    Receive a JPEG frame + real GPS from the mobile capture page (waterlogging).
    """
    global LATEST_WATERLOGGING_FRAME

    form = await request.form()
    image_file = form.get("frame")
    lat = float(form.get("lat", 0.0))
    lng = float(form.get("lng", 0.0))

    if image_file is None:
        raise HTTPException(status_code=400, detail="No frame provided")

    raw_bytes = await image_file.read()
    np_arr = np.frombuffer(raw_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image")

    annotated_frame = frame.copy()
    
    # Run HSV detection
    detections = detect_waterlogging_regions(frame)

    for det in detections:
        x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
        conf = det["confidence"]
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 165, 255), 3)
        label = f"WATERLOGGING {conf*100:.0f}%"
        cv2.putText(annotated_frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    cv2.rectangle(annotated_frame, (0, 0), (annotated_frame.shape[1], 75), (0, 0, 0), -1)
    status_text = f"WATERLOGGING CAM | GPS: {lat:.5f}, {lng:.5f}"
    cv2.putText(annotated_frame, status_text, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    detect_text = f"Regions this frame: {len(detections)} | Model: HSV+Contour"
    cv2.putText(annotated_frame, detect_text, (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    LATEST_WATERLOGGING_FRAME = buffer.tobytes()

    DUPLICATE_THRESHOLD = 3
    NEARBY_RADIUS_M = 100

    def _haversine_m(lat1, lng1, lat2, lng2) -> float:
        import math
        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    saved_alerts = []
    is_duplicate = False
    nearby_count = 0

    if detections and lat != 0.0:
        try:
            existing = json.loads(ALERTS_FILE.read_text(encoding="utf-8").strip() or "[]")
        except Exception:
            existing = []

        nearby_alerts = [
            a for a in existing
            if a.get("event_type") == "waterlogging"
            and a.get("gps")
            and _haversine_m(lat, lng, a["gps"]["lat"], a["gps"]["lng"]) <= NEARBY_RADIUS_M
        ]
        nearby_count = len(nearby_alerts)

        if nearby_count >= DUPLICATE_THRESHOLD:
            is_duplicate = True
        else:
            best = max(detections, key=lambda d: d["confidence"])
            alert_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()

            img_filename = f"waterlog_mobile_{alert_id[:8]}.jpg"
            img_path = IMAGES_DIR / img_filename
            cv2.imwrite(str(img_path), annotated_frame)

            alert = {
                "id": alert_id,
                "event_type": "waterlogging",
                "confidence": round(best["confidence"], 3),
                "timestamp": timestamp,
                "gps": {"lat": lat, "lng": lng},
                "bus_id": "MOBILE-CAM-WATERLOG",
                "image_path": img_filename,
                "source": "mobile_camera",
                "region_area_px": best["area"],
            }
            existing.insert(0, alert)
            ALERTS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            saved_alerts.append(alert_id)

    return {
        "status": "ok",
        "detections": len(detections),
        "alerts_saved": len(saved_alerts),
        "duplicate": is_duplicate,
        "nearby_count": nearby_count,
        "gps": {"lat": lat, "lng": lng},
    }

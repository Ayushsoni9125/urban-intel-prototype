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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
from fastapi import Request
import subprocess
import cv2
import numpy as np


# --------------------------------------------------
# Paths
# --------------------------------------------------
_THIS_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent

ALERTS_FILE = _PROJECT_ROOT / "shared" / "live-alerts.json"
TRAFFIC_FILE = _PROJECT_ROOT / "shared" / "traffic-data.json"
IMAGES_DIR = _THIS_DIR / "output" / "alerts"
VIDEOS_DIR = _THIS_DIR / "videos"

# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
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
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
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
    # Start traffic detection
    p2 = subprocess.Popen(
        [sys.executable, "detection/vehicle_detection.py", "detection/videos/traffic_video.mp4"],
        cwd=str(_PROJECT_ROOT)
    )
    
    _running_processes.extend([p1, p2])
    return {"status": "ok", "message": "Detection started."}


@app.post("/api/frame")
async def update_frame(request: Request):
    """Receive a JPEG frame from the detection script."""
    global LATEST_FRAME
    LATEST_FRAME = await request.body()
    return {"status": "ok"}

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

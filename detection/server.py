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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# --------------------------------------------------
# Paths
# --------------------------------------------------
_THIS_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _THIS_DIR.parent

ALERTS_FILE = _PROJECT_ROOT / "shared" / "live-alerts.json"
TRAFFIC_FILE = _PROJECT_ROOT / "shared" / "traffic-data.json"
IMAGES_DIR = _THIS_DIR / "output" / "alerts"

# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
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
# Routes
# --------------------------------------------------

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
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, app_dir=str(_THIS_DIR))

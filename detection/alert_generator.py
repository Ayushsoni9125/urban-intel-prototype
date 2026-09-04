"""
alert_generator.py
------------------
Reusable alert creation utility for the Urban Road Intelligence Platform.

This module handles:
- Creating structured alert objects
- Reading / writing shared/live-alerts.json safely
- Avoiding duplicate alerts within a short time window
"""

import json
import uuid
import os
from datetime import datetime, timezone

# --------------------------------------------------
# Path to the shared alerts JSON file
# --------------------------------------------------
# Resolved relative to the project root (one level up from detection/)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
ALERTS_FILE = os.path.join(_PROJECT_ROOT, "shared", "live-alerts.json")
TRAFFIC_FILE = os.path.join(_PROJECT_ROOT, "shared", "traffic-data.json")

# --------------------------------------------------
# Ensure shared/ directory exists
# --------------------------------------------------
os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)


def _load_json(filepath: str) -> list:
    """Load a JSON file as a list. Returns empty list if file is missing or corrupt."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _save_json(filepath: str, data: list) -> None:
    """Write a list to a JSON file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def create_alert(
    event_type: str,
    confidence: float,
    gps: dict,
    bus_id: str,
    image_path: str = "",
    extra: dict = None,
) -> dict:
    """
    Create a single alert dictionary and append it to live-alerts.json.

    Parameters
    ----------
    event_type   : e.g. "pothole", "vehicle_congestion", "traffic_density"
    confidence   : float 0.0–1.0
    gps          : {"lat": float, "lng": float}
    bus_id       : e.g. "DL-BUS-042"
    image_path   : optional path to evidence image (relative or absolute)
    extra        : optional dict with additional fields

    Returns
    -------
    The alert dict that was created.
    """

    alert = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "confidence": round(confidence, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gps": {
            "lat": round(gps.get("lat", 28.6139), 6),
            "lng": round(gps.get("lng", 77.2090), 6),
        },
        "bus_id": bus_id,
        "image_path": image_path,
    }

    if extra:
        alert.update(extra)

    # Append to the shared alerts file
    alerts = _load_json(ALERTS_FILE)
    alerts.append(alert)
    _save_json(ALERTS_FILE, alerts)

    return alert


def save_traffic_data(traffic_points: list) -> None:
    """
    Overwrite shared/traffic-data.json with the given list of traffic density points.

    Each point should look like:
    {
        "lat": 28.6142,
        "lng": 77.2101,
        "vehicle_count": 18,
        "timestamp": "...",
        "classes": { "car": 10, "motorcycle": 4, ... }
    }
    """
    _save_json(TRAFFIC_FILE, traffic_points)
    print(f"[AlertGenerator] Traffic data saved: {len(traffic_points)} points → {TRAFFIC_FILE}")


def initialize_files() -> None:
    """Create empty JSON files if they don't exist yet."""
    if not os.path.exists(ALERTS_FILE):
        _save_json(ALERTS_FILE, [])
        print(f"[AlertGenerator] Initialized: {ALERTS_FILE}")
    if not os.path.exists(TRAFFIC_FILE):
        _save_json(TRAFFIC_FILE, [])
        print(f"[AlertGenerator] Initialized: {TRAFFIC_FILE}")


# Initialize on import
initialize_files()

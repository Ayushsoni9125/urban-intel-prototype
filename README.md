# Urban Road Intelligence Platform
### SIH 2026 Prototype — AI-powered Road Monitoring Using Public Transport Fleet

---

## Overview

This prototype demonstrates an end-to-end AI pipeline that processes **public bus dashcam video** to detect road defects (potholes) and traffic conditions, then visualizes the results on a **government-style dashboard**.

**This is a prototype. GPS coordinates are simulated. Not for production use.**

---

## Architecture

```
Traffic Video                    Pothole Video
      ↓                                ↓
YOLO Vehicle Detection          Pothole YOLO Model
      ↓                                ↓
Centroid Tracker            Temporal Confirmation (3 frames)
      ↓                                ↓
Traffic Density Data          Evidence Images + Alerts
      ↓                                ↓
shared/traffic-data.json    shared/live-alerts.json
                ↓                    ↓
              FastAPI (detection/server.py)
                        ↓
              React Dashboard (dashboard/)
                        ↓
        ┌───────────────────────────────────┐
        │ Live Map with Pothole Markers     │
        │ Traffic Density Heatmap           │
        │ Pothole Heatmap                   │
        │ Statistics                        │
        │ Recent Alerts                     │
        │ Detection Preview + Evidence      │
        │ Incident Report (Printable PDF)   │
        └───────────────────────────────────┘
```

---

## Project Structure

```
urban-intel-prototype/
│
├── detection/
│   ├── videos/
│   │   ├── traffic_video.mp4        # Input traffic video
│   │   └── pothole_video.mp4        # Input pothole video
│   │
│   ├── models/
│   │   └── pothole_best.pt          # Pretrained pothole YOLOv8 model
│   │
│   ├── output/
│   │   ├── traffic_annotated.mp4    # Annotated output video
│   │   ├── pothole_annotated.mp4    # Annotated pothole video
│   │   └── alerts/                  # Cropped evidence images
│   │       └── pothole_001_*.jpg
│   │
│   ├── vehicle_detection.py         # Vehicle detection + tracking + traffic data
│   ├── pothole_detection.py         # Pothole detection + temporal confirmation
│   ├── alert_generator.py           # Shared alert creation utility
│   └── server.py                    # FastAPI backend
│
├── dashboard/
│   ├── src/
│   │   ├── App.jsx                  # Main app with polling
│   │   ├── components/
│   │   │   ├── Header.jsx           # Top bar with status
│   │   │   ├── StatsBar.jsx         # Summary statistics
│   │   │   ├── MapView.jsx          # Leaflet map + heatmaps
│   │   │   ├── AlertTable.jsx       # Alerts list
│   │   │   ├── DetectionPreview.jsx # Evidence image viewer
│   │   │   └── IncidentReport.jsx   # Printable report
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
│
├── shared/
│   ├── live-alerts.json             # All alerts (pothole + congestion)
│   └── traffic-data.json            # Traffic density points
│
├── .venv/                           # Python virtual environment
├── requirements.txt
└── README.md
```

---

## Setup

### Prerequisites
- Python 3.12+
- Node.js 18+
- The videos inside `detection/videos/`

### 1. Activate Python environment

```bash
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd dashboard
npm install
cd ..
```

---

## Running the System

### Step 1 — Run Traffic Detection

```bash
source .venv/bin/activate
python detection/vehicle_detection.py detection/videos/traffic_video.mp4
```

Outputs:
- `detection/output/traffic_annotated.mp4`
- `shared/traffic-data.json` (44 density points)
- Appends congestion alert to `shared/live-alerts.json`

### Step 2 — Run Pothole Detection

```bash
source .venv/bin/activate
python detection/pothole_detection.py detection/videos/pothole_video.mp4
```

Outputs:
- `detection/output/pothole_annotated.mp4`
- `detection/output/alerts/pothole_*.jpg` (evidence images)
- Appends pothole alerts to `shared/live-alerts.json`

### Step 3 — Start FastAPI Backend

```bash
source .venv/bin/activate
cd detection
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Or alternatively:
```bash
source .venv/bin/activate && cd detection && python server.py
```

### Step 4 — Start React Dashboard

```bash
cd dashboard
npm run dev
```

---

## URLs

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API Health | http://localhost:8000/api/health |
| Alerts API | http://localhost:8000/api/alerts |
| Traffic API | http://localhost:8000/api/traffic |
| Statistics API | http://localhost:8000/api/stats |
| API Docs | http://localhost:8000/docs |
| Evidence Image | http://localhost:8000/images/pothole_001_*.jpg |

---

## Judge Demo Sequence

1. **Open the dashboard** → http://localhost:5173
   - Point out the header, status indicator, and SIH prototype badge
   
2. **Show statistics** — all real values from detection:
   - Road Defects: 5 (confirmed potholes)
   - Traffic Events: 44 (density data points)
   - Vehicles Detected: 5,757
   - Active Buses: 2

3. **Show the map**:
   - Point out red pothole markers in the Delhi area
   - Toggle Traffic Heatmap — shows vehicle density colored by intensity
   - Toggle Pothole Heatmap — shows pothole concentration
   - Toggle Both Layers — combined view

4. **Click a pothole marker** on the map → popup shows details + evidence image

5. **Click a table row** → Detection Preview shows:
   - Confidence score
   - Simulated GPS
   - Bus ID
   - Cropped evidence photo from dashcam frame

6. **Click Generate Report** on any pothole row → Incident Report modal opens
   - Official PWD-style format
   - Incident ID, GPS, bus ID, evidence image
   - "Print / Save as PDF" button → window.print()

7. **Explain real-time polling** — dashboard refreshes every 5 seconds from FastAPI

8. **Show the terminal** with detection output running

---

## What is Real vs. Simulated

### REAL (AI processed)
- YOLOv8 object detection on actual video files
- Vehicle counting and tracking (centroid tracker)
- Pothole detection with temporal confirmation (3 consecutive frames)
- Confidence scores from YOLO model
- Cropped evidence images from actual video frames
- Alert generation and JSON persistence
- Dashboard visualization of detection data

### SIMULATED (Demo only)
- GPS coordinates (no real GPS hardware)
- Bus ID (DL-BUS-017, DL-BUS-042 are assigned, not real)
- "Live" streaming (actually batch processed video)
- Real-time updates (polling replays the same processed data)

---

## Known Limitations

1. **GPS is simulated** — coordinates follow a route near Delhi/New Delhi but are not real
2. **Batch processing** — videos are processed offline, not truly real-time
3. **Single model for potholes** — model from HuggingFace (peterhdd/pothole-detection-yolov8), not custom-trained
4. **No authentication** — prototype has no login/user management
5. **JSON storage** — no database; data resets when JSON files are deleted
6. **Traffic heatmap** — uses simulated route, not actual road network GPS

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Vehicle Detection | Ultralytics YOLOv8n (COCO pretrained) |
| Pothole Detection | YOLOv8 (pothole-specific, HuggingFace) |
| Object Tracking | Custom centroid-based tracker |
| Backend API | FastAPI + Uvicorn |
| Frontend | React + Vite |
| Styling | Tailwind CSS v4 |
| Map | Leaflet + leaflet.heat |
| Storage | JSON files |
| Video Processing | OpenCV |

---

## Resetting Data

To run fresh detections:

```bash
# Clear existing data
echo "[]" > shared/live-alerts.json
echo "[]" > shared/traffic-data.json
rm -f detection/output/alerts/*.jpg

# Re-run detection
source .venv/bin/activate
python detection/vehicle_detection.py detection/videos/traffic_video.mp4
python detection/pothole_detection.py detection/videos/pothole_video.mp4
```

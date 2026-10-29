# AI Crowd Intelligence & Entry-Exit Management System

> Production-ready, modular computer-vision platform for high-footfall venues (temples, stadiums, transit hubs, exhibitions) featuring multi-camera entry/exit line tracking, real-time occupancy estimation, crowd flow velocity, predictive bottleneck forecasting, and automated alert dispatching.

---

## 🌟 Key Features

- **Multi-Camera Computer Vision Ingestion**:
  - Supports USB Webcams, RTSP IP camera streams, HTTP MJPEG feeds, and recorded video files.
  - Background threaded pipeline running YOLO object detection and BoT-SORT / ByteTrack multi-object tracking.
- **Precision Virtual Gate Counting**:
  - Configurable entry/exit virtual counting lines with normalized coordinates `(0.0 - 1.0)`.
  - Geometric ray-segment crossing detection with directional assignment (`down`, `up`, `left`, `right`).
  - Strict cooldown hysteresis, bounding-box centroid tracking, and track expiry deduplication.
- **Occupancy & Capacity Intelligence**:
  - Baseline initialization and mid-shift manual re-alignment audit logging.
  - Automatic capacity calculation from venue area (m²) and density standard (e.g. 2.0 persons/m²) or admin limits.
  - Resilient to network disconnects: immutable counting event ledger recalculates true occupancy state.
- **Flow Velocity & Predictive Forecasting**:
  - Sliding-window flow analysis (inflow/min, outflow/min, net velocity/min).
  - Trend forecasting (15m, 30m, 45m, 60m horizons) and estimated time-to-warning and time-to-capacity (ETA).
- **Incident Alerts & Actionable Dispatch**:
  - Automatic threshold triggers: `NORMAL`, `WARNING` (75%), `CRITICAL` (90%), `DATA_UNRELIABLE`.
  - Operator acknowledgment and resolution workflow with incident notes.
- **Modern High-Performance UI**:
  - Built with React 19, TypeScript, Vite, Tailwind CSS v4, Lucide icons, and Recharts.
  - Sleek glassmorphism dark theme with real-time WebSocket state streaming (auto-reconnect).

---

## 🏗️ Architecture

```
                                  ┌─────────────────────────────┐
                                  │      Camera Feeds           │
                                  │ (Webcams, RTSP, Video Files)│
                                  └──────────────┬──────────────┘
                                                 │ OpenCV Frames
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │    Background Video Worker  │
                                  │  - YOLOv8 Person Detection  │
                                  │  - BoT-SORT / ByteTrack     │
                                  │  - Virtual Line Crossing    │
                                  └──────────────┬──────────────┘
                                                 │ Crossing Event (IN / OUT)
                                                 ▼
┌─────────────────────────────────┐   FastAPI    ┌─────────────────────────────┐
│       React + Vite Frontend     │◄────────────►│       FastAPI Backend       │
│  - Live Glassmorphism Dashboard │   REST & WS  │  - Occupancy & Flow Engine  │
│  - Venue Setup & Calibration    │              │  - Forecast & Alert Manager │
│  - Gate & Camera Manager        │              │  - SQLite / Postgres DB     │
└─────────────────────────────────┘              └─────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python**: 3.10+ (tested on Python 3.11)
- **Node.js**: 18+ and npm
- **Webcam / Video file** (optional for live tracking)

### 2. Quick Launch (Windows)

Simply double-click or run:
```cmd
run.bat
```
This automatically boots:
- **Backend API**: `http://localhost:8000` (Swagger docs at `http://localhost:8000/docs`)
- **Frontend Dashboard**: `http://localhost:5173`

To seed demo data with a pre-configured high-footfall pilgrimage corridor:
```cmd
run.bat seed
```

---

## 🛠️ Manual Installation

### Backend Setup
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Seed realistic sample venue and gates
python -m app.scripts.seed_demo

# Start backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Build for production or start dev server
npm run dev
```

---

## 🐳 Docker Deployment

Run both backend and frontend in containerized isolation:
```bash
docker compose up --build
```
- Frontend will be served at `http://localhost:3000`
- Backend API will be served at `http://localhost:8000`

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | System health, camera count, uptime |
| `GET` | `/api/v1/venues` | List all venues with occupancy status |
| `POST` | `/api/v1/venues` | Create venue with capacity rules |
| `POST` | `/api/v1/venues/{id}/baseline` | Set initial occupancy baseline |
| `POST` | `/api/v1/venues/{id}/reconcile`| Reconcile current occupancy |
| `GET` | `/api/v1/venues/{id}/dashboard`| Complete aggregated venue state |
| `GET` | `/api/v1/venues/{id}/occupancy`| Current occupancy & capacity metrics |
| `GET` | `/api/v1/venues/{id}/flow` | Flow velocity (inflow/outflow per min) |
| `GET` | `/api/v1/venues/{id}/forecast` | Predictive capacity horizon forecasts |
| `GET` | `/api/v1/venues/{id}/alerts` | Active and historical incident alerts |
| `POST`| `/api/v1/alerts/{id}/acknowledge` | Acknowledge alert |
| `POST`| `/api/v1/alerts/{id}/resolve` | Resolve alert with operator note |
| `GET` | `/api/v1/venues/{id}/gates` | List all gates and camera statuses |
| `POST`| `/api/v1/gates/{id}/start` | Start live camera tracking worker |
| `POST`| `/api/v1/gates/{id}/stop` | Stop live camera tracking worker |
| `WS`  | `/api/v1/ws/dashboard/{id}`| Live WebSocket bi-directional stream |

---

## ⚙️ Configuration (.env)

Configuration parameters can be set in `backend/.env` (see `backend/.env.example`):

```ini
APP_NAME=AI Crowd Intelligence System
APP_VERSION=1.0.0
DEBUG=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000

DATABASE_URL=sqlite:///./crowd_intel.db
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# Video Analytics
YOLO_MODEL=yolov8n.pt
TRACKER_CONFIG=tracker_configs/botsort.yaml
DEFAULT_CONFIDENCE_THRESHOLD=0.25
DEFAULT_FRAME_SKIP=1
CAMERA_RECONNECT_INTERVAL=5.0
MAX_RECONNECT_ATTEMPTS=5

# Flow & Alerts
FLOW_RATE_WINDOW_SECONDS=60
FORECAST_HORIZONS=[15,30,45,60]
ALERT_COOLDOWN_SECONDS=300
WS_BROADCAST_INTERVAL=1.0
```

---

## 🧪 Testing

Comprehensive test suites cover:
- Virtual line-crossing geometric math (entry/exit directions, duplicate filtering, trajectory hysteresis)
- Flow calculation, baseline calibration, and capacity alerts
- Full FastAPI endpoint integration tests

```bash
cd backend
python -m pytest tests -v
```

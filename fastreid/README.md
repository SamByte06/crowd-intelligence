# FastReID Dual-Camera Person Tracking & Cross-Camera Re-Identification

Dual-camera real-time person tracking and cross-camera Re-ID demo powered by **FastReID (ResNeSt-50 SBS)** and **YOLO11s + ByteTrack**, featuring FastAPI web streaming and analytics.

---

## Architecture & Features

- **Detection & Tracking**: YOLO11s person detector paired with ByteTrack per camera feed.
- **Feature Extraction**: FastReID ResNeSt-50 SBS trained on Market1501 extracting 2048-dim normalized embedding vectors.
- **Cross-Camera Matching**: `IdentityGallery` matching queries across cameras using cosine similarity with adaptive thresholding and temporal expiry.
- **FastAPI Dashboard**: Real-time MJPEG live feeds with bounding boxes, global IDs, crowd analytics, and gallery inspection.

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SamByte06/fastreid.git
   cd fastreid
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download FastReID Pretrained Weights:**
   Download `market_sbs_S50.pth` (~324 MB) and place it in the `fast-reid/` directory:
   ```bash
   # Windows (PowerShell):
   Invoke-WebRequest -Uri "https://github.com/JDAI-CV/fast-reid/releases/download/v0.1.1/market_sbs_S50.pth" -OutFile "fast-reid/market_sbs_S50.pth"

   # Linux/macOS:
   wget https://github.com/JDAI-CV/fast-reid/releases/download/v0.1.1/market_sbs_S50.pth -O fast-reid/market_sbs_S50.pth
   ```

   *(Note: YOLO11s weights `yolo11s.pt` will automatically be downloaded by Ultralytics upon initial run).*

---

## Running the Application

Start the FastAPI application:
```bash
python app.py
```
Or with uvicorn:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open your browser at `http://localhost:8000` to access the interactive web interface.

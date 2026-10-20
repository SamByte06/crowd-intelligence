@echo off
title AI Crowd Intelligence - Local Launcher
echo ========================================================
echo       AI CROWD INTELLIGENCE - LOCAL LAUNCHER
echo ========================================================
echo.
echo Starting all 3 services:
echo   1. Backend API (FastAPI)     - http://localhost:8001
echo   2. AI Tracking Engine (Webcam 0) - http://localhost:8000
echo   3. Frontend Web Dashboard    - http://localhost:5173
echo.

cd /d "%~dp0"

echo [1/3] Starting FastAPI Backend on port 8001...
start "AI Backend (Port 8001)" cmd /k "cd /d "%~dp0backend" && "..\venv\Scripts\activate" && uvicorn api.index:app --reload --port 8001"

timeout /t 2 /nobreak >nul

echo [2/3] Starting AI Engine with Laptop Webcam (source 0)...
start "AI Camera Engine (Port 8000)" cmd /k "cd /d "%~dp0" && ".\venv\Scripts\python.exe" track_webcam.py --source 0"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Frontend Dashboard on port 5173...
start "AI Frontend (Port 5173)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ========================================================
echo All services launched!
echo Dashboard will be available at: http://localhost:5173
echo.
echo Note: Inside the Dashboard, you can live-switch between
echo your Laptop Webcam and any YouTube link at any time!
echo ========================================================
echo.
pause

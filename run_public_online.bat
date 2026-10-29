@echo off
setlocal enabledelayedexpansion

echo ===================================================================
echo     AI Crowd Intelligence — Launching Public Online System
echo ===================================================================
echo.
echo 1. Starting Backend API (Port 8000)...
start "Crowd Intel - Backend API" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo 2. Waiting for Backend to initialize...
timeout /t 3 /nobreak >nul

echo 3. Starting Frontend UI (Port 5173)...
start "Crowd Intel - Frontend Admin UI" cmd /k "cd /d %~dp0frontend && npm run dev"

echo 4. Waiting for Frontend to initialize...
timeout /t 4 /nobreak >nul

echo ===================================================================
echo 5. Generating Secure Public Online HTTPS URL via Cloudflare...
echo ===================================================================
echo.
echo Look for the link ending in .trycloudflare.com below:
echo (Anyone in the world can open this link on phone or laptop!)
echo ===================================================================
echo.

cloudflared tunnel --url http://localhost:5173

pause


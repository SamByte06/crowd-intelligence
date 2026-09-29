@echo off
setlocal

echo ==========================================
echo   AI CROWD INTELLIGENCE - CAMERA START
echo ==========================================
echo.

set EVENT_ID=event_1
set BACKEND_URL=https://crowd-intelligence-back.vercel.app

echo Starting AI engine...
start "AI Crowd Intelligence" cmd /k "python track_webcam.py --event-id %EVENT_ID%"

echo.
echo Waiting for local video server...
timeout /t 5 /nobreak >nul

echo.
echo Starting Cloudflare Quick Tunnel...
echo.

cloudflared tunnel --url http://localhost:8000

pause
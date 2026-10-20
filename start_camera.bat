@echo off
setlocal

echo ==========================================
echo   AI CROWD INTELLIGENCE - CAMERA START
echo ==========================================
echo.

set EVENT_ID=event_1
set BACKEND_URL=https://crowd-intelligence-back.vercel.app

set VIDEO_SOURCE=%1
if "%VIDEO_SOURCE%"=="" (
    echo [SOURCE SELECTION]
    echo Press ENTER for Laptop Webcam (0)
    echo Or paste YouTube link (e.g. https://www.youtube.com/watch?v=...)
    set /p VIDEO_SOURCE="Video Source [default 0]: "
)
if "%VIDEO_SOURCE%"=="" set VIDEO_SOURCE=0

echo.
echo Starting AI engine with source: %VIDEO_SOURCE%
start "AI Crowd Intelligence" cmd /k "python track_webcam.py --event-id %EVENT_ID% --source "%VIDEO_SOURCE%""

echo.
echo Waiting for local video server...
timeout /t 5 /nobreak >nul

echo.
echo Starting Cloudflare Quick Tunnel...
echo.

cloudflared tunnel --url http://localhost:8000

pause
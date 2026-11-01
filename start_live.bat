@echo off
title AI Crowd Intelligence - Live Launcher
color 0A
setlocal enabledelayedexpansion

echo ===================================================================
echo     AI Crowd Intelligence - 1-Click Live Cloudflare Launcher
echo ===================================================================
echo.

:: 1. Check if backend port 8000 is already active
netstat -ano | findstr /R ":8000\>" | findstr /i "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Backend is already running on port 8000.
) else (
    echo [1/2] Starting Python Backend Server (Port 8000)...
    start "Crowd Intelligence - Backend API" cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo [INFO] Waiting for Backend to initialize...
    timeout /t 4 /nobreak >nul
)

echo.
echo ===================================================================
echo [2/2] Starting Cloudflare Tunnel (Target: IPv4 127.0.0.1:8000)...
echo ===================================================================
echo.
echo NOTE: Look for the HTTPS URL below ending in .trycloudflare.com
echo       Copy that URL and paste it in https://understandthecrowd.vercel.app
echo       (Click the STANDBY button on the top-right -> Paste -> Save)
echo.
echo Press Ctrl + C anytime in this window to stop the tunnel.
echo ===================================================================
echo.

:: Use 127.0.0.1 explicitly to prevent Windows IPv6 [::1] connection refused errors
cloudflared tunnel --url http://127.0.0.1:8000

pause

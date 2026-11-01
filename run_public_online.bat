@echo off
title AI Crowd Intelligence - Live Production Launcher
color 0B
setlocal enabledelayedexpansion

echo ===================================================================
echo     AI Crowd Intelligence - Live Production Launcher
echo ===================================================================
echo.

:: 1. Check if backend port 8000 is active
netstat -ano | findstr /R ":8000\>" | findstr /i "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Backend is already running on port 8000.
) else (
    echo [1/2] Starting Python Backend API (Port 8000)...
    start "Crowd Intel - Backend API" cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo [INFO] Waiting for Backend to initialize...
    timeout /t 4 /nobreak >nul
)

echo.
echo ===================================================================
echo [2/2] Generating Secure Public Online HTTPS URL via Cloudflare...
echo ===================================================================
echo.
echo Copy the link ending in .trycloudflare.com below:
echo Paste it into https://understandthecrowd.vercel.app (STANDBY button)
echo ===================================================================
echo.

:: Use 127.0.0.1 explicitly to prevent Windows IPv6 [::1] connection refused errors
cloudflared tunnel --url http://127.0.0.1:8000

pause

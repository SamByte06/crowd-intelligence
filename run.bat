@echo off
setlocal enabledelayedexpansion

echo ===================================================================
echo     AI Crowd Intelligence ^& Entry-Exit Management System
echo ===================================================================
echo.

if "%1"=="backend" goto run_backend
if "%1"=="frontend" goto run_frontend
if "%1"=="seed" goto run_seed
if "%1"=="test" goto run_test

echo Starting both Backend (Port 8000) and Frontend (Port 5173)...
echo.

start "Crowd Intel - Backend API" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

start "Crowd Intel - Frontend Admin UI" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ===================================================================
echo  Services launched in background windows:
echo  - Backend API:       http://localhost:8000
echo  - Swagger Docs:      http://localhost:8000/docs
echo  - Frontend UI:       http://localhost:5173
echo ===================================================================
echo.
pause
exit /b 0

:run_backend
cd /d "%~dp0backend"
echo Starting Backend API...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
exit /b 0

:run_frontend
cd /d "%~dp0frontend"
echo Starting Frontend UI...
npm run dev
exit /b 0

:run_seed
cd /d "%~dp0backend"
echo Seeding demo data...
python -m app.scripts.seed_demo
exit /b 0

:run_test
cd /d "%~dp0backend"
echo Running Backend Tests...
python -m pytest tests -v
exit /b 0

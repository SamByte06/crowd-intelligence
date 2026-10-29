#!/bin/bash
# AI Crowd Intelligence & Entry-Exit Management System
# Cross-platform startup script

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

case "$1" in
  backend)
    echo "Starting Backend API..."
    cd "$DIR/backend"
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ;;
  frontend)
    echo "Starting Frontend UI..."
    cd "$DIR/frontend"
    npm run dev
    ;;
  seed)
    echo "Seeding demo data..."
    cd "$DIR/backend"
    python -m app.scripts.seed_demo
    ;;
  test)
    echo "Running tests..."
    cd "$DIR/backend"
    python -m pytest tests -v
    ;;
  *)
    echo "==================================================================="
    echo "    AI Crowd Intelligence & Entry-Exit Management System"
    echo "==================================================================="
    echo "Starting Backend (Port 8000) and Frontend (Port 5173)..."

    cd "$DIR/backend"
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!

    sleep 2

    cd "$DIR/frontend"
    npm run dev &
    FRONTEND_PID=$!

    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

    echo "Services active:"
    echo " - Backend API:  http://localhost:8000"
    echo " - Frontend UI:  http://localhost:5173"
    echo "Press Ctrl+C to stop both."
    wait
    ;;
esac

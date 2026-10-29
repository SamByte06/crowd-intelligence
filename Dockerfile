# ==============================================================================
# AI Crowd Intelligence — Unified Production Dockerfile (Hugging Face Spaces)
# Builds Frontend & Backend together into a single ultra-light container on Port 7860
# ==============================================================================

# ----------------- Stage 1: Build React Frontend -----------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ----------------- Stage 2: Python Backend Runtime ----------------
FROM python:3.11-slim

WORKDIR /app

# System dependencies for OpenCV, PyTorch, and video codecs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application
COPY backend/ /app/backend/

# Copy built frontend assets directly into backend static directory
COPY --from=frontend-builder /build/dist /app/backend/static/

# Hugging Face Spaces runs as user 1000: create user and grant permissions
RUN useradd -m -u 1000 user && \
    mkdir -p /app/backend/data /app/backend/media_uploads /app/backend/media_cache && \
    chown -R user:user /app

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/app/backend \
    PORT=7860 \
    HOST=0.0.0.0

WORKDIR /app/backend

# Hugging Face Spaces requires exposing Port 7860
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]


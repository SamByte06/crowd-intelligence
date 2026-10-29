#!/usr/bin/env bash
# ==============================================================================
# AI Crowd Intelligence — Production Cloud VPS Deployment Script
# Supports: Ubuntu 20.04+, Debian 11+, Debian 12
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 Starting AI Crowd Intelligence Deployment..."
echo "=================================================================="

# 1. Check Root / Sudo Permissions
if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run as root or with sudo: sudo ./deploy.sh"
  exit 1
fi

# 2. Check and Install Docker if missing
if ! command -v docker &> /dev/null; then
    echo "📦 Docker not found. Installing official Docker Engine..."
    apt-get update -y
    apt-get install -y curl ca-certificates gnupg lsb-release
    
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc 2>/dev/null || \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" 2>/dev/null | tee /etc/apt/sources.list.d/docker.list || true

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    echo "✅ Docker installed successfully."
fi

# 3. Create required runtime directories
echo "📁 Setting up runtime directories..."
mkdir -p backend/media_uploads
mkdir -p backend/data
chmod -R 777 backend/media_uploads backend/data

# 4. Verify YOLO Model Weights exist
if [ ! -f "backend/11s-head.pt" ]; then
    echo "⚠️ Warning: backend/11s-head.pt not found. Checking root..."
    if [ -f "11s-head.pt" ]; then
        cp 11s-head.pt backend/11s-head.pt
    fi
fi

# 5. Build and Launch Containers
echo "🐳 Building and starting production containers..."
docker compose down --remove-orphans || true
docker compose up --build -d

# 6. Verify Healthcheck
echo "⏳ Waiting for services to become healthy..."
sleep 10

if docker ps | grep -q "crowd_backend"; then
    echo "=================================================================="
    echo "🎉 DEPLOYMENT SUCCESSFUL!"
    echo "=================================================================="
    SERVER_IP=$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')
    echo "🌐 Access your system at: http://${SERVER_IP}"
    echo "🔍 API Health Check:     http://${SERVER_IP}/health"
    echo "📊 Container Status:     docker compose ps"
    echo "📜 View Live Logs:       docker compose logs -f"
    echo "=================================================================="
else
    echo "❌ Deployment failed. Check logs using: docker compose logs"
    exit 1
fi


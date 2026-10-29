# AI Crowd Intelligence — Production VPS Deployment Guide

This guide covers deploying the **AI Crowd Intelligence System** to any Linux Cloud VPS (AWS EC2, DigitalOcean, Hetzner, Linode, GCP, or a dedicated on-premise server).

---

## 🖥️ Recommended Server Specifications

| Component | Minimum (1–2 Cameras) | Recommended (4–8 Cameras) | High-Traffic / Dense Crowd |
| :--- | :--- | :--- | :--- |
| **OS** | Ubuntu 22.04 / 24.04 LTS | Ubuntu 22.04 / 24.04 LTS | Ubuntu 22.04 LTS |
| **CPU** | 4 vCPU | 8 vCPU | 8+ vCPU |
| **RAM** | 8 GB | 16 GB | 16–32 GB |
| **GPU** | Optional (runs on CPU) | NVIDIA T4 / RTX 3060 / A10G | NVIDIA RTX 4080 / A10G |
| **Disk** | 40 GB SSD | 80 GB SSD | 150 GB NVMe |

---

## 🚀 Quick Start (Automated 1-Command Deploy)

### Step 1: Connect to your VPS via SSH
```bash
ssh root@YOUR_SERVER_IP
```

### Step 2: Clone your GitHub repository
```bash
git clone https://github.com/SamByte06/crowd-intelligence.git
cd crowd-intelligence
```

### Step 3: Run the deployment script
```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

The script will automatically:
1. Install Docker & Docker Compose if not already installed.
2. Configure directories and permissions.
3. Build the React production frontend with Nginx reverse proxy.
4. Build the FastAPI + YOLO11s-Head background worker container.
5. Launch both services with `restart: always` (auto-restarts on server reboot).
6. Output your live web URL: `http://YOUR_SERVER_IP`.

---

## 🌐 Firewall Configuration

Ensure standard web ports are open on your cloud firewall / security group:
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP Web UI & API
sudo ufw allow 443/tcp   # HTTPS (SSL)
sudo ufw allow 8000/tcp  # Direct API (Optional)
sudo ufw enable
```

*If using AWS EC2 or Google Cloud, also add Inbound Rules for Port 80 and 443 in your Security Group.*

---

## 🔒 Optional: Add Free HTTPS (Let's Encrypt SSL)

If you have a domain pointing to your VPS IP (e.g., `crowd.yourdomain.com`):

```bash
# 1. Install Certbot
sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx

# 2. Stop frontend temporarily to obtain cert
docker compose stop frontend

# 3. Request certificate
sudo certbot certonly --standalone -d crowd.yourdomain.com

# 4. Start frontend again
docker compose start frontend
```

---

## 📹 Connecting Real RTSP CCTV Cameras

In the web interface (**Gate Management** page):
1. Select your Gate.
2. In the **Camera Source** input, enter your camera's RTSP URL:
   ```
   rtsp://username:password@camera_ip:554/stream1
   ```
3. For public cloud VPS accessing local venue cameras:
   * **Option A**: Use a secure VPN (WireGuard or Tailscale) between the venue and VPS.
   * **Option B**: Port-forward RTSP 554 on the venue router with a static IP / DDNS.
   * **Option C**: Stream via Cloudflare Tunnel or WebRTC.

---

## 🛠️ Management Commands

| Action | Command |
| :--- | :--- |
| **View Live Logs** | `docker compose logs -f` |
| **View Backend Logs** | `docker compose logs -f backend` |
| **Check Status** | `docker compose ps` |
| **Restart System** | `docker compose restart` |
| **Stop System** | `docker compose down` |
| **Update to Latest Git Code** | `git pull && docker compose up --build -d` |


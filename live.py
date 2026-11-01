"""
AI Crowd Intelligence — All-in-One Live Launcher.
Starts the FastAPI backend and Cloudflare Tunnel together in a single process.
Automatically extracts the public trycloudflare.com URL and copies it to clipboard.
"""

import sys
import os
import re
import time
import signal
import threading
import subprocess

# Ensure backend folder is in Python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

def copy_to_clipboard(text: str):
    """Copy text to Windows clipboard via PowerShell."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False

def main():
    print("=" * 72)
    print("   AI CROWD INTELLIGENCE — ALL-IN-ONE LIVE LAUNCHER")
    print("=" * 72)
    print("\n[1/3] Initializing FastAPI Backend (Port 8000)...")

    import uvicorn
    from app.main import app

    server_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server to bind
    for _ in range(30):
        if server.started:
            break
        time.sleep(0.1)

    print("[SUCCESS] Backend Server is ONLINE at http://127.0.0.1:8000")
    print("\n[2/3] Connecting to Cloudflare Global Tunnel Network...")

    # Find cloudflared executable
    cloudflared_bin = "cloudflared"
    for candidate in [
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ]:
        if os.path.exists(candidate):
            cloudflared_bin = candidate
            break

    try:
        cf_process = subprocess.Popen(
            [cloudflared_bin, "tunnel", "--url", "http://127.0.0.1:8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        print(f"[ERROR] Failed to start cloudflared: {e}")
        print("Please ensure cloudflared is installed.")
        server.should_exit = True
        sys.exit(1)

    tunnel_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    # Read output to capture the public URL
    start_time = time.time()
    while time.time() - start_time < 20:
        line = cf_process.stdout.readline()
        if not line:
            if cf_process.poll() is not None:
                break
            continue

        match = url_pattern.search(line)
        if match:
            tunnel_url = match.group(0)
            break

    if not tunnel_url:
        print("[WARNING] Tunnel started but URL could not be auto-detected within 20s.")
        print("Listening for stream logs...")
    else:
        copy_success = copy_to_clipboard(tunnel_url)
        print("\n" + "=" * 72)
        print("   >>> YOUR LIVE BACKEND IS READY & ONLINE! <<<")
        print("=" * 72)
        print(f"\n  [+] Public URL:   {tunnel_url}")
        if copy_success:
            print("  [+] Clipboard:    URL COPIED TO CLIPBOARD AUTOMATICALLY!")
        print("\n  [NEXT STEPS]")
        print("  1. Open your frontend: https://understandthecrowd.vercel.app")
        print("  2. Click the 'STANDBY' button in the top-right header.")
        print(f"  3. Paste ({tunnel_url}) and click 'Test & Save Connection'.")
        print("  4. Your Vercel frontend is now live with real-time AI crowd vision!")
        print("\n" + "=" * 72)
        print("  Keep this window open while testing. Press Ctrl + C to stop.")
        print("=" * 72 + "\n")

    # Keep piping logs or stay alive until interrupted
    try:
        while cf_process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down Cloudflare Tunnel and Backend...")
    finally:
        cf_process.terminate()
        try:
            cf_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cf_process.kill()
        server.should_exit = True
        print("[INFO] All services stopped. Goodbye!")

if __name__ == "__main__":
    main()

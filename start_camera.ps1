# =========================================================
# AI CROWD INTELLIGENCE - AUTOMATIC CAMERA STARTUP
# =========================================================

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

$EventId = "event_1"

$BackendUrl = "https://crowd-intelligence-back.vercel.app"

$LocalVideoUrl = "http://localhost:8000"

$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path

$CloudflareOutput = Join-Path $ProjectPath "cloudflare_output.txt"
$CloudflareError = Join-Path $ProjectPath "cloudflare_error.txt"


# ---------------------------------------------------------
# START MESSAGE
# ---------------------------------------------------------

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   AI CROWD INTELLIGENCE CAMERA STARTUP" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Event ID: $EventId" -ForegroundColor Yellow
Write-Host ""


# ---------------------------------------------------------
# CHECK CLOUDFLARED
# ---------------------------------------------------------

$Cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue

if (-not $Cloudflared) {

    Write-Host "ERROR: cloudflared was not found." -ForegroundColor Red

    Write-Host ""
    Write-Host "Make sure cloudflared is installed and available in PATH." -ForegroundColor Red

    pause

    exit
}


# ---------------------------------------------------------
# START AI ENGINE
# ---------------------------------------------------------

Write-Host "Starting AI engine..." -ForegroundColor Green

Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/k python track_webcam.py --event-id $EventId" `
    -WorkingDirectory $ProjectPath


# ---------------------------------------------------------
# WAIT FOR LOCAL VIDEO SERVER
# ---------------------------------------------------------

Write-Host ""
Write-Host "Waiting for local video server..." -ForegroundColor Yellow

$VideoReady = $false

for ($i = 1; $i -le 30; $i++) {

    try {

        $response = Invoke-WebRequest `
            -Uri "$LocalVideoUrl/" `
            -TimeoutSec 2 `
            -UseBasicParsing

        if ($response.StatusCode -eq 200) {

            $VideoReady = $true

            break
        }

    }
    catch {

        Start-Sleep -Seconds 1
    }
}


if (-not $VideoReady) {

    Write-Host ""
    Write-Host "WARNING: Local video server was not detected." -ForegroundColor Red
    Write-Host "Cloudflare will still be started." -ForegroundColor Yellow
}


# ---------------------------------------------------------
# REMOVE OLD CLOUDFLARE LOGS
# ---------------------------------------------------------

if (Test-Path $CloudflareOutput) {
    Remove-Item $CloudflareOutput -Force
}

if (Test-Path $CloudflareError) {
    Remove-Item $CloudflareError -Force
}


# ---------------------------------------------------------
# START CLOUDFLARE QUICK TUNNEL
# ---------------------------------------------------------

Write-Host ""
Write-Host "Starting Cloudflare Quick Tunnel..." -ForegroundColor Green
Write-Host ""

$CloudflareProcess = Start-Process `
    -FilePath "cloudflared.exe" `
    -ArgumentList "tunnel --url http://localhost:8000" `
    -WorkingDirectory $ProjectPath `
    -RedirectStandardOutput $CloudflareOutput `
    -RedirectStandardError $CloudflareError `
    -PassThru `
    -WindowStyle Hidden


# ---------------------------------------------------------
# WAIT FOR CLOUDFLARE URL
# ---------------------------------------------------------

Write-Host "Waiting for Cloudflare public URL..." -ForegroundColor Yellow

$PublicUrl = $null

for ($i = 1; $i -le 60; $i++) {

    Start-Sleep -Seconds 1

    $CombinedOutput = ""

    if (Test-Path $CloudflareOutput) {

        $CombinedOutput += Get-Content `
            $CloudflareOutput `
            -Raw `
            -ErrorAction SilentlyContinue
    }

    if (Test-Path $CloudflareError) {

        $CombinedOutput += Get-Content `
            $CloudflareError `
            -Raw `
            -ErrorAction SilentlyContinue
    }


    $Match = [regex]::Match(
        $CombinedOutput,
        'https://[a-zA-Z0-9-]+\.trycloudflare\.com'
    )


    if ($Match.Success) {

        $PublicUrl = $Match.Value

        break
    }
}


# ---------------------------------------------------------
# CHECK CLOUDFLARE URL
# ---------------------------------------------------------

if (-not $PublicUrl) {

    Write-Host ""
    Write-Host "ERROR: Could not detect Cloudflare URL." -ForegroundColor Red

    Write-Host ""
    Write-Host "Cloudflare output:" -ForegroundColor Yellow

    if (Test-Path $CloudflareOutput) {
        Get-Content $CloudflareOutput
    }

    if (Test-Path $CloudflareError) {
        Get-Content $CloudflareError
    }

    pause

    exit
}


# ---------------------------------------------------------
# CREATE VIDEO URL
# ---------------------------------------------------------

$VideoUrl = "$PublicUrl/video_feed"


Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "       CLOUDFLARE CONNECTION READY" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""

Write-Host "Public video URL:" -ForegroundColor Cyan
Write-Host $VideoUrl -ForegroundColor White

Write-Host ""


# ---------------------------------------------------------
# REGISTER CAMERA STREAM WITH BACKEND
# ---------------------------------------------------------

Write-Host "Registering camera stream with backend..." -ForegroundColor Yellow

$Payload = @{
    event_id = $EventId
    video_url = $VideoUrl
    camera_name = "Camera 01 - Main Entrance"
    status = "LIVE"
} | ConvertTo-Json


try {

    $Result = Invoke-RestMethod `
        -Uri "$BackendUrl/api/camera-stream" `
        -Method POST `
        -ContentType "application/json" `
        -Body $Payload


    if ($Result.success) {

        Write-Host ""
        Write-Host "=============================================" -ForegroundColor Green
        Write-Host "        CAMERA REGISTERED SUCCESSFULLY" -ForegroundColor Green
        Write-Host "=============================================" -ForegroundColor Green
        Write-Host ""

        Write-Host "Event: $EventId" -ForegroundColor Cyan

        Write-Host ""
        Write-Host "Live video:" -ForegroundColor Cyan
        Write-Host $VideoUrl -ForegroundColor White

        Write-Host ""
        Write-Host "The backend now knows the current Cloudflare URL." -ForegroundColor Green
        Write-Host "No Git push is required when this URL changes." -ForegroundColor Green

    }
    else {

        Write-Host ""
        Write-Host "ERROR: Backend rejected camera registration." -ForegroundColor Red

        $Result | ConvertTo-Json -Depth 10
    }

}
catch {

    Write-Host ""
    Write-Host "ERROR: Could not register camera with backend." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}


# ---------------------------------------------------------
# KEEP SCRIPT RUNNING
# ---------------------------------------------------------

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "AI CAMERA IS RUNNING" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "AI engine is running in another window." -ForegroundColor Gray
Write-Host "Cloudflare tunnel is running in the background." -ForegroundColor Gray

Write-Host ""
Write-Host "Press CTRL+C here only if you want to stop the startup script." -ForegroundColor Yellow
Write-Host ""

while ($true) {

    Start-Sleep -Seconds 10

    if ($CloudflareProcess.HasExited) {

        Write-Host ""
        Write-Host "WARNING: Cloudflare tunnel has stopped." -ForegroundColor Red

        break
    }
}
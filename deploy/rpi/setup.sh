#!/bin/bash
# ==========================================
# RPi 5 Smart Home Setup Script
# ==========================================
# Run this once on a fresh Raspberry Pi OS (64-bit Bookworm).
#
# Usage:
#   git clone <repo-url> ~/google_claude
#   cd ~/google_claude
#   bash deploy/rpi/setup.sh
#
# After setup:
#   1. Copy .env from dev machine:  scp .env pi@rpi:~/google_claude/.env
#   2. Edit .env: set DEPLOYMENT_PROFILE=rpi-home, ENABLE_WAKE_WORD=true
#   3. Copy OAuth token:  scp ~/.google_workspace_adk/tokens.json pi@rpi:~/.google_workspace_adk/
#   4. Enable services:   sudo systemctl enable --now adk-web adk-telegram adk-wakeword adk-scheduler

set -euo pipefail

echo "=== RPi 5 Smart Home Setup ==="

# System dependencies
echo "[1/5] Installing system packages..."
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-pip \
    portaudio19-dev \
    ffmpeg \
    libopenblas-dev \
    git \
    alsa-utils \
    mosquitto-clients

# Create venv
echo "[2/5] Creating Python virtual environment..."
cd ~/google_claude
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
echo "[3/5] Installing Python dependencies (this takes a few minutes on RPi)..."
pip install --upgrade pip wheel setuptools
pip install -r requirements-rpi.txt

# Create token directory
echo "[4/5] Preparing directories..."
mkdir -p ~/.google_workspace_adk
mkdir -p ~/google_claude/logs

# Install systemd services
echo "[5/5] Installing systemd services..."
sudo cp deploy/rpi/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to ~/google_claude/.env"
echo "     Set: DEPLOYMENT_PROFILE=rpi-home"
echo "     Set: ENABLE_WAKE_WORD=true"
echo "  2. Copy OAuth token:"
echo "     scp ~/.google_workspace_adk/tokens.json pi@$(hostname):~/.google_workspace_adk/"
echo "  3. Verify MQTT broker is reachable:"
echo "     ping \$(grep MQTT_BROKER .env | cut -d= -f2)"
echo "  4. Test mic HAT:"
echo "     arecord -d 3 -f S16_LE -r 16000 /tmp/test.wav && aplay /tmp/test.wav"
echo "  5. Run Pi smoke check:"
echo "     .venv/bin/python scripts/rpi_smoke_check.py"
echo "  6. Start services:"
echo "     sudo systemctl enable --now adk-web adk-telegram adk-wakeword adk-scheduler"
echo "  7. Check status:"
echo "     sudo systemctl status adk-web adk-telegram adk-wakeword adk-scheduler"

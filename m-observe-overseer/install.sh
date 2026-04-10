#!/bin/bash
set -e

# ═══════════════════════════════════════════
#  M-OBSERVE Host — Install Script
#  Für Ubuntu / Debian / Raspbian
# ═══════════════════════════════════════════

INSTALL_DIR="/opt/m-observe"
SERVICE_NAME="m-observe-host"
CURRENT_USER=$(whoami)

echo ""
echo "  ┌──────────────────────────────────┐"
echo "  │   M-OBSERVE Host Installation    │"
echo "  └──────────────────────────────────┘"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo bash install.sh"
    exit 1
fi

# Install dependencies
echo "[1/5] System-Pakete installieren..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip >/dev/null 2>&1
echo "  ✓ Python installiert"

# Copy files
echo "[2/5] Dateien kopieren..."
mkdir -p "$INSTALL_DIR"
cp -r backend "$INSTALL_DIR/"
cp -r frontend "$INSTALL_DIR/"
echo "  ✓ Dateien kopiert nach $INSTALL_DIR"

# Create venv & install requirements
echo "[3/5] Python-Umgebung einrichten..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/backend/requirements.txt"
echo "  ✓ Abhängigkeiten installiert"

# Create systemd service
echo "[4/5] Systemd-Service einrichten..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=M-OBSERVE Host (Backend + WebUI)
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}/backend
ExecStart=${INSTALL_DIR}/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 3501
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl start ${SERVICE_NAME}
echo "  ✓ Service gestartet"

# Get IP
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "[5/5] Fertig!"
echo ""
echo "  ┌──────────────────────────────────────────────────┐"
echo "  │  M-OBSERVE läuft!                                │"
echo "  │                                                  │"
echo "  │  WebUI:  http://${IP}:3501                  │"
echo "  │                                                  │"
echo "  │  Öffne die URL im Browser und richte das         │"
echo "  │  Master-Passwort ein.                            │"
echo "  │                                                  │"
echo "  │  Service-Befehle:                                │"
echo "  │    sudo systemctl status ${SERVICE_NAME}         │"
echo "  │    sudo systemctl restart ${SERVICE_NAME}        │"
echo "  │    sudo journalctl -u ${SERVICE_NAME} -f         │"
echo "  └──────────────────────────────────────────────────┘"
echo ""

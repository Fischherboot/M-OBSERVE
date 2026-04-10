#!/usr/bin/env bash
# ============================================================================
# M-OBSERVE Minimal Client — Install Script (Debian / Ubuntu)
#
# Usage:  sudo bash install.sh
#
# Lightweight client for containers & VMs — telemetry only, no shell/logs.
# ============================================================================

set -e

INSTALL_DIR="/opt/m-observe-client"
SERVICE_NAME="m-observe-client"
SERVICE_USER="m-observe"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo bash install.sh)"
    exit 1
fi

echo ""
echo "=============================================="
echo "  M-OBSERVE Minimal Client Installer"
echo "=============================================="
echo ""

# 1. System packages
echo "[1/6] Installing system dependencies ..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip sudo > /dev/null 2>&1 || true
echo "      Done."

# 2. System user
echo "[2/6] Creating system user '${SERVICE_USER}' ..."
if id "${SERVICE_USER}" &>/dev/null; then
    echo "      User already exists, skipping."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "      Created."
fi

# 3. Copy files
echo "[3/6] Installing client to ${INSTALL_DIR} ..."
mkdir -p "${INSTALL_DIR}"
cp "${SCRIPT_DIR}/client.py" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/collectors" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/setup.py" "${INSTALL_DIR}/"

if [ -f "${INSTALL_DIR}/config.json" ]; then
    echo "      Existing config.json preserved."
fi
echo "      Files copied."

# 4. Python venv
echo "[4/6] Setting up Python virtual environment ..."
if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
echo "      Dependencies installed."

# 5. Interactive setup
echo "[5/6] Running interactive setup ..."
echo ""
"${INSTALL_DIR}/venv/bin/python3" "${INSTALL_DIR}/setup.py"

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 640 "${INSTALL_DIR}/config.json"

# Sudoers — minimal: only reboot, shutdown, apt
cat > /etc/sudoers.d/m-observe-client << 'SUDOERS'
# M-OBSERVE Minimal Client
m-observe ALL=(ALL) NOPASSWD: /sbin/reboot
m-observe ALL=(ALL) NOPASSWD: /sbin/shutdown
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl reboot
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl poweroff
m-observe ALL=(ALL) NOPASSWD: /usr/bin/systemctl reboot
m-observe ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt update
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt upgrade -y
SUDOERS
chmod 440 /etc/sudoers.d/m-observe-client
if visudo -cf /etc/sudoers.d/m-observe-client > /dev/null 2>&1; then
    echo "      Sudoers rules installed."
else
    echo "      WARNING: sudoers validation failed."
fi

# 6. systemd service
echo "[6/6] Installing systemd service ..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=M-OBSERVE Minimal Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/client.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "      Service '${SERVICE_NAME}' enabled and started."

echo ""
echo "=============================================="
echo "  Minimal Client installation complete!"
echo ""
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Service:      ${SERVICE_NAME}"
echo ""
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "=============================================="
echo ""

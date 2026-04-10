#!/usr/bin/env bash
# ============================================================================
# M-OBSERVE Client — Install Script (Debian / Ubuntu / Raspbian)
#
# Usage:  sudo bash install.sh
#
# What it does:
#   1. Installs system dependencies (python3, pip, smartmontools)
#   2. Creates m-observe system user
#   3. Copies client to /opt/m-observe-client/
#   4. Creates Python venv & installs requirements
#   5. Runs interactive setup (config.json)
#   6. Installs sudoers rules for passwordless system commands
#   7. Installs & enables systemd service (m-observe-client)
# ============================================================================

set -e

INSTALL_DIR="/opt/m-observe-client"
SERVICE_NAME="m-observe-client"
SERVICE_USER="m-observe"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo bash install.sh)"
    exit 1
fi

echo ""
echo "=============================================="
echo "  M-OBSERVE Client Installer"
echo "=============================================="
echo ""

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
echo "[1/7] Installing system dependencies ..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip sudo smartmontools util-linux > /dev/null 2>&1 || true
echo "      Done."

# ---------------------------------------------------------------------------
# 2. System user
# ---------------------------------------------------------------------------
echo "[2/7] Creating system user '${SERVICE_USER}' ..."
if id "${SERVICE_USER}" &>/dev/null; then
    echo "      User already exists, skipping."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "      Created."
fi

# ---------------------------------------------------------------------------
# 3. Copy files
# ---------------------------------------------------------------------------
echo "[3/7] Installing client to ${INSTALL_DIR} ..."
mkdir -p "${INSTALL_DIR}"
# Copy all client files
cp -r "${SCRIPT_DIR}/client.py" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/collectors" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/actions" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/setup.py" "${INSTALL_DIR}/"

# Preserve existing config if present
if [ -f "${INSTALL_DIR}/config.json" ]; then
    echo "      Existing config.json preserved."
fi
echo "      Files copied."

# ---------------------------------------------------------------------------
# 4. Python venv + dependencies
# ---------------------------------------------------------------------------
echo "[4/7] Setting up Python virtual environment ..."
if [ ! -d "${INSTALL_DIR}/venv" ]; then
    python3 -m venv "${INSTALL_DIR}/venv"
fi
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
# pynvml is optional — only works on NVIDIA GPU systems
"${INSTALL_DIR}/venv/bin/pip" install --quiet pynvml 2>/dev/null || echo "      (pynvml skipped — no NVIDIA GPU detected, that's fine)"
echo "      Dependencies installed."

# ---------------------------------------------------------------------------
# 5. Interactive setup
# ---------------------------------------------------------------------------
echo "[5/7] Running interactive setup ..."
echo ""
"${INSTALL_DIR}/venv/bin/python3" "${INSTALL_DIR}/setup.py"

# Set ownership
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
# config.json must be readable
chmod 640 "${INSTALL_DIR}/config.json"

# ---------------------------------------------------------------------------
# 6. Sudoers
# ---------------------------------------------------------------------------
echo "[6/7] Installing sudoers rules ..."
cat > /etc/sudoers.d/m-observe-client << 'SUDOERS'
# M-OBSERVE Client — passwordless system commands
m-observe ALL=(ALL) NOPASSWD: /sbin/reboot
m-observe ALL=(ALL) NOPASSWD: /sbin/shutdown
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl reboot
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl poweroff
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl restart *
m-observe ALL=(ALL) NOPASSWD: /usr/bin/systemctl reboot
m-observe ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
m-observe ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart *
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt update
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt upgrade -y
m-observe ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
m-observe ALL=(ALL) NOPASSWD: /usr/bin/smartctl
m-observe ALL=(ALL) NOPASSWD: /usr/bin/loginctl terminate-session *
m-observe ALL=(ALL) NOPASSWD: /usr/bin/pkill -u *
m-observe ALL=(ALL) NOPASSWD: /usr/bin/journalctl *
SUDOERS
chmod 440 /etc/sudoers.d/m-observe-client
# Validate
if visudo -cf /etc/sudoers.d/m-observe-client > /dev/null 2>&1; then
    echo "      Sudoers rules installed and validated."
else
    echo "      WARNING: sudoers validation failed. Check /etc/sudoers.d/m-observe-client"
fi

# ---------------------------------------------------------------------------
# 7. systemd service
# ---------------------------------------------------------------------------
echo "[7/7] Installing systemd service ..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=M-OBSERVE Client
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

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  Installation complete!"
echo ""
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Service:      ${SERVICE_NAME}"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status ${SERVICE_NAME}"
echo "    sudo journalctl -u ${SERVICE_NAME} -f"
echo "    sudo systemctl restart ${SERVICE_NAME}"
echo ""
echo "  To reconfigure:"
echo "    sudo ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/setup.py"
echo "    sudo systemctl restart ${SERVICE_NAME}"
echo "=============================================="
echo ""

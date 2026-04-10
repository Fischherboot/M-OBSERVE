#!/usr/bin/env python3
"""M-OBSERVE Client — Interactive Setup.

Run: sudo python3 setup.py
Creates config.json, installs systemd service, and sets up sudoers.
"""

import json
import os
import platform
import socket
import sys
import uuid


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_os_string() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.platform()


def main():
    print()
    print("=" * 50)
    print("  M-OBSERVE Client Setup")
    print("=" * 50)
    print()

    hostname = socket.gethostname()
    local_ip = get_local_ip()
    os_str = get_os_string()

    print(f"  Hostname:  {hostname}")
    print(f"  OS:        {os_str}")
    print(f"  IP:        {local_ip}")
    print()

    # Load existing config if present
    existing = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                existing = json.load(f)
            print("  Existing config found. Press Enter to keep current values.")
            print()
        except Exception:
            pass

    # Client name
    default_name = existing.get("client_name", hostname.replace("-", " ").title())
    client_name = input(f"  Gerätename [{default_name}]: ").strip()
    if not client_name:
        client_name = default_name

    # Overseer IP
    default_ip = ""
    if existing.get("backend_url"):
        # Extract IP from ws://IP:PORT/ws/client
        try:
            default_ip = existing["backend_url"].split("//")[1].split(":")[0]
        except Exception:
            pass
    overseer_ip = input(f"  Overseer IP/Hostname [{default_ip}]: ").strip()
    if not overseer_ip:
        if default_ip:
            overseer_ip = default_ip
        else:
            print("  ERROR: Overseer IP is required.")
            sys.exit(1)

    # Port
    default_port = "3501"
    if existing.get("backend_url"):
        try:
            default_port = existing["backend_url"].split(":")[2].split("/")[0]
        except Exception:
            pass
    port = input(f"  Overseer Port [{default_port}]: ").strip()
    if not port:
        port = default_port

    # API Key
    default_key = existing.get("api_key", "")
    prompt = f"  API-Key [{default_key}]: " if default_key else "  API-Key: "
    api_key = input(prompt).strip()
    if not api_key:
        if default_key:
            api_key = default_key
        else:
            print("  ERROR: API-Key is required.")
            sys.exit(1)

    # Client ID: hostname + random suffix
    client_id = existing.get("client_id", f"{hostname}-{uuid.uuid4().hex[:12]}")

    backend_url = f"ws://{overseer_ip}:{port}/ws/client"

    config = {
        "client_id": client_id,
        "client_name": client_name,
        "backend_url": backend_url,
        "api_key": api_key,
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

    print()
    print(f"  Config saved to {CONFIG_PATH}")
    print(f"  Client ID:   {client_id}")
    print(f"  Backend URL: {backend_url}")
    print()
    print("  Setup complete.")
    print()


if __name__ == "__main__":
    main()

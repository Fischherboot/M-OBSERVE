#!/usr/bin/env python3
"""M-OBSERVE Minimal Client — lightweight container/VM monitor."""

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import sys
import time

import psutil
import websockets

from collectors import cpu, ram, network, temperatures
from collectors import updates as upd_collector

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("m-observe")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

MINIMAL_NOTICE = (
    "Dies ist ein Minimal Client, er ist nur zum Überwachen gedacht.\n"
    "Höchst wahrscheinlich ist dies keine physische Host-Maschine "
    "sondern ein Container oder eine VM."
)

config: dict = {}
_shutdown_event = asyncio.Event()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config():
    global config
    if not os.path.exists(CONFIG_PATH):
        log.error(f"Config not found at {CONFIG_PATH}. Run setup.py first.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    for key in ("client_id", "client_name", "backend_url", "api_key"):
        if key not in config:
            log.error(f"Missing '{key}' in config.json. Re-run setup.py.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# System info helpers
# ---------------------------------------------------------------------------
def get_os_string() -> str:
    try:
        import distro
        name = distro.name(pretty=True)
        if name:
            return f"[MINIMAL CLIENT] {name}"
    except ImportError:
        pass
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return "[MINIMAL CLIENT] " + line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return f"[MINIMAL CLIENT] {platform.platform()}"


def get_platform() -> str:
    s = platform.system().lower()
    if s == "linux":
        return "linux"
    elif s == "freebsd":
        return "freebsd"
    elif s == "windows":
        return "windows"
    return s


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Telemetry assembly
# ---------------------------------------------------------------------------
def build_telemetry() -> dict:
    payload = {
        "type": "telemetry",
        "client_id": config["client_id"],
        "client_name": config["client_name"],
        "timestamp": int(time.time()),
        "os": get_os_string(),
        "platform": get_platform(),
        "hostname": socket.gethostname(),
        "ip": get_local_ip(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "plaintext": MINIMAL_NOTICE,
    }

    payload.update(cpu.collect())
    payload.update(ram.collect())
    payload.update(network.collect())
    payload.update(temperatures.collect())

    # No disks, no GPUs
    payload["disks"] = []
    payload["gpus"] = []
    payload["users"] = []

    # Load average
    try:
        payload["load_avg"] = list(os.getloadavg())
    except (OSError, AttributeError):
        payload["load_avg"] = None

    return payload


# ---------------------------------------------------------------------------
# Auth message
# ---------------------------------------------------------------------------
def build_auth() -> dict:
    return {
        "api_key": config["api_key"],
        "client_id": config["client_id"],
        "client_name": config["client_name"],
        "hostname": socket.gethostname(),
        "os": get_os_string(),
        "platform": get_platform(),
        "ip": get_local_ip(),
    }


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------
async def handle_message(ws, msg: dict):
    msg_type = msg.get("type", "")
    cid = config["client_id"]

    if msg_type == "request":
        req = msg.get("request", "")

        if req == "updates":
            data = await asyncio.get_event_loop().run_in_executor(
                None, upd_collector.collect
            )
            await ws.send(json.dumps({
                "type": "updates",
                "client_id": cid,
                "data": data,
            }))

        elif req == "processes":
            await ws.send(json.dumps({
                "type": "processes",
                "client_id": cid,
                "data": [],
            }))

        elif req == "services":
            await ws.send(json.dumps({
                "type": "services",
                "client_id": cid,
                "data": [],
            }))

        elif req == "disk_check":
            await ws.send(json.dumps({
                "type": "smart",
                "client_id": cid,
                "data": [],
            }))

        elif req == "logs":
            await ws.send(json.dumps({
                "type": "logs_line",
                "client_id": cid,
                "data": "Dies ist ein Minimal Client. Log-Streaming ist nicht verfügbar.",
            }))

        elif req == "shell":
            await ws.send(json.dumps({
                "type": "shell_output",
                "client_id": cid,
                "data": "Dies ist ein Minimal Client. Die Shell ist nicht verfügbar.\r\n",
            }))

    elif msg_type == "action":
        action = msg.get("action", "")
        params = msg.get("params", {})
        result = "unknown action"

        if action == "reboot":
            result = _do_reboot()
        elif action == "shutdown":
            result = _do_shutdown()
        elif action == "update_packages":
            result = await asyncio.get_event_loop().run_in_executor(
                None, _do_update_packages
            )
        else:
            result = "not supported on minimal client"

        await ws.send(json.dumps({
            "type": "action_result",
            "client_id": cid,
            "action": action,
            "result": result,
        }))

    elif msg_type == "shell_input":
        # Ignore all shell input, just echo the notice again
        await ws.send(json.dumps({
            "type": "shell_output",
            "client_id": cid,
            "data": "Dies ist ein Minimal Client. Die Shell ist nicht verfügbar.\r\n",
        }))

    elif msg_type == "stop_stream":
        pass  # Nothing to stop


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------
def _do_reboot() -> str:
    import subprocess
    try:
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        return "ok"
    except Exception as e:
        return f"error: {e}"


def _do_shutdown() -> str:
    import subprocess
    try:
        subprocess.Popen(["sudo", "systemctl", "poweroff"])
        return "ok"
    except Exception as e:
        return f"error: {e}"


def _do_update_packages() -> str:
    import subprocess
    try:
        subprocess.Popen(
            ["sudo", "apt", "update"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).wait(timeout=120)
        subprocess.Popen(
            ["sudo", "apt", "upgrade", "-y"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).wait(timeout=600)
        return "ok"
    except Exception as e:
        return f"error: {e}"


# ---------------------------------------------------------------------------
# Main connection loop
# ---------------------------------------------------------------------------
async def run():
    interval = config.get("telemetry_interval", 3)
    backoff = 1

    while not _shutdown_event.is_set():
        try:
            url = config["backend_url"]
            log.info(f"Connecting to {url} ...")
            async with websockets.connect(
                url, ping_interval=20, ping_timeout=10
            ) as ws:
                await ws.send(json.dumps(build_auth()))
                log.info("Authenticated. Streaming telemetry.")
                backoff = 1

                psutil.cpu_percent(interval=0, percpu=True)

                async def telemetry_loop():
                    while True:
                        try:
                            payload = await asyncio.get_event_loop().run_in_executor(
                                None, build_telemetry
                            )
                            await ws.send(json.dumps(payload))
                        except websockets.ConnectionClosed:
                            return
                        await asyncio.sleep(interval)

                async def receive_loop():
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            await handle_message(ws, msg)
                        except json.JSONDecodeError:
                            log.warning("Received invalid JSON from host.")

                await asyncio.gather(telemetry_loop(), receive_loop())

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log.warning(f"Connection lost/refused: {e}. Reconnecting in {backoff}s ...")
        except Exception as e:
            log.error(f"Unexpected error: {e}. Reconnecting in {backoff}s ...")

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    load_config()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal_handler():
        log.info("Shutdown signal received.")
        _shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()

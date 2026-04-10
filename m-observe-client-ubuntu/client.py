#!/usr/bin/env python3
"""M-OBSERVE Client — connects to the Overseer and streams telemetry."""

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
import uuid

import psutil
import websockets

from collectors import cpu, ram, disk, gpu, network, temperatures
from collectors import processes as proc_collector
from collectors import users as user_collector
from collectors import services as svc_collector
from collectors import updates as upd_collector
from actions.handlers import (
    handle_reboot, handle_shutdown, handle_kick_user,
    handle_update_packages, handle_service_restart,
    handle_disk_check, ShellSession, LogStreamer,
)

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

config: dict = {}
shell_session: ShellSession | None = None
log_streamer: LogStreamer | None = None
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
    """Return a human-readable OS string."""
    try:
        import distro
        name = distro.name(pretty=True)
        if name:
            return name
    except ImportError:
        pass
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return platform.platform()


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
    """Best-effort local IP detection."""
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
    }
    # Merge collector outputs
    payload.update(cpu.collect())
    payload.update(ram.collect())
    payload.update(disk.collect())
    payload.update(gpu.collect())
    payload.update(network.collect())
    payload.update(temperatures.collect())

    # Load average
    try:
        payload["load_avg"] = list(os.getloadavg())
    except (OSError, AttributeError):
        payload["load_avg"] = None

    # Users
    payload["users"] = user_collector.collect()

    # Plaintext (optional custom hook)
    plaintext_path = os.path.join(BASE_DIR, "plaintext.sh")
    if os.path.isfile(plaintext_path) and os.access(plaintext_path, os.X_OK):
        try:
            import subprocess
            result = subprocess.run(
                [plaintext_path], capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                payload["plaintext"] = result.stdout.strip()
        except Exception:
            pass

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
    global shell_session, log_streamer

    msg_type = msg.get("type", "")

    # --- On-demand data requests ---
    if msg_type == "request":
        req = msg.get("request", "")
        if req == "processes":
            await ws.send(json.dumps({
                "type": "processes",
                "client_id": config["client_id"],
                "data": proc_collector.collect(),
            }))
        elif req == "services":
            await ws.send(json.dumps({
                "type": "services",
                "client_id": config["client_id"],
                "data": svc_collector.collect(),
            }))
        elif req == "updates":
            data = await asyncio.get_event_loop().run_in_executor(None, upd_collector.collect)
            await ws.send(json.dumps({
                "type": "updates",
                "client_id": config["client_id"],
                "data": data,
            }))
        elif req == "disk_check":
            data = await asyncio.get_event_loop().run_in_executor(None, handle_disk_check)
            await ws.send(json.dumps({
                "type": "smart",
                "client_id": config["client_id"],
                "data": data,
            }))
        elif req == "logs":
            # Start log streaming
            if log_streamer:
                log_streamer.stop()
            log_streamer = LogStreamer()
            log_streamer.start()
            asyncio.ensure_future(_stream_logs(ws))
        elif req == "shell":
            # Start shell session
            if shell_session:
                shell_session.stop()
            shell_session = ShellSession()
            shell_session.start()
            asyncio.ensure_future(_stream_shell(ws))

    # --- Action commands ---
    elif msg_type == "action":
        action = msg.get("action", "")
        params = msg.get("params", {})
        result = "unknown action"

        if action == "reboot":
            result = await asyncio.get_event_loop().run_in_executor(None, handle_reboot)
        elif action == "shutdown":
            result = await asyncio.get_event_loop().run_in_executor(None, handle_shutdown)
        elif action == "kick_user":
            result = await asyncio.get_event_loop().run_in_executor(None, handle_kick_user, params)
        elif action == "update_packages":
            result = await asyncio.get_event_loop().run_in_executor(None, handle_update_packages)
        elif action == "service_restart":
            result = await asyncio.get_event_loop().run_in_executor(None, handle_service_restart, params)
        elif action == "disk_check":
            data = await asyncio.get_event_loop().run_in_executor(None, handle_disk_check)
            await ws.send(json.dumps({
                "type": "smart",
                "client_id": config["client_id"],
                "data": data,
            }))
            return

        await ws.send(json.dumps({
            "type": "action_result",
            "client_id": config["client_id"],
            "action": action,
            "result": result,
        }))

    # --- Shell input ---
    elif msg_type == "shell_input":
        if shell_session and shell_session.running:
            data = msg.get("data", "")
            shell_session.write(data)

    # --- Stop streams ---
    elif msg_type == "stop_stream":
        stream = msg.get("stream", "")
        if stream == "logs" and log_streamer:
            log_streamer.stop()
            log_streamer = None
        elif stream == "shell" and shell_session:
            shell_session.stop()
            shell_session = None


async def _stream_logs(ws):
    """Read journalctl output and stream to host."""
    global log_streamer
    streamer = log_streamer
    if not streamer or not streamer.process:
        return
    loop = asyncio.get_event_loop()
    try:
        while streamer.process and streamer.process.poll() is None:
            line = await loop.run_in_executor(None, streamer.process.stdout.readline)
            if not line:
                break
            try:
                await ws.send(json.dumps({
                    "type": "logs_line",
                    "client_id": config["client_id"],
                    "data": line.rstrip("\n"),
                }))
            except websockets.ConnectionClosed:
                break
    except Exception:
        pass


async def _stream_shell(ws):
    """Read PTY output and stream to host."""
    global shell_session
    session = shell_session
    if not session or not session.running:
        return
    loop = asyncio.get_event_loop()
    try:
        while session.running:
            data = await loop.run_in_executor(None, session.read, 0.1)
            if data:
                try:
                    await ws.send(json.dumps({
                        "type": "shell_output",
                        "client_id": config["client_id"],
                        "data": data,
                    }))
                except websockets.ConnectionClosed:
                    break
            else:
                await asyncio.sleep(0.05)
    except Exception:
        pass


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
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                # Authenticate
                await ws.send(json.dumps(build_auth()))
                log.info("Authenticated. Streaming telemetry.")
                backoff = 1  # reset on success

                # Kick off a psutil cpu_percent warm-up
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

        # Cleanup streams on disconnect
        global shell_session, log_streamer
        if shell_session:
            shell_session.stop()
            shell_session = None
        if log_streamer:
            log_streamer.stop()
            log_streamer = None

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

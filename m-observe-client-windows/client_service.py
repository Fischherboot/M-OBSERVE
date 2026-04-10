"""
M-OBSERVE Client Service for Windows
Runs as a Windows Service — connects to the Overseer via WebSocket,
sends telemetry, handles commands (reboot, shutdown, shell, etc.).
"""

import sys
import os
import json
import time
import uuid
import socket
import platform
import asyncio
import threading
import subprocess
import logging
import ctypes
from pathlib import Path

# Windows service support
import servicemanager
import win32serviceutil
import win32service
import win32event

import psutil
import websockets

# Optional GPU support
try:
    import pynvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
INSTALL_DIR = Path(os.environ.get("M_OBSERVE_DIR", r"C:\Program Files\M-OBSERVE Client"))
CONFIG_PATH = INSTALL_DIR / "config.json"
LOG_PATH = INSTALL_DIR / "client.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging():
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Telemetry collection
# ---------------------------------------------------------------------------
def get_os_string() -> str:
    ver = platform.version()
    release = platform.release()
    edition = ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        edition = winreg.QueryValueEx(key, "ProductName")[0]
        winreg.CloseKey(key)
    except Exception:
        edition = f"Windows {release}"
    return edition


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def collect_cpu() -> dict:
    freq = psutil.cpu_freq()
    return {
        "usage_percent": psutil.cpu_percent(interval=0),
        "per_core": psutil.cpu_percent(interval=0, percpu=True),
        "model": platform.processor() or "Unknown",
        "cores": psutil.cpu_count(logical=True),
        "freq_mhz": int(freq.current) if freq else 0,
    }


def collect_ram() -> dict:
    vm = psutil.virtual_memory()
    return {
        "total_mb": round(vm.total / 1048576),
        "used_mb": round(vm.used / 1048576),
        "percent": vm.percent,
    }


def collect_disks() -> list:
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts.lower() or part.fstype == "":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "total_gb": round(usage.total / 1073741824, 1),
                "used_gb": round(usage.used / 1073741824, 1),
                "percent": round(usage.percent),
                "fs_type": part.fstype,
            })
        except PermissionError:
            pass
    return disks


def collect_gpus() -> list:
    gpus = []
    if not HAS_NVML:
        return gpus
    try:
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            gpu = {"name": name}
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                gpu["usage_percent"] = util.gpu
                gpu["encoder_percent"] = 0
                gpu["decoder_percent"] = 0
            except Exception:
                pass
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                gpu["vram_used_mb"] = round(mem.used / 1048576)
                gpu["vram_total_mb"] = round(mem.total / 1048576)
            except Exception:
                pass
            try:
                gpu["temp_c"] = pynvml.nvmlDeviceGetTemperature(h, 0)
            except Exception:
                pass
            try:
                gpu["power_draw_w"] = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000)
            except Exception:
                pass
            try:
                gpu["power_limit_w"] = round(pynvml.nvmlDeviceGetPowerManagementLimit(h) / 1000)
            except Exception:
                pass
            try:
                gpu["fan_speed_percent"] = pynvml.nvmlDeviceGetFanSpeed(h)
            except Exception:
                pass
            try:
                gpu["driver"] = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(gpu["driver"], bytes):
                    gpu["driver"] = gpu["driver"].decode()
            except Exception:
                pass
            try:
                cuda_ver = pynvml.nvmlSystemGetCudaDriverVersion_v2()
                gpu["cuda_version"] = f"{cuda_ver // 1000}.{(cuda_ver % 1000) // 10}"
            except Exception:
                pass
            gpus.append(gpu)
        pynvml.nvmlShutdown()
    except Exception as e:
        logging.debug(f"NVML error: {e}")
    return gpus


def collect_temperatures() -> dict:
    temps = {}
    # psutil on Windows often has no sensor data, but try
    try:
        sensor_temps = psutil.sensors_temperatures()
        if sensor_temps:
            for chip, entries in sensor_temps.items():
                for entry in entries:
                    label = entry.label or chip
                    label = label.lower().replace(" ", "_")
                    if entry.high or entry.critical:
                        temps[label] = {
                            "current": round(entry.current),
                            "high": round(entry.high) if entry.high else None,
                            "critical": round(entry.critical) if entry.critical else None,
                        }
                    else:
                        temps[label] = round(entry.current)
    except Exception:
        pass
    # GPU temps from pynvml (already in gpus, but also add here)
    if HAS_NVML:
        try:
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                try:
                    temps[f"gpu{i}"] = pynvml.nvmlDeviceGetTemperature(h, 0)
                except Exception:
                    pass
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return temps


def collect_network() -> dict:
    interfaces = []
    counters = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()
    for name, addr_list in addrs.items():
        ip = None
        for a in addr_list:
            if a.family == socket.AF_INET:
                ip = a.address
                break
        if ip and not ip.startswith("127."):
            c = counters.get(name)
            interfaces.append({
                "name": name,
                "ip": ip,
                "rx_bytes": c.bytes_recv if c else 0,
                "tx_bytes": c.bytes_sent if c else 0,
            })
    return {"interfaces": interfaces}


def collect_users() -> list:
    users = []
    for u in psutil.users():
        users.append({
            "name": u.name,
            "terminal": u.terminal or "",
            "host": u.host or "",
            "started": time.strftime("%H:%M", time.localtime(u.started)),
        })
    return users


def build_telemetry(cfg: dict) -> dict:
    return {
        "type": "telemetry",
        "client_id": cfg["client_id"],
        "client_name": cfg["client_name"],
        "timestamp": int(time.time()),
        "os": get_os_string(),
        "platform": "windows",
        "hostname": socket.gethostname(),
        "ip": get_local_ip(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu": collect_cpu(),
        "ram": collect_ram(),
        "disks": collect_disks(),
        "gpus": collect_gpus(),
        "temperatures": collect_temperatures(),
        "network": collect_network(),
        "load_avg": None,
        "users": collect_users(),
    }

# ---------------------------------------------------------------------------
# Process list
# ---------------------------------------------------------------------------
def collect_processes() -> list:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username", "create_time"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "cpu_percent": round(info.get("cpu_percent") or 0, 1),
                "ram_percent": round(info.get("memory_percent") or 0, 1),
                "user": info.get("username") or "",
                "started": time.strftime("%Y-%m-%d %H:%M", time.localtime(info["create_time"])) if info.get("create_time") else "",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs

# ---------------------------------------------------------------------------
# SMART data (requires smartctl installed, e.g. from smartmontools)
# ---------------------------------------------------------------------------
def collect_smart() -> str:
    try:
        # Try smartctl first
        result = subprocess.run(
            ["smartctl", "--scan"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise FileNotFoundError
        lines = result.stdout.strip().splitlines()
        output_parts = []
        for line in lines:
            dev = line.split()[0] if line.split() else None
            if dev:
                r = subprocess.run(
                    ["smartctl", "-a", dev],
                    capture_output=True, text=True, timeout=30
                )
                output_parts.append(r.stdout)
        return "\n\n".join(output_parts) if output_parts else "No drives found."
    except FileNotFoundError:
        # Fallback: wmic
        try:
            r = subprocess.run(
                ["wmic", "diskdrive", "get", "Caption,Status,Size,SerialNumber,Model"],
                capture_output=True, text=True, timeout=15
            )
            return r.stdout.strip() if r.stdout else "SMART data unavailable."
        except Exception as e:
            return f"SMART data unavailable: {e}"

# ---------------------------------------------------------------------------
# Shell (PTY-like via subprocess)
# ---------------------------------------------------------------------------
class ShellSession:
    def __init__(self):
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen(
            ["cmd.exe"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
            bufsize=0,
        )

    def write(self, data: str):
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(data.encode("utf-8", errors="replace"))
                self.proc.stdin.flush()
            except Exception:
                pass

    def read_line(self) -> str | None:
        if self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if line:
                    return line.decode("utf-8", errors="replace")
            except Exception:
                pass
        return None

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def execute_action(action: str, params: dict) -> str:
    try:
        if action == "reboot":
            subprocess.Popen(["shutdown", "/r", "/t", "0"])
            return "ok"
        elif action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
            return "ok"
        elif action == "kick_user":
            user = params.get("user", "")
            terminal = params.get("terminal", "")
            # Try logoff by session id
            if terminal.isdigit():
                subprocess.run(["logoff", terminal], timeout=10)
            else:
                # Query sessions and find matching user
                r = subprocess.run(["query", "user"], capture_output=True, text=True, timeout=10)
                for line in r.stdout.splitlines():
                    if user.lower() in line.lower():
                        parts = line.split()
                        for p in parts:
                            if p.isdigit():
                                subprocess.run(["logoff", p], timeout=10)
                                break
                        break
            return "ok"
        elif action == "disk_check":
            return "ok"  # SMART data sent separately
        else:
            return f"unknown action: {action}"
    except Exception as e:
        return f"error: {e}"

# ---------------------------------------------------------------------------
# Main async client loop
# ---------------------------------------------------------------------------
class MObserveClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ws = None
        self.running = True
        self.shell = ShellSession()
        self.shell_active = False
        self.logs_active = False
        self._shell_reader_task = None
        self._logs_task = None

    async def connect(self):
        url = self.cfg["backend_url"]
        logging.info(f"Connecting to {url}")
        self.ws = await websockets.connect(url, ping_interval=20, ping_timeout=60)
        # Auth
        auth = {
            "api_key": self.cfg["api_key"],
            "client_id": self.cfg["client_id"],
            "client_name": self.cfg["client_name"],
            "hostname": socket.gethostname(),
            "os": get_os_string(),
            "platform": "windows",
            "ip": get_local_ip(),
        }
        await self.ws.send(json.dumps(auth))
        logging.info("Authenticated.")

    async def telemetry_loop(self):
        interval = 3
        while self.running:
            try:
                data = build_telemetry(self.cfg)
                await self.ws.send(json.dumps(data))
            except Exception as e:
                logging.warning(f"Telemetry send error: {e}")
                raise
            await asyncio.sleep(interval)

    async def _stream_shell_output(self):
        while self.shell_active and self.running:
            line = await asyncio.get_event_loop().run_in_executor(None, self.shell.read_line)
            if line:
                try:
                    await self.ws.send(json.dumps({
                        "type": "shell_output",
                        "client_id": self.cfg["client_id"],
                        "data": line,
                    }))
                except Exception:
                    break
            else:
                await asyncio.sleep(0.05)

    async def _stream_logs(self):
        """Stream Windows Event Log or recent log entries."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-Command",
                "Get-WinEvent -LogName System -MaxEvents 50 | Format-Table -Wrap -AutoSize | Out-String -Width 200",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            while self.logs_active and self.running:
                line = await proc.stdout.readline()
                if not line:
                    break
                await self.ws.send(json.dumps({
                    "type": "logs_line",
                    "client_id": self.cfg["client_id"],
                    "data": line.decode("utf-8", errors="replace"),
                }))
            proc.terminate()
        except Exception as e:
            logging.warning(f"Logs stream error: {e}")

    async def handle_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        msg_type = msg.get("type")

        if msg_type == "request":
            req = msg.get("request")
            if req == "processes":
                procs = await asyncio.get_event_loop().run_in_executor(None, collect_processes)
                await self.ws.send(json.dumps({
                    "type": "processes",
                    "client_id": self.cfg["client_id"],
                    "data": procs,
                }))
            elif req == "disk_check":
                smart_data = await asyncio.get_event_loop().run_in_executor(None, collect_smart)
                await self.ws.send(json.dumps({
                    "type": "smart",
                    "client_id": self.cfg["client_id"],
                    "data": smart_data,
                }))
            elif req == "logs":
                self.logs_active = True
                self._logs_task = asyncio.ensure_future(self._stream_logs())
            elif req == "shell":
                await asyncio.get_event_loop().run_in_executor(None, self.shell.start)
                self.shell_active = True
                self._shell_reader_task = asyncio.ensure_future(self._stream_shell_output())
            elif req == "services":
                # Windows doesn't use systemd; send running services via sc query
                svc_data = await asyncio.get_event_loop().run_in_executor(None, self._get_services)
                await self.ws.send(json.dumps({
                    "type": "services",
                    "client_id": self.cfg["client_id"],
                    "data": svc_data,
                }))
            elif req == "updates":
                await self.ws.send(json.dumps({
                    "type": "updates",
                    "client_id": self.cfg["client_id"],
                    "data": {"packages": []},
                }))

        elif msg_type == "action":
            action = msg.get("action", "")
            params = msg.get("params", {})
            result = await asyncio.get_event_loop().run_in_executor(
                None, execute_action, action, params
            )
            await self.ws.send(json.dumps({
                "type": "action_result",
                "client_id": self.cfg["client_id"],
                "action": action,
                "result": result,
            }))
            # If disk_check action, also send SMART data
            if action == "disk_check":
                smart_data = await asyncio.get_event_loop().run_in_executor(None, collect_smart)
                await self.ws.send(json.dumps({
                    "type": "smart",
                    "client_id": self.cfg["client_id"],
                    "data": smart_data,
                }))

        elif msg_type == "shell_input":
            data = msg.get("data", "")
            await asyncio.get_event_loop().run_in_executor(None, self.shell.write, data)

        elif msg_type == "stop_stream":
            stream = msg.get("stream")
            if stream == "shell":
                self.shell_active = False
                self.shell.stop()
            elif stream == "logs":
                self.logs_active = False

    def _get_services(self) -> list:
        services = []
        try:
            for svc in psutil.win_service_iter():
                try:
                    info = svc.as_dict()
                    state_map = {"running": "active", "stopped": "inactive", "paused": "inactive"}
                    services.append({
                        "name": info.get("name", ""),
                        "state": state_map.get(info.get("status", ""), "inactive"),
                        "sub": info.get("status", "unknown"),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return services

    async def listen_loop(self):
        async for message in self.ws:
            await self.handle_message(message)

    async def run(self):
        backoff = 1
        while self.running:
            try:
                await self.connect()
                backoff = 1
                telemetry_task = asyncio.ensure_future(self.telemetry_loop())
                listen_task = asyncio.ensure_future(self.listen_loop())
                done, pending = await asyncio.wait(
                    [telemetry_task, listen_task],
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for t in pending:
                    t.cancel()
                for t in done:
                    if t.exception():
                        logging.warning(f"Task exception: {t.exception()}")
            except Exception as e:
                logging.warning(f"Connection error: {e}")
            if not self.running:
                break
            logging.info(f"Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    def stop(self):
        self.running = False
        self.shell.stop()

# ---------------------------------------------------------------------------
# Windows Service wrapper
# ---------------------------------------------------------------------------
class MObserveService(win32serviceutil.ServiceFramework):
    _svc_name_ = "MObserveClient"
    _svc_display_name_ = "M-OBSERVE Client"
    _svc_description_ = "Sends system telemetry to the M-OBSERVE Overseer and executes remote commands."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.client = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.client:
            self.client.stop()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        setup_logging()
        logging.info("Service starting...")
        try:
            cfg = load_config()
        except Exception as e:
            logging.error(f"Config load failed: {e}")
            return

        self.client = MObserveClient(cfg)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.client.run())
        except Exception as e:
            logging.error(f"Client crashed: {e}")
        finally:
            loop.close()
        logging.info("Service stopped.")


# ---------------------------------------------------------------------------
# Entry point — can run as service or standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Started by Windows SCM
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(MObserveService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # CLI: install/remove/start/stop/debug
        win32serviceutil.HandleCommandLine(MObserveService)

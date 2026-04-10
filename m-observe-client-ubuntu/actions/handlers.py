"""Action handlers for remote commands."""
import subprocess
import os
import pty
import select
import asyncio
import logging

log = logging.getLogger("m-observe")


def handle_reboot() -> str:
    try:
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        return "ok"
    except Exception as e:
        return f"error: {e}"


def handle_shutdown() -> str:
    try:
        subprocess.Popen(["sudo", "systemctl", "poweroff"])
        return "ok"
    except Exception as e:
        return f"error: {e}"


def handle_kick_user(params: dict) -> str:
    user = params.get("user", "")
    terminal = params.get("terminal", "")
    try:
        # Find session ID for the terminal
        out = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend", "--no-pager"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == user:
                session_id = parts[0]
                subprocess.run(
                    ["sudo", "loginctl", "terminate-session", session_id],
                    capture_output=True, timeout=10,
                )
                return "ok"
        # Fallback: try pkill
        subprocess.run(["sudo", "pkill", "-u", user], capture_output=True, timeout=10)
        return "ok"
    except Exception as e:
        return f"error: {e}"


def handle_update_packages() -> str:
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


def handle_service_restart(params: dict) -> str:
    service_name = params.get("service_name", "")
    if not service_name:
        return "error: no service_name"
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return "ok"
        return f"error: {result.stderr.strip()}"
    except Exception as e:
        return f"error: {e}"


def handle_disk_check() -> list:
    """Run smartctl on all block devices and return structured SMART data."""
    devices = []
    try:
        # Find block devices
        out = subprocess.run(
            ["lsblk", "-dnpo", "NAME,TYPE"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "disk":
                devices.append(parts[0])
    except Exception:
        # Fallback
        import glob
        for d in glob.glob("/dev/sd?") + glob.glob("/dev/nvme?n?"):
            devices.append(d)

    results = []
    for dev in devices:
        entry = {"device": dev}
        try:
            out = subprocess.run(
                ["sudo", "smartctl", "-a", dev],
                capture_output=True, text=True, timeout=30,
            )
            raw = out.stdout
            entry["raw_output"] = raw

            # Parse basic fields
            for line in raw.splitlines():
                ll = line.lower()
                if "model" in ll and ":" in line:
                    entry.setdefault("model", line.split(":", 1)[1].strip())
                if "serial" in ll and ":" in line:
                    entry.setdefault("serial", line.split(":", 1)[1].strip())
                if "firmware" in ll and ":" in line:
                    entry.setdefault("firmware", line.split(":", 1)[1].strip())
                if "capacity" in ll and ":" in line:
                    entry.setdefault("capacity", line.split(":", 1)[1].strip())
                if "health" in ll and ":" in line:
                    entry.setdefault("health", line.split(":", 1)[1].strip())
                if "temperature" in ll and "celsius" in ll:
                    try:
                        val = int(line.split()[-1])
                        entry.setdefault("temperature", val)
                    except Exception:
                        pass
                if "power_on_hours" in ll or "power on hours" in ll:
                    try:
                        val = int(line.split()[-1])
                        entry.setdefault("power_on_hours", val)
                    except Exception:
                        pass
                if "power_cycle_count" in ll or "power cycle count" in ll:
                    try:
                        val = int(line.split()[-1])
                        entry.setdefault("power_cycle_count", val)
                    except Exception:
                        pass
                if "reallocated" in ll and "sector" in ll:
                    try:
                        val = int(line.split()[-1])
                        entry.setdefault("reallocated_sectors", val)
                    except Exception:
                        pass
                if "wear_leveling" in ll:
                    try:
                        val = int(line.split()[-1])
                        entry.setdefault("wear_leveling", val)
                    except Exception:
                        pass

            # Parse SMART attribute table
            attributes = []
            in_table = False
            for line in raw.splitlines():
                if "ID#" in line and "ATTRIBUTE_NAME" in line:
                    in_table = True
                    continue
                if in_table:
                    if not line.strip():
                        break
                    parts = line.split()
                    if len(parts) >= 10 and parts[0].isdigit():
                        attributes.append({
                            "id": int(parts[0]),
                            "name": parts[1],
                            "value": int(parts[3]),
                            "worst": int(parts[4]),
                            "thresh": int(parts[5]),
                            "raw": parts[9],
                        })
            if attributes:
                entry["attributes"] = attributes

        except Exception as e:
            entry["raw_output"] = f"Error reading {dev}: {e}"

        results.append(entry)
    return results


class ShellSession:
    """Manages a PTY shell session."""

    def __init__(self):
        self.master_fd = None
        self.pid = None
        self._running = False

    def start(self):
        master_fd, slave_fd = pty.openpty()
        child_pid = os.fork()
        if child_pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            # Always use /bin/bash — the m-observe user has nologin as shell
            os.execvp("/bin/bash", ["/bin/bash", "--login"])
        else:
            # Parent
            os.close(slave_fd)
            self.master_fd = master_fd
            self.pid = child_pid
            self._running = True

    def write(self, data: str):
        if self.master_fd is not None:
            os.write(self.master_fd, data.encode())

    def read(self, timeout: float = 0.05) -> str:
        if self.master_fd is None:
            return ""
        r, _, _ = select.select([self.master_fd], [], [], timeout)
        if r:
            try:
                data = os.read(self.master_fd, 4096)
                return data.decode("utf-8", errors="replace")
            except OSError:
                self._running = False
                return ""
        return ""

    def stop(self):
        self._running = False
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.pid and self.pid > 0:
            try:
                os.kill(self.pid, 9)
                os.waitpid(self.pid, os.WNOHANG)
            except Exception:
                pass
            self.pid = None

    @property
    def running(self) -> bool:
        return self._running


class LogStreamer:
    """Streams journalctl output."""

    def __init__(self):
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            ["sudo", "journalctl", "-f", "-n", "200", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def stop(self):
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=5)
            except Exception:
                pass
            self.process = None

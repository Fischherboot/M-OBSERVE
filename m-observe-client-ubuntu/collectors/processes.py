"""Process list collector (on-demand)."""
import psutil
import datetime


def collect() -> list:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username", "create_time"]):
        try:
            info = p.info
            started = ""
            if info["create_time"]:
                started = datetime.datetime.fromtimestamp(info["create_time"]).strftime("%Y-%m-%d %H:%M")
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "cpu_percent": round(info["cpu_percent"] or 0, 1),
                "ram_percent": round(info["memory_percent"] or 0, 1),
                "user": info["username"] or "",
                "started": started,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    return procs

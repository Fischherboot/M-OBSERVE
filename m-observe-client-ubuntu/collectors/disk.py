"""Disk telemetry collector."""
import psutil


def collect() -> dict:
    disks = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_gb": round(usage.used / (1024 ** 3), 1),
                "percent": round(usage.percent),
                "fs_type": part.fstype,
            })
        except PermissionError:
            pass
    return {"disks": disks}

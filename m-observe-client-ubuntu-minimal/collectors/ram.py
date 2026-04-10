"""RAM telemetry collector."""
import psutil


def collect() -> dict:
    mem = psutil.virtual_memory()
    return {
        "ram": {
            "total_mb": round(mem.total / (1024 * 1024)),
            "used_mb": round(mem.used / (1024 * 1024)),
            "percent": mem.percent,
        }
    }

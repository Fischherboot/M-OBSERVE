"""CPU telemetry collector — Minimal Client (always reports as Virtual CPU)."""
import psutil


def collect() -> dict:
    freq = psutil.cpu_freq()
    freq_mhz = int(freq.current) if freq else 0

    per_core = psutil.cpu_percent(interval=0, percpu=True)
    total = psutil.cpu_percent(interval=0)
    cores = psutil.cpu_count(logical=True) or 1

    return {
        "cpu": {
            "usage_percent": total,
            "per_core": per_core,
            "model": "Virtual CPU",
            "cores": cores,
            "freq_mhz": freq_mhz,
        }
    }

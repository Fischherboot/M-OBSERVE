"""Temperature sensor collector."""
import psutil


def collect() -> dict:
    temps = {}
    try:
        sensors = psutil.sensors_temperatures()
        if not sensors:
            return {"temperatures": temps}
        for chip, entries in sensors.items():
            for entry in entries:
                label = entry.label or chip
                label = label.lower().replace(" ", "_")
                # De-duplicate labels
                key = label
                i = 0
                while key in temps:
                    i += 1
                    key = f"{label}_{i}"
                if entry.high or entry.critical:
                    temps[key] = {
                        "current": round(entry.current),
                        "high": round(entry.high) if entry.high else None,
                        "critical": round(entry.critical) if entry.critical else None,
                    }
                else:
                    temps[key] = round(entry.current)
    except Exception:
        pass
    return {"temperatures": temps}

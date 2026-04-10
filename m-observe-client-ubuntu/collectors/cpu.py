"""CPU telemetry collector."""
import psutil


def collect() -> dict:
    """Return cpu/cpus block for telemetry payload."""
    freq = psutil.cpu_freq()
    freq_mhz = int(freq.current) if freq else 0

    per_core = psutil.cpu_percent(interval=0, percpu=True)
    total = psutil.cpu_percent(interval=0)

    # Try to detect physical CPU packages via /sys
    packages = _detect_packages()

    if packages and len(packages) > 1:
        cpus = []
        for pkg_id, core_indices in sorted(packages.items()):
            pkg_per_core = [per_core[i] for i in core_indices if i < len(per_core)]
            pkg_usage = sum(pkg_per_core) / len(pkg_per_core) if pkg_per_core else 0.0
            cpus.append({
                "usage_percent": round(pkg_usage, 1),
                "per_core": pkg_per_core,
                "model": _cpu_model(),
                "cores": len(core_indices),
                "freq_mhz": freq_mhz,
            })
        return {"cpus": cpus}
    else:
        return {
            "cpu": {
                "usage_percent": total,
                "per_core": per_core,
                "model": _cpu_model(),
                "cores": psutil.cpu_count(logical=True),
                "freq_mhz": freq_mhz,
            }
        }


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "Unknown CPU"


def _detect_packages() -> dict:
    """Return {package_id: [logical_cpu_indices]} from sysfs."""
    packages = {}
    try:
        import os
        cpu_dir = "/sys/devices/system/cpu"
        for entry in os.listdir(cpu_dir):
            if not entry.startswith("cpu") or not entry[3:].isdigit():
                continue
            idx = int(entry[3:])
            pkg_file = os.path.join(cpu_dir, entry, "topology/physical_package_id")
            if os.path.exists(pkg_file):
                with open(pkg_file) as f:
                    pkg_id = int(f.read().strip())
                packages.setdefault(pkg_id, []).append(idx)
        for k in packages:
            packages[k].sort()
    except Exception:
        pass
    return packages

"""Available package updates collector (on-demand)."""
import subprocess
import logging

log = logging.getLogger("m-observe")


def collect() -> dict:
    packages = []
    try:
        # First refresh the cache silently
        subprocess.run(["sudo", "apt", "update"], capture_output=True, timeout=120)
        out = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, timeout=30,
        )
        for line in out.stdout.strip().splitlines():
            if "/" not in line or "Listing" in line:
                continue
            # Format: name/repo version arch [upgradable from: old_version]
            try:
                name_part, rest = line.split("/", 1)
                parts = rest.split()
                available = parts[1] if len(parts) > 1 else ""
                current = ""
                if "upgradable from:" in line:
                    current = line.split("upgradable from:")[-1].strip().rstrip("]")
                packages.append({
                    "name": name_part,
                    "current": current,
                    "available": available,
                })
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Updates collect error: {e}")
    return {"packages": packages}

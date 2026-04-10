"""systemd service list collector (on-demand)."""
import subprocess
import logging

log = logging.getLogger("m-observe")


def collect() -> list:
    services = []
    try:
        out = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[0].replace(".service", "")
            # LOAD ACTIVE SUB DESCRIPTION...
            state = parts[2]  # active/inactive/failed
            sub = parts[3]    # running/exited/dead/...
            services.append({"name": name, "state": state, "sub": sub})
    except Exception as e:
        log.warning(f"Services collect error: {e}")
    return services

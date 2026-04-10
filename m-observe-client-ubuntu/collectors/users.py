"""Logged-in users collector."""
import psutil


def collect() -> list:
    users = []
    for u in psutil.users():
        users.append({
            "name": u.name,
            "terminal": u.terminal or "",
            "host": u.host or "",
            "started": u.started if isinstance(u.started, str) else "",
        })
    return users

"""
M-OBSERVE Tray + Overlay
- System tray icon in hidden icons area with Pause / Resume / Uninstall
- Transparent always-on-top overlay: "Dieses Gerät wird von M-OBSERVE überwacht."
Runs at user login via Registry autostart.
"""

import sys
import os
import ctypes
import subprocess
import threading
import time
import shutil
import winreg
import tkinter as tk
from pathlib import Path

# pystray for system tray
import pystray
from PIL import Image

INSTALL_DIR = Path(os.environ.get("M_OBSERVE_DIR", r"C:\Program Files\M-OBSERVE Client"))
LOGO_PATH = INSTALL_DIR / "logo.png"
SERVICE_NAME = "MObserveClient"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "MObserveTray"

# ---------------------------------------------------------------------------
# Service control helpers
# ---------------------------------------------------------------------------
def _sc(cmd: str):
    subprocess.run(["sc", cmd, SERVICE_NAME], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)

def is_service_running() -> bool:
    r = subprocess.run(["sc", "query", SERVICE_NAME], capture_output=True, text=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return "RUNNING" in r.stdout

def pause_service():
    _sc("stop")

def resume_service():
    _sc("start")

# ---------------------------------------------------------------------------
# Uninstaller
# ---------------------------------------------------------------------------
def uninstall():
    """Remove service, autostart, overlay, and all installed files."""
    # Stop service
    _sc("stop")
    time.sleep(2)
    subprocess.run(["sc", "delete", SERVICE_NAME], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    # Remove autostart
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, AUTOSTART_VALUE)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass
    # Also check HKLM
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, AUTOSTART_VALUE)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass
    # Schedule file deletion (can't delete running exe)
    bat = Path(os.environ["TEMP"]) / "m_observe_uninstall.bat"
    bat.write_text(
        f'@echo off\n'
        f'timeout /t 3 /nobreak > nul\n'
        f'rmdir /s /q "{INSTALL_DIR}"\n'
        f'del "%~f0"\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat)],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    os._exit(0)

# ---------------------------------------------------------------------------
# Overlay window (Tkinter, transparent, click-through)
# ---------------------------------------------------------------------------
class OverlayWindow:
    def __init__(self):
        self.root = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self.root = tk.Tk()
        self.root.title("M-OBSERVE Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.50)
        self.root.configure(bg="black")
        # Transparent color key for click-through
        self.root.attributes("-transparentcolor", "black")

        label = tk.Label(
            self.root,
            text="Dieses Gerät wird von M-OBSERVE überwacht.",
            fg="#888888",
            bg="black",
            font=("Segoe UI", 9),
        )
        label.pack(padx=6, pady=2)

        self.root.update_idletasks()
        w = self.root.winfo_width()
        sw = self.root.winfo_screenwidth()
        # Position: top right, below taskbar area
        x = sw - w - 20
        y = 8
        self.root.geometry(f"+{x}+{y}")

        # Make click-through on Windows
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        ex_style |= 0x00080000 | 0x00000020 | 0x00000080
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style)

        self.root.mainloop()

# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------
def create_tray():
    # Load logo or create fallback
    try:
        icon_img = Image.open(str(LOGO_PATH)).resize((64, 64), Image.LANCZOS)
    except Exception:
        # Fallback: simple colored square
        icon_img = Image.new("RGBA", (64, 64), (126, 102, 184, 255))

    def on_pause(icon, item):
        pause_service()

    def on_resume(icon, item):
        resume_service()

    def on_uninstall(icon, item):
        icon.stop()
        uninstall()

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    def get_status(item):
        return "● Running" if is_service_running() else "○ Stopped"

    menu = pystray.Menu(
        pystray.MenuItem(get_status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Pause Service", on_pause),
        pystray.MenuItem("Resume Service", on_resume),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Uninstall M-OBSERVE", on_uninstall),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Close Tray Icon", on_quit),
    )

    icon = pystray.Icon("M-OBSERVE", icon_img, "M-OBSERVE Client", menu)
    return icon


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    overlay = OverlayWindow()
    overlay.start()
    icon = create_tray()
    icon.run()  # Blocks


if __name__ == "__main__":
    main()

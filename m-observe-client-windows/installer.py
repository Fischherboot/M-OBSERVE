"""
M-OBSERVE Client — Windows Installer / Uninstaller
Dark-mode Tkinter GUI.
  - Install: License → Config → API Key → Install
  - Uninstall: Confirm → Nuke everything
"""

import sys
import os
import uuid
import json
import shutil
import subprocess
import winreg
import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# ---------------------------------------------------------------------------
# PyInstaller resource path
# ---------------------------------------------------------------------------
def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
INSTALL_DIR = Path(r"C:\Program Files\M-OBSERVE Client")
SERVICE_NAME = "MObserveClient"
SERVICE_EXE_NAME = "m-observe-svc.exe"
OVERLAY_EXE_NAME = "m-observe-overlay.exe"
LOGO_FILE = "logo.png"
TRAY_ICON_FILE = "tray_icon.png"
LICENSE_FILE = "msol.txt"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "MObserveOverlay"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
BG = "#0a0a0c"
BG2 = "#111114"
BG3 = "#1a1a1f"
FG = "#e0e0e0"
FG_DIM = "#888888"
ACCENT = "#7e66b8"
ACCENT_HOVER = "#9a80d4"
BORDER = "#2a2a30"
RED = "#b82020"
RED_HOVER = "#d03030"

# ---------------------------------------------------------------------------
# Admin check
# ---------------------------------------------------------------------------
def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def relaunch_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)

# ---------------------------------------------------------------------------
# Styled widgets
# ---------------------------------------------------------------------------
class DarkEntry(tk.Entry):
    def __init__(self, master, **kw):
        kw.setdefault("bg", BG3)
        kw.setdefault("fg", FG)
        kw.setdefault("insertbackground", FG)
        kw.setdefault("relief", "flat")
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightcolor", ACCENT)
        kw.setdefault("highlightbackground", BORDER)
        kw.setdefault("font", ("Segoe UI", 10))
        super().__init__(master, **kw)

class DarkButton(tk.Button):
    def __init__(self, master, primary=False, danger=False, **kw):
        if danger:
            bg, fg_c = RED, "#ffffff"
            abg = RED_HOVER
        elif primary:
            bg, fg_c = ACCENT, "#ffffff"
            abg = ACCENT_HOVER
        else:
            bg, fg_c = BG3, FG
            abg = BORDER
        kw.setdefault("bg", bg)
        kw.setdefault("fg", fg_c)
        kw.setdefault("activebackground", abg)
        kw.setdefault("activeforeground", "#ffffff")
        kw.setdefault("relief", "flat")
        kw.setdefault("cursor", "hand2")
        kw.setdefault("font", ("Segoe UI", 10))
        kw.setdefault("padx", 18)
        kw.setdefault("pady", 6)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)

# ---------------------------------------------------------------------------
# Full nuke (used by both uninstall and pre-install cleanup)
# ---------------------------------------------------------------------------
def nuke_previous(log=None):
    """Remove every trace of a previous M-OBSERVE installation."""
    def _log(msg):
        if log:
            log(msg)

    # Kill processes
    for exe in [SERVICE_EXE_NAME, OVERLAY_EXE_NAME, "m-observe-tray.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", exe],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(0.5)
    _log("  → Processes killed")

    # Disable service recovery + auto-start so it can't respawn
    subprocess.run(["sc", "failure", SERVICE_NAME, "reset=0", "actions=//"],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run(["sc", "config", SERVICE_NAME, "start=disabled"],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    # Stop service and wait
    subprocess.run(["sc", "stop", SERVICE_NAME],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(10):
        r = subprocess.run(["sc", "query", SERVICE_NAME],
                           capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if "STOPPED" in r.stdout or "1060" in r.stdout:
            break
        time.sleep(0.5)
    _log("  → Service stopped")

    # Delete service
    subprocess.run(["sc", "delete", SERVICE_NAME],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(0.5)
    _log("  → Service deleted")

    # Remove autostart (both old tray and new overlay keys, both hives)
    for value_name in [AUTOSTART_VALUE, "MObserveTray"]:
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                key = winreg.OpenKey(hive, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except Exception:
                pass
    _log("  → Autostart entries removed")

    # Remove environment variable
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                             0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "M_OBSERVE_DIR")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

    # Nuke install directory
    if INSTALL_DIR.exists():
        try:
            shutil.rmtree(str(INSTALL_DIR), ignore_errors=True)
        except Exception:
            pass
        # Force via cmd if still there
        if INSTALL_DIR.exists():
            subprocess.run(["cmd.exe", "/c", f'rmdir /s /q "{INSTALL_DIR}"'],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(0.5)
        _log("  → Files deleted")
    else:
        _log("  → No files found")

# ---------------------------------------------------------------------------
# Installer App
# ---------------------------------------------------------------------------
class InstallerApp:
    PAGES_INSTALL = ["choice", "license", "config", "apikey", "install_progress"]
    PAGES_UNINSTALL = ["choice", "uninstall_confirm", "uninstall_progress"]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("M-OBSERVE Client Setup")
        self.root.geometry("620x520")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(resource_path("logo.ico"))
        except Exception:
            pass

        self.current_page = None

        # Data
        self.client_name = tk.StringVar(value=os.environ.get("COMPUTERNAME", ""))
        self.host_ip = tk.StringVar(value="")
        self.host_port = tk.StringVar(value="3501")
        self.api_key = tk.StringVar(value="")

        # Load logo
        self.logo_img = None
        try:
            from PIL import Image, ImageTk
            img = Image.open(resource_path(LOGO_FILE))
            ratio = 120 / img.width
            img = img.resize((120, int(img.height * ratio)), Image.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
        except Exception:
            pass

        # Load license text
        try:
            with open(resource_path(LICENSE_FILE), "r", encoding="utf-8") as f:
                self.license_text = f.read()
        except Exception:
            self.license_text = "License file not found."

        # Container
        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.show_page("choice")
        self.root.mainloop()

    def _add_logo(self, frame):
        if self.logo_img:
            lbl = tk.Label(frame, image=self.logo_img, bg=BG)
            lbl.place(x=14, rely=1.0, anchor="sw", y=-10)

    def show_page(self, name):
        self.current_page = name
        for w in self.container.winfo_children():
            w.destroy()
        getattr(self, f"_page_{name}")()

    # -----------------------------------------------------------------------
    # Page: Choose Install or Uninstall
    # -----------------------------------------------------------------------
    def _page_choice(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="M-OBSERVE Client", bg=BG, fg=FG,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(30, 4))
        tk.Label(f, text="Self-Hosted Monitoring System", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 50))

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(anchor="w")

        DarkButton(btn_frame, text="Install", primary=True,
                   font=("Segoe UI", 12), padx=32, pady=10,
                   command=lambda: self.show_page("license")).pack(side="left", padx=(0, 16))
        DarkButton(btn_frame, text="Uninstall", danger=True,
                   font=("Segoe UI", 12), padx=32, pady=10,
                   command=lambda: self.show_page("uninstall_confirm")).pack(side="left")

        # Cancel
        bottom = tk.Frame(f, bg=BG)
        bottom.pack(fill="x", side="bottom")
        DarkButton(bottom, text="Cancel", command=self.root.destroy).pack(side="right")

        self._add_logo(self.container)

    # -----------------------------------------------------------------------
    # Page: License
    # -----------------------------------------------------------------------
    def _page_license(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="License Agreement", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(f, text="Please read and accept the Moritzsoft Open License.",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 10))

        txt_frame = tk.Frame(f, bg=BORDER, bd=1, relief="solid")
        txt_frame.pack(fill="both", expand=True)
        txt = tk.Text(txt_frame, bg=BG2, fg=FG_DIM, font=("Consolas", 8), wrap="word",
                      relief="flat", padx=10, pady=8, selectbackground=ACCENT, insertbackground=FG)
        txt.insert("1.0", self.license_text)
        txt.configure(state="disabled")
        sb = tk.Scrollbar(txt_frame, command=txt.yview, bg=BG3, troughcolor=BG2,
                          activebackground=ACCENT)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)

        self.accept_var = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(f, text="I accept the terms of the Moritzsoft Open License",
                            variable=self.accept_var, bg=BG, fg=FG, selectcolor=BG3,
                            activebackground=BG, activeforeground=FG, font=("Segoe UI", 9),
                            command=self._toggle_next)
        cb.pack(anchor="w", pady=(10, 0))

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill="x", pady=(10, 0))
        self._next_btn = DarkButton(btn_frame, text="Next →", primary=True,
                                     command=lambda: self.show_page("config"), state="disabled")
        self._next_btn.pack(side="right")
        DarkButton(btn_frame, text="← Back",
                   command=lambda: self.show_page("choice")).pack(side="right", padx=(0, 8))

        self._add_logo(self.container)

    def _toggle_next(self):
        self._next_btn.configure(state="normal" if self.accept_var.get() else "disabled")

    # -----------------------------------------------------------------------
    # Page: Connection config
    # -----------------------------------------------------------------------
    def _page_config(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="Connection Setup", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(f, text="Configure how this client connects to the M-OBSERVE Overseer.",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 18))

        def field(parent, label, var):
            tk.Label(parent, text=label, bg=BG, fg=FG,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 2))
            e = DarkEntry(parent, textvariable=var, width=50)
            e.pack(anchor="w", ipady=4)

        field(f, "Client Name (Display Name)", self.client_name)
        field(f, "Overseer IP / Hostname", self.host_ip)
        field(f, "Overseer Port", self.host_port)

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill="x", pady=(24, 0), side="bottom")
        DarkButton(btn_frame, text="Next →", primary=True,
                   command=self._validate_config).pack(side="right")
        DarkButton(btn_frame, text="← Back",
                   command=lambda: self.show_page("license")).pack(side="right", padx=(0, 8))

        self._add_logo(self.container)

    def _validate_config(self):
        if not self.client_name.get().strip():
            messagebox.showwarning("Missing", "Client name is required.")
            return
        if not self.host_ip.get().strip():
            messagebox.showwarning("Missing", "Overseer IP is required.")
            return
        if not self.host_port.get().strip().isdigit():
            messagebox.showwarning("Invalid", "Port must be a number.")
            return
        self.show_page("apikey")

    # -----------------------------------------------------------------------
    # Page: API Key
    # -----------------------------------------------------------------------
    def _page_apikey(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="API Key", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(f, text="Enter the API key from your M-OBSERVE Overseer setup.",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 18))

        tk.Label(f, text="API Key", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 2))
        DarkEntry(f, textvariable=self.api_key, width=50).pack(anchor="w", ipady=4)

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill="x", pady=(24, 0), side="bottom")
        DarkButton(btn_frame, text="Install →", primary=True,
                   command=self._start_install).pack(side="right")
        DarkButton(btn_frame, text="← Back",
                   command=lambda: self.show_page("config")).pack(side="right", padx=(0, 8))

        self._add_logo(self.container)

    def _start_install(self):
        if not self.api_key.get().strip():
            messagebox.showwarning("Missing", "API key is required.")
            return
        self.show_page("install_progress")

    # -----------------------------------------------------------------------
    # Page: Install progress
    # -----------------------------------------------------------------------
    def _page_install_progress(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="Installing...", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")

        self.status_label = tk.Label(f, text="Preparing...", bg=BG, fg=FG_DIM,
                                     font=("Segoe UI", 9), anchor="w")
        self.status_label.pack(anchor="w", fill="x", pady=(10, 6))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("dark.Horizontal.TProgressbar", troughcolor=BG3,
                         background=ACCENT, thickness=8, borderwidth=0)
        self.progress = ttk.Progressbar(f, style="dark.Horizontal.TProgressbar",
                                         mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))

        self.log_frame = tk.Frame(f, bg=BORDER, bd=1, relief="solid")
        self.log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(self.log_frame, bg=BG2, fg=FG_DIM, font=("Consolas", 8),
                                 wrap="word", relief="flat", padx=8, pady=6, state="disabled")
        self.log_text.pack(fill="both", expand=True)

        self._add_logo(self.container)
        threading.Thread(target=self._do_install, daemon=True).start()

    def _log(self, msg: str, progress: int = None):
        def _update():
            self.status_label.configure(text=msg)
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
            if progress is not None:
                self.progress["value"] = progress
        self.root.after(0, _update)

    def _do_install(self):
        try:
            self._install_inner()
        except Exception as e:
            self._log(f"ERROR: {e}")
            self.root.after(0, lambda: messagebox.showerror("Installation Failed", str(e)))

    def _install_inner(self):
        # 0. Nuke previous
        self._log("Removing previous installation...", 2)
        nuke_previous(log=self._log)
        time.sleep(0.3)
        self._log("Previous installation cleaned.", 10)

        # 1. Create dir
        self._log("Creating installation directory...", 12)
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        time.sleep(0.2)

        # 2. Config
        self._log("Generating configuration...", 18)
        config = {
            "client_id": str(uuid.uuid4()),
            "client_name": self.client_name.get().strip(),
            "backend_url": f"ws://{self.host_ip.get().strip()}:{self.host_port.get().strip()}/ws/client",
            "api_key": self.api_key.get().strip(),
        }
        (INSTALL_DIR / "config.json").write_text(json.dumps(config, indent=4), encoding="utf-8")
        time.sleep(0.2)

        # 3. Copy files
        self._log("Copying program files...", 28)
        src_dir = Path(resource_path("."))
        for fname in [SERVICE_EXE_NAME, OVERLAY_EXE_NAME, LOGO_FILE, TRAY_ICON_FILE, LICENSE_FILE]:
            src = src_dir / fname
            if src.exists():
                shutil.copy2(str(src), str(INSTALL_DIR / fname))
                self._log(f"  → {fname}")
        time.sleep(0.3)

        # 4. Windows Service
        self._log("Installing Windows Service...", 45)
        svc_exe = INSTALL_DIR / SERVICE_EXE_NAME
        result = subprocess.run(
            ["sc", "create", SERVICE_NAME,
             f"binPath={svc_exe}",
             "start=auto",
             f"DisplayName=M-OBSERVE Client"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._log(f"  sc create: {result.stdout.strip()}")

        subprocess.run(
            ["sc", "description", SERVICE_NAME,
             "Sends system telemetry to the M-OBSERVE Overseer."],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        subprocess.run(
            ["sc", "failure", SERVICE_NAME, "reset=60",
             "actions=restart/5000/restart/10000/restart/30000"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(0.3)

        # 5. Environment variable
        self._log("Setting environment variables...", 55)
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "M_OBSERVE_DIR", 0, winreg.REG_SZ, str(INSTALL_DIR))
            winreg.CloseKey(key)
        except Exception as e:
            self._log(f"  ⚠ Env var: {e}")

        # 6. Register overlay for autostart
        self._log("Registering autostart...", 65)
        overlay_exe = INSTALL_DIR / OVERLAY_EXE_NAME
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, AUTOSTART_KEY,
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, f'"{overlay_exe}"')
            winreg.CloseKey(key)
            self._log("  → HKLM autostart registered")
        except Exception:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                                     0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, f'"{overlay_exe}"')
                winreg.CloseKey(key)
                self._log("  → HKCU autostart registered")
            except Exception as e:
                self._log(f"  ⚠ Autostart: {e}")

        # 7. Start service
        self._log("Starting service...", 80)
        result = subprocess.run(["sc", "start", SERVICE_NAME],
                                capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self._log(f"  {result.stdout.strip()}")
        time.sleep(0.5)

        # 8. Launch overlay
        self._log("Launching overlay...", 90)
        if overlay_exe.exists():
            subprocess.Popen([str(overlay_exe)],
                             creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)

        # Done
        self._log("Installation complete!", 100)
        self.root.after(500, self._show_done)

    def _show_done(self):
        self.status_label.configure(text="✓ Installation complete!", fg="#50e050")
        btn = DarkButton(self.container, text="Close", primary=True, command=self.root.destroy)
        btn.place(relx=1.0, rely=1.0, anchor="se", x=-24, y=-18)

    # -----------------------------------------------------------------------
    # Page: Uninstall confirmation
    # -----------------------------------------------------------------------
    def _page_uninstall_confirm(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="Uninstall M-OBSERVE Client", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(30, 8))

        tk.Label(f, text="This will permanently remove:", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        items = [
            "• Windows Service (MObserveClient)",
            "• Overlay text",
            "• Autostart entries",
            "• All files in C:\\Program Files\\M-OBSERVE Client\\",
            "• Environment variables",
        ]
        for item in items:
            tk.Label(f, text=item, bg=BG, fg=FG_DIM,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(16, 0), pady=1)

        tk.Label(f, text="This action cannot be undone.", bg=BG, fg=RED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(16, 0))

        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(fill="x", side="bottom", pady=(0, 0))
        DarkButton(btn_frame, text="Uninstall", danger=True,
                   command=lambda: self.show_page("uninstall_progress")).pack(side="right")
        DarkButton(btn_frame, text="← Back",
                   command=lambda: self.show_page("choice")).pack(side="right", padx=(0, 8))

        self._add_logo(self.container)

    # -----------------------------------------------------------------------
    # Page: Uninstall progress
    # -----------------------------------------------------------------------
    def _page_uninstall_progress(self):
        f = tk.Frame(self.container, bg=BG)
        f.pack(fill="both", expand=True, padx=24, pady=18)

        tk.Label(f, text="Uninstalling...", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")

        self.status_label = tk.Label(f, text="Removing...", bg=BG, fg=FG_DIM,
                                     font=("Segoe UI", 9), anchor="w")
        self.status_label.pack(anchor="w", fill="x", pady=(10, 6))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("dark.Horizontal.TProgressbar", troughcolor=BG3,
                         background=RED, thickness=8, borderwidth=0)
        self.progress = ttk.Progressbar(f, style="dark.Horizontal.TProgressbar",
                                         mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))

        self.log_frame = tk.Frame(f, bg=BORDER, bd=1, relief="solid")
        self.log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(self.log_frame, bg=BG2, fg=FG_DIM, font=("Consolas", 8),
                                 wrap="word", relief="flat", padx=8, pady=6, state="disabled")
        self.log_text.pack(fill="both", expand=True)

        self._add_logo(self.container)
        threading.Thread(target=self._do_uninstall, daemon=True).start()

    def _do_uninstall(self):
        try:
            self._log("Removing M-OBSERVE Client...", 5)
            time.sleep(0.3)
            nuke_previous(log=self._log)
            self._log("Uninstall complete.", 100)
            self.root.after(500, self._show_uninstall_done)
        except Exception as e:
            self._log(f"ERROR: {e}")

    def _show_uninstall_done(self):
        self.status_label.configure(text="✓ M-OBSERVE Client has been removed.", fg="#50e050")
        btn = DarkButton(self.container, text="Close", primary=True, command=self.root.destroy)
        btn.place(relx=1.0, rely=1.0, anchor="se", x=-24, y=-18)

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not is_admin():
        relaunch_as_admin()
    InstallerApp()

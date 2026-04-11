"""
M-OBSERVE Overlay — "Activate Windows" style text.
Runs at user login via Registry autostart.
No tray, no menu, just the text.
"""

import sys
import os
import ctypes
import tkinter as tk


def main():
    root = tk.Tk()
    root.title("")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.attributes("-transparentcolor", "black")
    root.attributes("-alpha", 0.42)

    label = tk.Label(
        root,
        text="Dieses Gerät wird von\nM-OBSERVE überwacht.",
        fg="white",
        bg="black",
        font=("Segoe UI Semibold", 14),
        justify="right",
        anchor="se",
    )
    label.pack(padx=12, pady=8)

    root.update_idletasks()
    w = root.winfo_reqwidth()
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"+{sw - w - 28}+{sh - h - 64}")

    # Click-through + no taskbar entry
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        ex |= 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex)
    except Exception:
        pass

    root.mainloop()


if __name__ == "__main__":
    main()

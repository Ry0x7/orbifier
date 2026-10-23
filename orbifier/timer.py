"""
timer.py – Fake game process: countdown timer window for Discord detection.

Discord detects games by scanning visible top-level windows (EnumWindows).
When orbifier copies itself (or pythonw.exe) and renames it to a game's
executable name, the copy opens this window. Keeping the window open (or
minimized to the taskbar/tray) allows Discord to see the process and track the quest.
"""

import os
import sys
import time
import tkinter as tk
from pathlib import Path

BG_COLOR      = "#0f101a"
PANEL_COLOR   = "#161826"
TEXT_COLOR    = "#f0f2f5"
ACCENT_COLOR  = "#00e5ff"
GREEN_COLOR   = "#4ade80"
MUTED_COLOR   = "#8b90a0"
DONE_COLOR    = "#ff6b8b"
DEFAULT_MINS  = 20


class TimerApp:
    def __init__(
        self,
        root: tk.Tk,
        name: str = "",
        duration_s: float = DEFAULT_MINS * 60,
        started: float | None = None,
        auto_close: bool = True,
    ):
        self.root = root
        self.name = name or self._detect_name()
        self.duration_s = float(duration_s)
        self.started = float(started) if started is not None else time.time()
        self.auto_close = auto_close
        self.tray = None
        self._saved_geometry = None

        self.root.title(f"Orbifier – {self.name}")
        self.root.geometry("380x230")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_COLOR)

        # Center on screen
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"+{x}+{y}")

        # Title / Game label
        self.name_label = tk.Label(
            root, text=self.name,
            font=("Segoe UI", 12, "bold"), fg=ACCENT_COLOR, bg=BG_COLOR,
            wraplength=350,
        )
        self.name_label.pack(pady=(14, 2))

        # Big countdown timer
        initial_rem = max(0, int(self.duration_s - (time.time() - self.started)))
        m, s = divmod(initial_rem, 60)
        self.timer_label = tk.Label(
            root, text=f"{m:02d}:{s:02d}",
            font=("Consolas", 38, "bold"), fg=TEXT_COLOR, bg=BG_COLOR,
        )
        self.timer_label.pack(pady=2)

        # Status indicator
        self.status_label = tk.Label(
            root, text="● Spoofing active (Discord detecting game)",
            font=("Segoe UI", 9, "bold"), fg=GREEN_COLOR, bg=BG_COLOR,
        )
        self.status_label.pack(pady=(2, 6))

        # Action buttons
        btn_row = tk.Frame(root, bg=BG_COLOR)
        btn_row.pack(side="top", pady=(0, 4))

        self.tray_btn = tk.Button(
            btn_row,
            text="🗕 HIDE TO TRAY",
            command=self.hide_to_tray,
            bg=PANEL_COLOR,
            fg=ACCENT_COLOR,
            activebackground=BG_COLOR,
            activeforeground=TEXT_COLOR,
            font=("Segoe UI", 8, "bold"),
            relief="groove",
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
        )
        self.tray_btn.pack(side="left", padx=4)

        # Tip / minimize note
        self.tip_label = tk.Label(
            root, text="Keep open or in tray. Close window to stop quest.",
            font=("Segoe UI", 8), fg=MUTED_COLOR, bg=BG_COLOR,
        )
        self.tip_label.pack(side="bottom", pady=(0, 8))

        self.root.protocol("WM_DELETE_WINDOW", self.stop_and_exit)
        self._tick()

    def _detect_name(self) -> str:
        for i, arg in enumerate(sys.argv):
            if arg == "--name" and i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        stem = Path(sys.argv[0]).stem
        if stem and stem.lower() not in ("orbifier", "python", "pythonw", "_orbifier_timer"):
            return stem
        return "Game"

    def _tick(self):
        elapsed = time.time() - self.started
        remaining = max(0, int(self.duration_s - elapsed))
        self.remaining = remaining
        m, s = divmod(remaining, 60)
        time_str = f"{m:02d}:{s:02d}"
        self.timer_label.config(text=time_str)

        if self.tray and getattr(self.tray, "_running", False):
            self.tray.update_tooltip(f"Orbifier – {self.name} ({time_str})")

        if remaining > 0:
            self.root.after(1000, self._tick)
        else:
            self.timer_label.config(fg=DONE_COLOR)
            if self.auto_close:
                self.status_label.config(text="✓ Quest complete! Auto-closing in 2s...", fg=ACCENT_COLOR)
                self.root.after(2000, self.stop_and_exit)
            else:
                self.status_label.config(text="✓ Quest time complete (keep open if needed)", fg=ACCENT_COLOR)

    def hide_to_tray(self):
        """Hide window to notification tray while keeping IsWindowVisible == 1 for Discord."""
        if sys.platform != "win32":
            self.root.iconify()
            return
        self._saved_geometry = self.root.geometry()
        # Set toolwindow so taskbar entry is removed, move off-screen
        self.root.attributes("-toolwindow", True)
        self.root.geometry("+50000+50000")

        rem = max(0, int(self.duration_s - (time.time() - self.started)))
        m, s = divmod(rem, 60)
        try:
            from .tray import TrayIcon
        except ImportError:
            try:
                from orbifier.tray import TrayIcon
            except ImportError:
                TrayIcon = None

        if TrayIcon:
            def _open():
                self.root.after(0, self.restore_from_tray)

            def _exit():
                self.root.after(0, self.stop_and_exit)

            self.tray = TrayIcon(
                tooltip=f"Orbifier – {self.name} ({m:02d}:{s:02d})",
                on_open=_open,
                on_exit=_exit,
            )
            self.tray.start()

    def restore_from_tray(self):
        """Restore window from system tray."""
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.root.attributes("-toolwindow", False)
        self.root.geometry(self._saved_geometry or "380x230")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def stop_and_exit(self):
        """Cleanly destroy window and exit."""
        if self.tray:
            self.tray.stop()
            self.tray = None
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)


def run_timer():
    """Entry point for the fake game process."""
    name = ""
    duration_s = float(DEFAULT_MINS * 60)
    started = None
    auto_close = True

    try:
        from . import config
        duration_s = float(getattr(config, "QUEST_MINUTES", DEFAULT_MINS) * 60)
        auto_close = bool(getattr(config, "AUTO_CLOSE", True))
    except Exception:
        pass

    for i, arg in enumerate(sys.argv):
        if arg == "--name" and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
        elif arg == "--duration" and i + 1 < len(sys.argv):
            try:
                duration_s = float(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg == "--minutes" and i + 1 < len(sys.argv):
            try:
                duration_s = float(sys.argv[i + 1]) * 60
            except ValueError:
                pass
        elif arg == "--started" and i + 1 < len(sys.argv):
            try:
                started = float(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg == "--auto-close" and i + 1 < len(sys.argv):
            auto_close = sys.argv[i + 1] in ("1", "true", "True")

    root = tk.Tk()
    TimerApp(root, name=name, duration_s=duration_s, started=started, auto_close=auto_close)
    root.mainloop()

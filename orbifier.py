#!/usr/bin/env python3
"""
Backward-compatible entry point.

Usage:
    python orbifier.py         (desktop GUI)
    python orbifier.py --cli   (terminal menu)
    python -m orbifier         (package-style, same flags)

When launched with --timer-mode (by a renamed copy of itself),
it runs a silent, windowless keep-alive instead of the main menu.
"""

import sys
import os


def _attach_console_for_cli():
    """Give a windowed (console=False) frozen exe a console when --cli is used."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        if sys.stdout is not None and sys.stdout.fileno() >= 0:
            return  # already has a usable stdout
    except Exception:
        pass
    try:
        import ctypes
        if not ctypes.windll.kernel32.AllocConsole():
            return
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass


if "--cli" in sys.argv:
    _attach_console_for_cli()

# ── Safety: redirect stdio to devnull when running without a console ──────────
# PyInstaller --noconsole (or pythonw) sets sys.stdout/stderr/stdin to None.
# Redirect to devnull so print() / input() don't crash the whole app.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")

if "--timer-mode" in sys.argv:
    from orbifier.timer import run_timer
    run_timer()
elif "--cli" in sys.argv:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from orbifier.main import main
    from orbifier.ui import print_color, Colors

    try:
        main()
    except KeyboardInterrupt:
        print_color("\n\n[!] Interrupted", Colors.YELLOW)
        sys.exit(0)
    except Exception as e:
        print_color(f"\n[ERROR] Fatal error: {e}", Colors.RED, bold=True)
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
else:
    try:
        from orbifier.gui import run_gui
        run_gui()
    except Exception:
        import traceback
        _tb = traceback.format_exc()
        try:
            import tkinter as _tk
            from tkinter import messagebox as _mb
            _root = _tk.Tk()
            _root.withdraw()
            _mb.showerror("Orbifier - fatal error", _tb)
            _root.destroy()
        except Exception:
            print(_tb, file=sys.stderr)
        sys.exit(1)

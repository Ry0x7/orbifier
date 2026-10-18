"""Entry point for `python -m orbifier` (GUI by default, --cli for the terminal menu)."""

import os
import sys


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


if "--timer-mode" in sys.argv:
    from .timer import run_timer
    run_timer()
elif "--cli" in sys.argv:
    _attach_console_for_cli()
    from .main import main
    main()
else:
    try:
        from .gui import run_gui
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

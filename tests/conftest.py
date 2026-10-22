"""Shared Tk fixtures for the GUI integration tests.

The Windows Store Tcl runtime cannot reliably initialise a second Tk root
after the first one is destroyed, so every GUI test module shares one
session-scoped root while still getting a fresh OrbifierApp per module.
"""
import os
import tkinter as tk

import pytest

from orbifier import gui, ui


@pytest.fixture(scope="session")
def gui_root():
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("Tk integration tests require a desktop display or Xvfb.")
    root = tk.Tk()
    root.withdraw()
    yield root
    ui.set_output_hook(None)
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture(scope="module")
def gui_app(gui_root):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gui, "is_process_elevated", lambda: False)
    monkeypatch.setattr(gui.OrbifierApp, "run_task", lambda *a, **kw: None)
    instance = gui.OrbifierApp(gui_root, check_updates=False)
    yield instance

    ui.set_output_hook(None)
    for after_id in gui_root.tk.call("after", "info"):
        try:
            gui_root.after_cancel(after_id)
        except tk.TclError:
            pass
    for child in list(gui_root.winfo_children()):
        try:
            child.destroy()
        except tk.TclError:
            pass
    monkeypatch.undo()

"""Exercise the real Tk controls without networking or launching placeholders."""
import tkinter as tk
import os

import pytest

from orbifier import gui, ui


@pytest.fixture(scope="module")
def app():
    monkeypatch = pytest.MonkeyPatch()
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("Tk integration tests require a desktop display or Xvfb.")
    root = tk.Tk()
    root.withdraw()
    monkeypatch.setattr(gui, "is_process_elevated", lambda: False)
    monkeypatch.setattr(gui.OrbifierApp, "run_task", lambda *a, **kw: None)
    instance = gui.OrbifierApp(root, check_updates=False)
    yield instance
    ui.set_output_hook(None)
    root.destroy()
    monkeypatch.undo()


def test_changed_screens_fit_existing_window(app):
    for name in ("manual", "database", "steam"):
        app.show(name)
        app.root.update_idletasks()
        screen = app.screens[name]
        assert screen.winfo_reqwidth() <= gui.WIN_W, (name, screen.winfo_reqwidth())
        assert screen.winfo_reqheight() <= gui.HOST_H, (name, screen.winfo_reqheight())


def test_steam_app_id_entry_does_not_need_store_search(app):
    app.steam_query.insert(0, "4080220")
    app.steam_search()
    assert app.steam_results[0]["id"] == 4080220
    assert app.steam_list.curselection() == (0,)


def test_steam_confirmation_previews_fc27_layout(app, tmp_path, monkeypatch):
    app.steam_path.insert(0, str(tmp_path / "steamapps"))
    app.steam_query.delete(0, "end")
    app.steam_query.insert(0, "4080220")
    app.steam_search()
    app.steam_install.insert(0, "EA SPORTS FC 27")
    app.steam_override.insert(0, r"..\EA SPORTS FC 27\fc27.exe")
    monkeypatch.setattr(app, "run_task", lambda label, fn, done: done(fn()))
    monkeypatch.setattr(gui.steam, "fetch_steam_app_info", lambda appid: None)
    confirmations = []
    monkeypatch.setattr(gui.messagebox, "askyesno",
                        lambda title, text, **kw: confirmations.append(text) or False)
    app.steam_create()
    assert len(confirmations) == 1
    text = confirmations[0]
    assert str(tmp_path / "steamapps/common/EA SPORTS FC 27/fc27.exe") in text
    assert "Manifest mode: installed" in text
    assert not (tmp_path / "steamapps").exists()

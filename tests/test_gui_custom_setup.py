"""Exercise the real Tk controls without networking or launching placeholders."""
import pytest

from orbifier import gui


@pytest.fixture(scope="module")
def app(gui_app):
    return gui_app


@pytest.mark.parametrize("width", [gui.WIN_W, gui.DEFAULT_W])
def test_changed_screens_fit_window(app, width):
    for name in ("manual", "database", "steam"):
        app.show(name)
        app.root.update_idletasks()
        screen = app.screens[name]
        assert screen.winfo_reqwidth() <= width, (name, width, screen.winfo_reqwidth())
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


def test_steam_create_overwrites_existing_manifest_and_exe(app, tmp_path, monkeypatch):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir(parents=True)
    acf = steamapps / "appmanifest_4080220.acf"
    acf.write_text("old manifest")
    exe = steamapps / "common/EA SPORTS FC 27/fc27.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"old exe")

    app.steam_path.delete(0, "end")
    app.steam_path.insert(0, str(steamapps))
    app.steam_query.delete(0, "end")
    app.steam_query.insert(0, "4080220")
    app.steam_search()
    app.steam_install.delete(0, "end")
    app.steam_install.insert(0, "EA SPORTS FC 27")
    app.steam_override.delete(0, "end")
    app.steam_override.insert(0, r"..\EA SPORTS FC 27\fc27.exe")

    monkeypatch.setattr(app, "run_task", lambda label, fn, done, *a: done(fn()))
    monkeypatch.setattr(gui.steam, "fetch_steam_app_info", lambda appid: None)
    monkeypatch.setattr(app.faker, "launch_executable", lambda path, **kw: None)
    confirmations = []
    monkeypatch.setattr(gui.messagebox, "askyesno",
                        lambda title, text, **kw: confirmations.append(text) or True)

    app.steam_create()
    assert len(confirmations) == 1
    assert "overwritten" in confirmations[0]
    assert "AppState" in acf.read_text()


def test_steam_delete_removes_setup(app, tmp_path, monkeypatch):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir(parents=True)
    acf = steamapps / "appmanifest_4080220.acf"
    acf.write_text("manifest to delete")
    exe = steamapps / "common/EA SPORTS FC 27/fc27.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe to delete")

    app.steam_path.delete(0, "end")
    app.steam_path.insert(0, str(steamapps))
    app.steam_query.delete(0, "end")
    app.steam_query.insert(0, "4080220")
    app.steam_search()
    app.steam_install.delete(0, "end")
    app.steam_install.insert(0, "EA SPORTS FC 27")
    app.steam_override.delete(0, "end")
    app.steam_override.insert(0, r"..\EA SPORTS FC 27\fc27.exe")

    monkeypatch.setattr(app, "run_task", lambda label, fn, done, *a: done(fn()))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **kw: True)

    app.steam_delete()
    assert not acf.exists()
    assert not exe.exists()
    assert not (steamapps / "common/EA SPORTS FC 27").exists()


def test_manual_delete_removes_executable(app, tmp_path, monkeypatch):
    out = tmp_path / "manual_out"
    app.output_directory.set(str(out))
    target = app.faker.create_fake_game("testgame.exe", output_dir=out)
    assert target.exists()

    app.manual_exe.delete(0, "end")
    app.manual_exe.insert(0, "testgame.exe")

    monkeypatch.setattr(app, "run_task", lambda label, fn, done, *a: done(fn()))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **kw: True)

    app.manual_delete()
    assert not target.exists()


class _DeadProc:
    def poll(self):
        return 1


@pytest.mark.parametrize("proc", [None, _DeadProc()], ids=["no-process", "dead-process"])
def test_create_and_launch_requires_a_live_process(app, tmp_path, monkeypatch, proc):
    target = tmp_path / "deadgame.exe"
    target.write_bytes(b"x")
    before = len(app.quests.quests)
    sentinel = "SHOULD-NOT-LOG-SUCCESS"
    cleaned = []

    monkeypatch.setattr(app.faker, "create_fake_game", lambda *a, **k: target)
    monkeypatch.setattr(app.faker, "launch_executable", lambda *a, **k: proc)
    monkeypatch.setattr(app.faker, "delete_fake_game",
                        lambda *a, **k: cleaned.append((a, k)) or {})
    monkeypatch.setattr(app, "run_task", lambda label, fn, done, *a: done(fn()))

    app._create_and_launch("deadgame.exe", sentinel, minutes=20)

    log = app.log_text.get("1.0", "end")
    assert sentinel not in log
    assert "did not start; no quest was tracked" in log
    assert len(app.quests.quests) == before
    assert cleaned

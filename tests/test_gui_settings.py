"""Exercise the real SETTINGS screen and the auto-clean / close-on-exit wiring."""
import json

import pytest

from orbifier import config, gui, user_settings


@pytest.fixture(scope="module")
def app(gui_app):
    return gui_app


@pytest.fixture(autouse=True)
def _clear_app_quests(app):
    app.quests.quests.clear()
    yield
    app.quests.quests.clear()


def _show(app):
    app.show("settings")
    app.root.update_idletasks()


def test_home_has_settings_button(app):
    assert app.home_settings_button.text == "SETTINGS"
    app.home_settings_button.invoke()
    assert app.current == "settings"


def test_settings_and_home_fit_minimum_window(app):
    for name in ("home", "settings"):
        app.show(name)
        app.root.update_idletasks()
        screen = app.screens[name]
        assert screen.winfo_reqwidth() <= gui.WIN_W, name
        assert screen.winfo_reqheight() <= gui.HOST_H, name


def test_settings_screen_seeds_from_config(app, monkeypatch):
    monkeypatch.setattr(config, "QUEST_MINUTES", 33.0)
    monkeypatch.setattr(config, "AUTO_CLOSE", False)
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", False)
    monkeypatch.setattr(config, "CHECK_UPDATES", False)
    monkeypatch.setattr(config, "OUTPUT_DIR", "C:/tmp/out")
    _show(app)
    assert app.settings_minutes.get() == "33"
    assert app.settings_autoclose.get() is False
    assert app.settings_autoclean.get() is False
    assert app.settings_close_on_exit.get() is False
    assert app.settings_check_updates.get() is False
    assert app.settings_output.get() == "C:/tmp/out"


def test_save_writes_json_and_applies(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    app.settings_autoclose.set(False)
    app.settings_autoclean.set(False)
    app.settings_close_on_exit.set(False)
    app.settings_check_updates.set(False)
    app.settings_output.set(str(tmp_path / "out"))
    app.settings_save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["QUEST_MINUTES"] == 25.0
    assert data["AUTO_CLEAN"] is False
    assert config.QUEST_MINUTES == 25.0
    assert config.AUTO_CLOSE is False
    assert config.AUTO_CLEAN is False
    assert config.CLOSE_QUESTS_ON_EXIT is False
    assert config.CHECK_UPDATES is False
    assert config.OUTPUT_DIR == str(tmp_path / "out")
    assert app.output_directory.get() == str(tmp_path / "out")
    for entry in (app.db_minutes, app.manual_minutes, app.steam_minutes):
        assert entry.get() == "25"
    for var in (app.db_autoclose, app.manual_autoclose, app.steam_autoclose):
        assert var.get() is False


def test_save_blank_output_uses_desktop_default(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    app.settings_output.set("   ")
    app.settings_save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["OUTPUT_DIR"] == ""
    assert config.OUTPUT_DIR == ""
    assert app.settings_output.get() == ""
    assert app.output_directory.get() == str(
        app.faker.desktop_path / config.FAKE_EXE_DIR)


def test_save_invalid_timer_keeps_file_unchanged(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"AUTO_CLOSE": true}', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    base = config.QUEST_MINUTES
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "0")
    app.settings_save()
    assert "between 1 and 1440" in app.settings_status_var.get()
    assert config.QUEST_MINUTES == base
    assert path.read_text(encoding="utf-8") == before


def test_save_failure_does_not_apply_config(app, monkeypatch):
    base = config.QUEST_MINUTES
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    monkeypatch.setattr(user_settings, "save_overrides",
                        lambda values: (_ for _ in ()).throw(
                            user_settings.SettingsError("disk full")))
    app.settings_save()
    assert "disk full" in app.settings_status_var.get()
    assert config.QUEST_MINUTES == base


def test_reset_deletes_file_and_restores_defaults(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    base = config.QUEST_MINUTES
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    app.settings_save()
    assert path.exists()
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.settings_reset()
    assert not path.exists()
    assert config.QUEST_MINUTES == base
    assert "RESET" in app.settings_status_var.get()


class FakeProc:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def test_close_on_exit_stops_all_quests(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.quests, "stop_all",
                        lambda clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", True)
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    app._stop_quests_for_exit()
    assert calls == [False]


def test_close_on_exit_disabled_does_nothing(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.quests, "stop_all",
                        lambda clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", False)
    app._stop_quests_for_exit()
    assert calls == []


def test_tick_auto_cleans_stopped_quests(app, monkeypatch):
    quest = app.quests.add("Stopped.exe", FakeProc(returncode=0))
    calls = []
    monkeypatch.setattr(app, "_stop_quests", lambda quests: calls.extend(quests))
    monkeypatch.setattr(config, "AUTO_CLEAN", True)
    app._tick_quests()
    assert quest in calls
    app.quests.quests.remove(quest)


def test_tick_keeps_stopped_quest_when_auto_clean_off(app, monkeypatch):
    quest = app.quests.add("Stopped.exe", FakeProc(returncode=0))
    calls = []
    monkeypatch.setattr(app, "_stop_quests", lambda quests: calls.extend(quests))
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    app._tick_quests()
    assert calls == []
    assert quest in app.quests.quests
    app.quests.quests.remove(quest)


@pytest.mark.parametrize("auto_clean", [True, False])
def test_stop_quests_passes_auto_clean_flag(app, monkeypatch, auto_clean):
    quest = app.quests.add("Test.exe", FakeProc())
    calls = []
    monkeypatch.setattr(app.quests, "cleanup",
                        lambda q, clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(config, "AUTO_CLEAN", auto_clean)
    app._stop_quests([quest])
    assert calls == [auto_clean]

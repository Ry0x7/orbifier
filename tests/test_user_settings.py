import json

import pytest

from orbifier import user_settings


def test_settings_path_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(tmp_path / "s.json"))
    assert user_settings.settings_path() == tmp_path / "s.json"


def test_settings_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("ORBIFIER_SETTINGS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert user_settings.settings_path() == tmp_path / "Orbifier" / "settings.json"


def test_settings_path_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("ORBIFIER_SETTINGS", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(user_settings, "_home_dir", lambda: tmp_path)
    assert user_settings.settings_path() == tmp_path / ".orbifier" / "settings.json"


def test_save_load_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    values = {"QUEST_MINUTES": 25, "AUTO_CLOSE": False, "AUTO_CLEAN": False,
              "CLOSE_QUESTS_ON_EXIT": False, "OUTPUT_DIR": str(tmp_path / "out"),
              "CHECK_UPDATES": False}
    assert user_settings.save_overrides(values) == path
    assert user_settings.load_overrides() == {**values, "QUEST_MINUTES": 25.0}
    assert user_settings.LOAD_ERROR is None


def test_save_is_atomic(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    user_settings.save_overrides({"AUTO_CLOSE": False})
    assert not (tmp_path / "settings.json.tmp").exists()


@pytest.mark.parametrize("values", [
    {"QUEST_MINUTES": 0}, {"QUEST_MINUTES": "abc"}, {"QUEST_MINUTES": True},
    {"AUTO_CLOSE": "yes"}, {"OUTPUT_DIR": 123},
])
def test_validate_rejects_invalid_values(values):
    with pytest.raises(user_settings.SettingsError):
        user_settings.validate(values)


def test_malformed_json_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {}
    assert "Could not read" in user_settings.LOAD_ERROR


def test_unknown_keys_are_ignored(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"NOPE": 1, "AUTO_CLOSE": False}), encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {"AUTO_CLOSE": False}
    assert user_settings.LOAD_ERROR is None


def test_invalid_key_is_skipped(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"QUEST_MINUTES": 0, "AUTO_CLOSE": False}), encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {"AUTO_CLOSE": False}
    assert "QUEST_MINUTES" in user_settings.LOAD_ERROR


def test_delete_is_safe_when_missing(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.delete_overrides() is False
    user_settings.save_overrides({"AUTO_CLOSE": True})
    assert user_settings.delete_overrides() is True
    assert not path.exists()

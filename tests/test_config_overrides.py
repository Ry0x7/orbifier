from orbifier import config


def test_new_keys_have_expected_defaults():
    assert config.CLOSE_QUESTS_ON_EXIT is True
    assert config.OUTPUT_DIR == ""
    assert config.CHECK_UPDATES is True


def test_apply_overrides_changes_values():
    base_minutes = config.QUEST_MINUTES
    config.apply_overrides({"QUEST_MINUTES": 25, "AUTO_CLEAN": False})
    assert config.QUEST_MINUTES == 25
    assert config.AUTO_CLEAN is False
    config.reset_overrides()
    assert config.QUEST_MINUTES == base_minutes
    assert config.AUTO_CLEAN is True


def test_loaded_override_wins(monkeypatch):
    monkeypatch.setitem(config._overrides, "QUEST_MINUTES", 33)
    assert config._get("QUEST_MINUTES", 20) == 33


def test_reset_restores_output_and_close_on_exit():
    config.apply_overrides({"OUTPUT_DIR": "C:/out", "CLOSE_QUESTS_ON_EXIT": False})
    assert config.OUTPUT_DIR == "C:/out"
    assert config.CLOSE_QUESTS_ON_EXIT is False
    config.reset_overrides()
    assert config.OUTPUT_DIR == ""
    assert config.CLOSE_QUESTS_ON_EXIT is True

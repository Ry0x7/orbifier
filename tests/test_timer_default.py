"""The shipped timer default stays consistent across code and credits."""
import settings

from orbifier import config, faker, timer
from orbifier.ui import _NoColors, credits_text


class FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args


def test_default_timer_is_twenty_minutes():
    assert settings.QUEST_MINUTES == 20
    assert config.QUEST_MINUTES == 20
    assert timer.DEFAULT_MINS == 20


def test_credits_mention_twenty_minutes():
    assert "20 minutes" in credits_text(c=_NoColors, enter_prompt=False)


def test_embedded_timer_defaults_to_twenty():
    assert "DEFAULT_MINS  = 20" in faker._TIMER_PYW_CODE


def test_launch_uses_configured_timer_default(tmp_path, monkeypatch):
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(faker.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(faker, "loading_animation", lambda *a, **k: None)
    monkeypatch.setattr(faker, "print_color", lambda *a, **k: None)
    monkeypatch.setattr(config, "QUEST_MINUTES", 25)
    proc = faker.GameFaker().launch_executable(exe)
    assert proc.args[proc.args.index("--duration") + 1] == "1500"

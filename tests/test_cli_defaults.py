from orbifier import config, faker, main


class FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args

    def poll(self):
        return None


def _game(monkeypatch):
    monkeypatch.setattr(faker.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(faker, "loading_animation", lambda *a, **k: None)
    monkeypatch.setattr(faker, "print_color", lambda *a, **k: None)
    return faker.GameFaker()


def test_launch_auto_close_uses_config(tmp_path, monkeypatch):
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(config, "AUTO_CLOSE", False)
    proc = _game(monkeypatch).launch_executable(exe)
    assert proc.args[proc.args.index("--auto-close") + 1] == "0"


def test_update_check_can_be_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "auto_update", lambda: calls.append(1))
    monkeypatch.setattr(config, "CHECK_UPDATES", False)
    main._run_update_check()
    assert calls == []
    monkeypatch.setattr(config, "CHECK_UPDATES", True)
    main._run_update_check()
    assert calls == [1]

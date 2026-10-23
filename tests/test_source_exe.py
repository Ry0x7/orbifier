import subprocess
import sys
from pathlib import Path

import pytest

from orbifier import faker


def test_source_exe_prefers_readable_executable(tmp_path, monkeypatch):
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    # The Windows Store app-execution alias exists as a file but cannot be opened.
    alias_exe = alias_dir / "pythonw.exe"
    alias_exe.write_bytes(b"Store alias")

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    real_pythonw = base_dir / "pythonw.exe"
    real_pythonw.write_bytes(b"pythonw")

    real_open = Path.open

    def guarded_open(self, *args, **kwargs):
        if self == alias_exe:
            raise PermissionError("Windows Store alias cannot be opened")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    monkeypatch.setattr(faker.sys, "executable", str(alias_dir / "python.exe"))
    monkeypatch.setattr(faker.sys, "base_prefix", str(base_dir))

    assert faker._find_source_exe() == real_pythonw


def test_source_exe_prefers_readable_pythonw_over_base_python(tmp_path, monkeypatch):
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    venv_pythonw = alias_dir / "pythonw.exe"
    venv_pythonw.write_bytes(b"pythonw")

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (base_dir / "pythonw.exe").write_bytes(b"base pythonw")

    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    monkeypatch.setattr(faker.sys, "executable", str(alias_dir / "python.exe"))
    monkeypatch.setattr(faker.sys, "base_prefix", str(base_dir))

    assert faker._find_source_exe() == venv_pythonw


@pytest.mark.skipif(sys.platform != "win32", reason="Windows source-copy check")
def test_copied_source_exe_starts_and_imports_tkinter(tmp_path):
    pytest.importorskip("tkinter")

    instance = faker.GameFaker()
    target = tmp_path / "StoreTest.exe"
    instance.copy_exe_to(target)

    marker = tmp_path / "probe-marker.txt"
    probe = tmp_path / "probe.pyw"
    probe.write_text(
        "import pathlib\n"
        "import sys\n"
        "import tkinter\n"
        "root = tkinter.Tk()\n"
        "root.withdraw()\n"
        "version = tkinter.TkVersion\n"
        "root.destroy()\n"
        "pathlib.Path(sys.argv[1]).write_text(str(version), encoding='utf-8')\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [str(target), str(probe), str(marker)],
        env=faker._source_launch_env(target),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )

    assert proc.returncode == 0, proc.returncode
    assert marker.exists()
    assert float(marker.read_text(encoding="utf-8")) >= 8.0


def test_create_fake_game_rejects_unsupported_source(tmp_path, monkeypatch):
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    monkeypatch.setattr(faker, "_find_source_exe", lambda: tmp_path / "pythonw.exe")
    monkeypatch.setattr(faker, "_source_runtime_problem",
                        lambda: "Python runtime files are missing")
    messages = []
    monkeypatch.setattr(faker, "print_color",
                        lambda text, *a, **k: messages.append(str(text)))

    result = faker.GameFaker().create_fake_game("game.exe", output_dir=tmp_path)

    assert result is None
    assert any("Python runtime files are missing" in message for message in messages)
    assert not (tmp_path / "game.exe").exists()


class _DeadPopen:
    returncode = 3221225781  # STATUS_DLL_NOT_FOUND

    def __init__(self, args, **kwargs):
        self.args = args

    def poll(self):
        return self.returncode


def test_launch_reports_failure_when_process_exits_immediately(tmp_path, monkeypatch):
    exe = tmp_path / "Dead.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(faker.subprocess, "Popen", _DeadPopen)
    monkeypatch.setattr(faker, "loading_animation", lambda *a, **k: None)
    monkeypatch.setattr(faker, "print_color", lambda *a, **k: None)

    assert faker.GameFaker().launch_executable(exe) is None

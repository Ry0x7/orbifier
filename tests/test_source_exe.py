import os
import subprocess
import sys
import time
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


def test_helper_failure_removes_the_written_exe(tmp_path, monkeypatch):
    """A fake without its timer script would die at launch, so it is removed."""
    source = tmp_path / "pythonw.exe"
    source.write_bytes(b"pythonw")
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_source_runtime_problem", lambda: None)
    monkeypatch.setattr(faker, "_source_runtime_files", lambda: [])
    monkeypatch.setattr(faker, "_source_tcl_dirs", lambda: (None, None))

    real_write_text = Path.write_text

    def guarded_write_text(self, *args, **kwargs):
        if self.name == faker.TIMER_SCRIPT:
            raise OSError("The file is in use by another process")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    target = tmp_path / "Game.exe"

    with pytest.raises(RuntimeError):
        faker.GameFaker().copy_exe_to(target)

    assert not target.exists()
    assert not faker._source_runtime_dir(tmp_path).exists()
    assert not list(tmp_path.glob("*.orbifier-tmp"))


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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows source-copy check")
def test_second_source_copy_reuses_runtime_without_copying(tmp_path, monkeypatch):
    """A second fake must not rewrite the DLLs a running first fake loaded.

    This is the WinError 32 regression: the copied runtime used to sit beside
    the exe, so the second copy tried to overwrite locked files.
    """
    instance = faker.GameFaker()
    first = tmp_path / "First.exe"
    instance.copy_exe_to(first)

    runtime_dir = faker._source_runtime_dir(tmp_path)
    assert runtime_dir.is_dir()

    handles = []
    writes = []
    try:
        for path in sorted(runtime_dir.iterdir()):
            if path.is_file():
                handles.append(path.open("rb"))

        original = faker.shutil.copy2

        def spy(source, destination, *args, **kwargs):
            writes.append(Path(destination))
            return original(source, destination, *args, **kwargs)

        monkeypatch.setattr(faker.shutil, "copy2", spy)

        second = tmp_path / "Second.exe"
        instance.copy_exe_to(second)
    finally:
        for handle in handles:
            handle.close()

    assert second.is_file()
    assert not any(runtime_dir in Path(write).parents for write in writes)
    assert faker._runtime_dir_ready(runtime_dir)


def _write_probe(path: Path) -> Path:
    path.write_text(
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        "import tkinter\n"
        "root = tkinter.Tk()\n"
        "root.withdraw()\n"
        "root.update()\n"
        "pathlib.Path(sys.argv[1]).write_text(str(tkinter.TkVersion), encoding='utf-8')\n"
        "time.sleep(float(sys.argv[2]))\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.skipif(sys.platform != "win32", reason="Windows source-copy check")
def test_copied_source_runtime_supports_two_live_fakes(tmp_path):
    pytest.importorskip("tkinter")
    if faker._source_runtime_problem() is not None:
        pytest.skip("source mode cannot build a runnable copy on this install")

    instance = faker.GameFaker()
    first = tmp_path / "First.exe"
    instance.copy_exe_to(first)
    probe = _write_probe(tmp_path / "probe.pyw")
    first_marker = tmp_path / "first.txt"

    first_proc = subprocess.Popen(
        [str(first), str(probe), str(first_marker), "30"],
        env=faker._source_launch_env(first),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not first_marker.exists():
            if first_proc.poll() is not None:
                pytest.fail(f"first fake exited early with code {first_proc.returncode}")
            time.sleep(0.1)
        assert first_marker.exists(), "first fake never imported tkinter"

        # The first fake is alive and holds its runtime DLLs open.
        second = tmp_path / "Second.exe"
        instance.copy_exe_to(second)
        second_marker = tmp_path / "second.txt"
        result = subprocess.run(
            [str(second), str(probe), str(second_marker), "0"],
            env=faker._source_launch_env(second),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        assert result.returncode == 0, result.returncode
        assert float(second_marker.read_text(encoding="utf-8")) >= 8.0
    finally:
        first_proc.terminate()
        try:
            first_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            first_proc.kill()
            first_proc.wait(timeout=10)


def test_conflicting_runtime_file_fails_with_actionable_error(tmp_path):
    sources = faker._source_runtime_files()
    if not sources:
        pytest.skip("no runtime files to conflict with on this platform")

    runtime_dir = faker._source_runtime_dir(tmp_path)
    runtime_dir.mkdir()
    source = sources[0]
    (runtime_dir / source.name).write_bytes(
        b"" if source.stat().st_size else b"x"
    )

    target = tmp_path / "Game.exe"
    with pytest.raises(RuntimeError) as caught:
        faker.GameFaker().copy_exe_to(target)

    assert str(runtime_dir) in str(caught.value)
    assert not target.exists()
    assert not list(tmp_path.glob("*.orbifier-tmp"))


def test_failed_exe_copy_removes_staged_file_and_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(faker, "_source_runtime_problem", lambda: None)
    monkeypatch.setattr(faker, "_source_runtime_files", lambda: [])
    monkeypatch.setattr(faker, "_source_tcl_dirs", lambda: (None, None))

    def failing_copy(source, destination, *args, **kwargs):
        raise PermissionError(13, "Access is denied", str(destination))

    monkeypatch.setattr(faker.shutil, "copy2", failing_copy)

    target = tmp_path / "Game.exe"
    with pytest.raises(RuntimeError) as caught:
        faker.GameFaker().copy_exe_to(target)

    assert "Could not create Game.exe" in str(caught.value)
    assert not target.exists()
    assert not list(tmp_path.glob("*.orbifier-tmp"))
    assert not faker._source_runtime_dir(tmp_path).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launch environment check")
def test_launch_env_searches_shared_runtime_dir(tmp_path):
    runtime_dir = faker._source_runtime_dir(tmp_path)
    tcl_dir = runtime_dir / faker.TCL_HELPER_DIR / "tcl8.6"
    tk_dir = runtime_dir / faker.TCL_HELPER_DIR / "tk8.6"
    tcl_dir.mkdir(parents=True)
    tk_dir.mkdir(parents=True)
    (runtime_dir / faker.RUNTIME_MARKER).write_text("ok", encoding="utf-8")
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")

    env = faker._source_launch_env(exe)

    assert env is not None
    assert env["PATH"].split(os.pathsep)[0] == str(runtime_dir)
    assert env["PYTHONPATH"] == str(runtime_dir)
    assert env["TCL_LIBRARY"] == str(tcl_dir)
    assert env["TK_LIBRARY"] == str(tk_dir)

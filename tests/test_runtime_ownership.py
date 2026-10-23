"""Ownership rules for the shared fake-game runtime folder in faker.py.

These tests never touch the real interpreter install: the runtime file list and
the Tcl/Tk script trees are replaced with small files under ``tmp_path``.
"""
import pytest

from orbifier import faker


@pytest.fixture
def runtime_sources(tmp_path, monkeypatch):
    """Stand-in runtime DLLs and Tcl/Tk trees for ``_ensure_source_runtime``."""
    source_root = tmp_path / "base"
    source_root.mkdir()

    files = []
    for name, payload in (
        ("python313.dll", b"python" * 8),
        ("python3.dll", b"py3" * 6),
        ("_tkinter.pyd", b"tkinter" * 4),
        ("zlib1.dll", b"zlib" * 5),
    ):
        path = source_root / name
        path.write_bytes(payload)
        files.append(path)

    tcl_dir = source_root / "tcl8.6"
    tcl_dir.mkdir()
    (tcl_dir / "init.tcl").write_text("tcl library", encoding="utf-8")
    tk_dir = source_root / "tk8.6"
    tk_dir.mkdir()
    (tk_dir / "tk.tcl").write_text("tk library", encoding="utf-8")

    monkeypatch.setattr(faker, "_source_runtime_files", lambda: list(files))
    monkeypatch.setattr(faker, "_source_tcl_dirs", lambda: (tcl_dir, tk_dir))
    return files


def _owned_pyvenv_text() -> str:
    text = faker._source_pyvenv_text()
    assert text is not None
    return text


def test_first_call_builds_shared_runtime_folder(tmp_path, runtime_sources):
    created = faker._ensure_source_runtime(tmp_path)

    runtime_dir = faker._source_runtime_dir(tmp_path)
    assert runtime_dir.is_dir()
    assert runtime_dir.name.startswith(faker.RUNTIME_DIR_PREFIX)
    assert faker._runtime_dir_ready(runtime_dir)

    for source in runtime_sources:
        assert (runtime_dir / source.name).read_bytes() == source.read_bytes()

    tcl_root = runtime_dir / faker.TCL_HELPER_DIR
    assert (tcl_root / "tcl8.6" / "init.tcl").is_file()
    assert (tcl_root / "tk8.6" / "tk.tcl").is_file()

    expected = {runtime_dir, runtime_dir / faker.RUNTIME_MARKER,
                tcl_root / "tcl8.6", tcl_root / "tk8.6"}
    expected.update(runtime_dir / source.name for source in runtime_sources)
    assert set(created) == expected


def test_second_call_reuses_runtime_without_touching_it(tmp_path, runtime_sources):
    faker._ensure_source_runtime(tmp_path)
    runtime_dir = faker._source_runtime_dir(tmp_path)

    dest = runtime_dir / runtime_sources[0].name
    dest.write_bytes(b"live copy in use")
    runtime_sources[0].unlink()  # a re-copy attempt would fail loudly

    assert faker._ensure_source_runtime(tmp_path) == []
    assert dest.read_bytes() == b"live copy in use"


def test_conflicting_runtime_file_fails_cleanly(tmp_path, runtime_sources):
    runtime_dir = faker._source_runtime_dir(tmp_path)
    runtime_dir.mkdir(parents=True)
    conflict = runtime_dir / runtime_sources[0].name
    conflict.write_bytes(b"different build")

    with pytest.raises(RuntimeError) as error:
        faker._ensure_source_runtime(tmp_path)

    assert str(runtime_dir) in str(error.value)
    assert conflict.read_bytes() == b"different build"
    assert not faker._runtime_dir_ready(runtime_dir)


def test_interrupted_copy_is_completed_without_rewriting_files(tmp_path, runtime_sources):
    runtime_dir = faker._source_runtime_dir(tmp_path)
    runtime_dir.mkdir(parents=True)
    present = runtime_dir / runtime_sources[0].name
    present.write_bytes(runtime_sources[0].read_bytes())  # same size, already copied

    created = faker._ensure_source_runtime(tmp_path)

    assert faker._runtime_dir_ready(runtime_dir)
    for source in runtime_sources:
        assert (runtime_dir / source.name).is_file()
    assert present not in created


def test_remove_owned_helpers_removes_app_files_and_runtime(tmp_path, runtime_sources):
    faker._ensure_source_runtime(tmp_path)
    runtime_dir = faker._source_runtime_dir(tmp_path)
    timer = tmp_path / faker.TIMER_SCRIPT
    timer.write_text(faker._TIMER_PYW_CODE, encoding="utf-8")
    pyvenv = tmp_path / faker.PYVENV_CFG
    pyvenv.write_text(_owned_pyvenv_text(), encoding="utf-8")
    user_dll = tmp_path / "python3.dll"
    user_dll.write_bytes(b"user file, not ours")

    removed = faker.remove_owned_helpers(tmp_path)

    assert set(removed) == {timer, pyvenv, runtime_dir}
    assert not timer.exists()
    assert not pyvenv.exists()
    assert not runtime_dir.exists()
    assert user_dll.read_bytes() == b"user file, not ours"


def test_remove_owned_helpers_preserves_a_user_pyvenv_config(tmp_path):
    config = tmp_path / faker.PYVENV_CFG
    config.write_text("home = C:\\Python311\ninclude-system-site-packages = false\n",
                      encoding="utf-8")

    assert faker.remove_owned_helpers(tmp_path) == []
    assert config.exists()


def test_remove_owned_helpers_keeps_runtime_while_a_fake_exe_remains(tmp_path, runtime_sources):
    faker._ensure_source_runtime(tmp_path)
    runtime_dir = faker._source_runtime_dir(tmp_path)
    timer = tmp_path / faker.TIMER_SCRIPT
    timer.write_text(faker._TIMER_PYW_CODE, encoding="utf-8")
    other_fake = tmp_path / "OtherGame.exe"
    other_fake.write_bytes(b"still running")

    removed = faker.remove_owned_helpers(tmp_path)

    assert removed == [timer]
    assert not timer.exists()
    assert runtime_dir.is_dir()
    assert other_fake.exists()


def test_tracked_paths_are_removed_even_when_content_is_not_app_owned(tmp_path):
    config = tmp_path / faker.PYVENV_CFG
    config.write_text("someone else's environment", encoding="utf-8")

    removed = faker.remove_owned_helpers(tmp_path, tracked={config})

    assert removed == [config]
    assert not config.exists()


def test_incomplete_runtime_is_repaired_before_reuse(tmp_path, runtime_sources):
    """A short-circuiting marker must not hide a missing DLL or Tcl script."""
    faker._ensure_source_runtime(tmp_path)
    runtime_dir = faker._source_runtime_dir(tmp_path)
    (runtime_dir / runtime_sources[0].name).unlink()
    (runtime_dir / faker.TCL_HELPER_DIR / "tcl8.6" / "init.tcl").unlink()

    assert faker._runtime_dir_ready(runtime_dir) is False
    created = faker._ensure_source_runtime(tmp_path)

    assert (runtime_dir / runtime_sources[0].name).is_file()
    assert (runtime_dir / faker.TCL_HELPER_DIR / "tcl8.6" / "init.tcl").is_file()
    assert faker._runtime_dir_ready(runtime_dir)
    # The folder itself is reused, so a rollback must not own it.
    assert runtime_dir not in created


def test_remove_owned_helpers_sweeps_staging_and_legacy_tcl(tmp_path):
    stale = tmp_path / "Game.exe.orbifier-tmp"
    stale.write_bytes(b"half copied exe")
    legacy_root = tmp_path / faker.TCL_HELPER_DIR
    (legacy_root / "tcl8.6").mkdir(parents=True)
    (legacy_root / "tcl8.6" / "init.tcl").write_text("tcl", encoding="utf-8")

    removed = faker.remove_owned_helpers(tmp_path)

    assert not stale.exists()
    assert not legacy_root.exists()
    assert set(removed) == {stale, legacy_root}


def test_owned_helpers_are_discovered_after_a_restart(tmp_path, runtime_sources, monkeypatch):
    source = tmp_path / "pythonw.exe"
    source.write_bytes(b"pythonw")
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_source_runtime_problem", lambda: None)
    target = faker.GameFaker().create_fake_game("Game.exe", output_dir=tmp_path)

    # A fresh instance has an empty created_helpers set, like after a restart.
    helpers = faker.GameFaker().owned_helpers(tmp_path)

    assert faker._source_runtime_dir(tmp_path) in helpers
    assert (tmp_path / faker.TIMER_SCRIPT).resolve() in helpers
    assert (tmp_path / faker.PYVENV_CFG).resolve() in helpers
    assert target not in helpers


def test_other_exe_remains_ignores_non_executables(tmp_path):
    (tmp_path / "notes.txt").write_text("not a game", encoding="utf-8")
    assert faker._other_exe_remains(tmp_path) is False

    (tmp_path / "Game.EXE").write_bytes(b"fake")
    assert faker._other_exe_remains(tmp_path) is True

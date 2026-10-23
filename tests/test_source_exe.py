from orbifier import faker


def test_source_exe_prefers_readable_executable(tmp_path, monkeypatch):
    alias_dir = tmp_path / "alias"
    alias_dir.mkdir()
    # The Windows Store app-execution alias exists but cannot be opened.
    (alias_dir / "pythonw.exe").mkdir()

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    real_pythonw = base_dir / "pythonw.exe"
    real_pythonw.write_bytes(b"pythonw")

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

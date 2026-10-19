from pathlib import Path

import pytest

from orbifier import faker


def test_custom_output_directory_creates_nested_executable(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_is_frozen", lambda: True)
    monkeypatch.setattr(faker, "loading_animation", lambda *a: None)
    instance = faker.GameFaker()
    target = instance.create_fake_game(r"Bin\game.exe", output_dir=tmp_path / "custom")
    assert target == tmp_path / "custom/Bin/game.exe"
    assert target.read_bytes() == b"placeholder"


def test_existing_executable_is_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    target = tmp_path / "game.exe"
    target.write_bytes(b"real game")
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    faker.GameFaker().copy_exe_to(target)
    assert target.read_bytes() == b"placeholder"


def test_existing_directory_as_target_is_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    target = tmp_path / "game.exe"
    target.mkdir()
    (target / "nested.txt").write_text("in the way")
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    faker.GameFaker().copy_exe_to(target)
    assert target.is_file()
    assert target.read_bytes() == b"placeholder"


def test_source_copy_preserves_existing_environment_config(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    output = tmp_path / "custom"
    output.mkdir()
    cfg = output / "pyvenv.cfg"
    cfg.write_text("existing environment")
    runtime = tmp_path / "runtime"
    (runtime / "Scripts").mkdir(parents=True)
    (runtime / "pyvenv.cfg").write_text("source environment")
    monkeypatch.setattr(faker.sys, "executable", str(runtime / "Scripts/python.exe"))
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    instance = faker.GameFaker()
    instance.copy_exe_to(output / "game.exe")
    assert cfg.read_text() == "existing environment"
    assert cfg not in instance.created_helpers


def test_source_copy_overwrites_existing_timer_script(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    helper = tmp_path / "_orbifier_timer.pyw"
    helper.write_text("unrelated content")
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    faker.GameFaker().copy_exe_to(tmp_path / "game.exe")
    assert helper.read_text(encoding="utf-8") == faker._TIMER_PYW_CODE
    assert (tmp_path / "game.exe").exists()


def test_delete_fake_game(tmp_path, monkeypatch):
    source = tmp_path / "source.exe"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(faker, "_find_source_exe", lambda: source)
    monkeypatch.setattr(faker, "_is_frozen", lambda: False)
    instance = faker.GameFaker()
    out = tmp_path / "output"
    target = instance.create_fake_game("Sub/game.exe", output_dir=out)
    assert target.exists()
    assert (out / "Sub/_orbifier_timer.pyw").exists()

    res = instance.delete_fake_game("Sub/game.exe", output_dir=out)
    assert res["executable"][1] is True
    assert not target.exists()
    assert not (out / "Sub").exists()

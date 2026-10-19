"""Tests for steam.py – pure functions only (no network calls)."""

from pathlib import Path
import pytest
from orbifier import steam

from orbifier.steam import (
    _pick_windows_exe, sanitize_installdir, sanitize_executable, steam_fake_exe_path,
)
from orbifier.textmatch import match_score, normalize, NO_MATCH, EXACT


class TestSanitize:
    def test_strips_trademarks_and_colon(self):
        assert sanitize_installdir("Call of Duty®: Modern Warfare® 4") == "Call of Duty Modern Warfare 4"

    def test_invalid_chars_and_trailing_dots(self):
        assert sanitize_installdir('A<b>c|d?e*"f. ') == "A b c d e f"

    def test_empty_falls_back(self):
        assert sanitize_installdir("™:?", "App1") == "App1"

    def test_reserved_name(self):
        assert sanitize_installdir("CON") == "_CON"

    def test_executable_keeps_subdirs(self):
        assert sanitize_executable("Bin\\Win64\\Game: X.exe") == "Bin/Win64/Game X.exe"

    def test_executable_blocks_traversal_and_adds_exe(self):
        assert sanitize_executable("../../evil") == "evil.exe"

    def test_fake_exe_path_valid(self):
        p = steam_fake_exe_path(Path("C:/Steam"), "Call of Duty®: Modern Warfare® 4", "Game.exe")
        assert p.parent.name == "Call of Duty Modern Warfare 4"
        assert ":" not in str(p)[2:]


class TestTextMatch:
    def test_normalize(self):
        assert normalize("Call of Duty®: Modern-Warfare™ 4") == "call of duty modern warfare 4"

    def test_punctuation_insensitive_exact(self):
        assert match_score("call of duty modern warfare 4", "Call of Duty®: Modern Warfare® 4") == EXACT

    def test_compact_match(self):
        assert match_score("spiderman", "Marvel's Spider-Man") != NO_MATCH

    def test_non_adjacent_words(self):
        assert match_score("cod warfare", "COD: Modern Warfare") != NO_MATCH

    def test_no_match(self):
        assert match_score("fortnite", "Minecraft") == NO_MATCH


class TestPickWindowsExe:
    def test_finds_first_windows_exe(self):
        launch = {
            "0": {
                "executable": "game.exe",
                "config": {"oslist": "windows"},
            },
            "1": {
                "executable": "game_server.exe",
                "config": {"oslist": "windows"},
            },
        }
        assert _pick_windows_exe(launch) == "game.exe"

    def test_skips_non_windows(self):
        launch = {
            "0": {
                "executable": "game.app",
                "config": {"oslist": "macos"},
            },
            "1": {
                "executable": "game.exe",
                "config": {"oslist": "windows"},
            },
        }
        assert _pick_windows_exe(launch) == "game.exe"

    def test_skips_non_exe(self):
        launch = {
            "0": {
                "executable": "game.sh",
                "config": {"oslist": "windows"},
            },
        }
        assert _pick_windows_exe(launch) is None

    def test_empty_launch(self):
        assert _pick_windows_exe({}) is None


class TestCustomSteamSetup:
    def test_cli_fc27_setup_writes_matching_manifest_and_executable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steam, "_resolve_steam_path", lambda: tmp_path / "steamapps")
        monkeypatch.setattr(steam, "fetch_steam_app_info", lambda appid: {
            "name": "EA SPORTS FC™ 27", "installdir": "EA SPORTS FC 27",
            "executable": "fc27.exe", "depot_id": None})
        answers = iter(["4080220", "EA SPORTS FC 27", r"..\EA SPORTS FC 27\fc27.exe", "", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        monkeypatch.setattr(steam, "ask_confirm", lambda: True)
        monkeypatch.setattr(steam, "loading_animation", lambda *a: None)
        launched = []

        class Placeholder:
            def copy_exe_to(self, path):
                path.parent.mkdir(parents=True)
                path.write_bytes(b"test placeholder")

            def launch_executable(self, path):
                launched.append(path)

        steam.steam_quest_mode(Placeholder())
        expected = tmp_path / "steamapps/common/EA SPORTS FC 27/fc27.exe"
        assert launched == [expected]
        assert expected.read_bytes() == b"test placeholder"
        manifest = tmp_path / "steamapps/appmanifest_4080220.acf"
        assert '"StateFlags"\t\t"4"' in manifest.read_text(encoding="utf-8")

    def test_cli_can_override_detected_library(self, tmp_path, monkeypatch):
        detected = tmp_path / "Steam"
        detected.mkdir()
        chosen = tmp_path / "OtherLibrary"
        monkeypatch.setattr(steam, "get_steam_path", lambda: detected)
        monkeypatch.setattr("builtins.input", lambda *a: str(chosen))
        assert steam._resolve_steam_path() == chosen

    def test_fc27_metadata_uses_actual_exe(self, monkeypatch):
        monkeypatch.setattr(steam, "loading_animation", lambda *a: None)
        monkeypatch.setattr(steam, "fetch_json", lambda *a: {
            "data": {"4080220": {"common": {"name": "EA SPORTS FC™ 27"},
                "config": {"installdir": "EA SPORTS FC 27", "launch": {
                    "0": {"executable": "link2ea://launch"}}}}}})
        assert steam.fetch_steam_app_info(4080220)["executable"] == "fc27.exe"

    def test_parent_relative_path_does_not_duplicate_folder(self, tmp_path):
        target = steam_fake_exe_path(tmp_path, "EA SPORTS FC 27",
                                     r"..\EA SPORTS FC 27\fc27.exe")
        assert target == tmp_path / "steamapps/common/EA SPORTS FC 27/fc27.exe"

    @pytest.mark.parametrize("exe", ["../../outside.exe", "../Other/game.exe",
                                      "C:/outside.exe", "//server/share/game.exe"])
    def test_rejects_path_outside_install_directory(self, tmp_path, exe):
        with pytest.raises(ValueError):
            steam_fake_exe_path(tmp_path, "Game", exe)

    def test_accepts_steamapps_or_library_root(self, tmp_path):
        expected = tmp_path / "steamapps/common/Game/game.exe"
        assert steam_fake_exe_path(tmp_path / "steamapps", "Game", "game.exe") == expected

    def test_minimal_installed_manifest_matches_instructions(self, tmp_path):
        path = steam.generate_appmanifest(4080220, "EA SPORTS FC™ 27", "EA SPORTS FC 27",
                                          tmp_path / "steamapps", manifest_mode="installed")
        assert path == tmp_path / "steamapps/appmanifest_4080220.acf"
        content = path.read_text(encoding="utf-8")
        assert '"StateFlags"\t\t"4"' in content
        assert '"name"\t\t"EA SPORTS FC™ 27"' in content
        assert '"installdir"\t\t"EA SPORTS FC 27"' in content
        assert "StagedDepots" not in content

    def test_legacy_manifest_is_still_available(self, tmp_path):
        path = steam.generate_appmanifest(123, "Game", "Game", tmp_path)
        assert '"StateFlags"\t\t"1026"' in path.read_text()

    def test_overwrites_existing_manifest(self, tmp_path):
        path = tmp_path / "steamapps/appmanifest_123.acf"
        path.parent.mkdir()
        path.write_text("existing installation")
        manifest = steam.generate_appmanifest(123, "Game", "Game", tmp_path)
        assert manifest == path
        assert '"appid"\t\t"123"' in path.read_text()
        assert "existing installation" not in path.read_text()

    def test_delete_steam_game(self, tmp_path):
        manifest = steam.generate_appmanifest(123, "Game", "GameDir", tmp_path)
        fake_exe = tmp_path / "steamapps/common/GameDir/game.exe"
        fake_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_exe.write_bytes(b"placeholder")
        helper = fake_exe.parent / "_orbifier_timer.pyw"
        helper.write_text("timer")

        res = steam.delete_steam_game(tmp_path, 123, "GameDir", "game.exe")
        assert res["manifest"][1] is True
        assert res["executable"][1] is True
        assert not manifest.exists()
        assert not fake_exe.exists()
        assert not helper.exists()
        assert not (tmp_path / "steamapps/common/GameDir").exists()

    def test_normalises_backslashes(self):
        launch = {
            "0": {
                "executable": "Bin\\Win64\\game.exe",
                "config": {"oslist": "windows"},
            },
        }
        assert _pick_windows_exe(launch) == "Bin/Win64/game.exe"

    def test_empty_oslist_counts_as_windows(self):
        launch = {
            "0": {
                "executable": "game.exe",
                "config": {"oslist": ""},
            },
        }
        assert _pick_windows_exe(launch) == "game.exe"

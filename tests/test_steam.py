"""Tests for steam.py – pure functions only (no network calls)."""

from pathlib import Path

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

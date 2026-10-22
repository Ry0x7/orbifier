"""Tests for discord_db.py – pure functions only (no network calls)."""

from orbifier.discord_db import DiscordGamesDB


def _make_db_with_games(games: list) -> DiscordGamesDB:
    """Create a DiscordGamesDB without hitting the network."""
    db = object.__new__(DiscordGamesDB)  # skip __init__
    db.games = games
    db.source = "test"
    return db


SAMPLE_GAMES = [
    {
        "id": "1",
        "name": "Minecraft",
        "aliases": ["MC"],
        "executables": [
            {"os": "win32", "name": "javaw.exe"},
            {"os": "win32", "name": ">Minecraft.Windows.exe"},
        ],
    },
    {
        "id": "2",
        "name": "Minecraft Dungeons",
        "aliases": [],
        "executables": [
            {"os": "win32", "name": "Dungeons.exe"},
            {"os": "linux", "name": "dungeons"},
        ],
    },
    {
        "id": "3",
        "name": "Fortnite",
        "aliases": ["FN", "Fort"],
        "executables": [
            {"os": "win32", "name": "FortniteClient-Win64-Shipping.exe"},
            {"os": "win32", "name": "FortniteClient-Win64-Shipping_BE.exe"},
            {"os": "win32", "name": "FortniteLauncher.exe"},
        ],
    },
]


class TestSearchGames:
    def test_exact_match_by_name(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        results = db.search_games("Minecraft")
        assert results[0]["id"] == "1"

    def test_exact_match_by_alias(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        results = db.search_games("MC")
        assert results[0]["id"] == "1"

    def test_partial_match(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        results = db.search_games("mine")
        assert len(results) == 2  # Minecraft + Minecraft Dungeons

    def test_no_results(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        results = db.search_games("nonexistent_game_xyz")
        assert results == []

    def test_ignores_punctuation_and_symbols(self):
        db = _make_db_with_games(SAMPLE_GAMES + [
            {"id": "4", "name": "Call of Duty®: Modern Warfare® III", "aliases": [], "executables": []},
        ])
        assert db.search_games("call of duty modern warfare")[0]["id"] == "4"
        assert db.search_games("Call-of-Duty: Modern Warfare III")[0]["id"] == "4"

    def test_exact_ranked_before_partial(self):
        db = _make_db_with_games(list(reversed(SAMPLE_GAMES)))
        assert db.search_games("minecraft")[0]["id"] == "1"

    def test_case_insensitive(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        results = db.search_games("fortnite")
        assert results[0]["id"] == "3"


class TestFilterWin32Exes:
    def test_returns_win32_only(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        exes = db.get_all_executables(SAMPLE_GAMES[1])  # Minecraft Dungeons
        assert "Dungeons.exe" in exes
        assert "dungeons" not in exes  # linux exe excluded

    def test_skips_anti_cheat_with_patterns(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        exe = db.get_win32_executable(SAMPLE_GAMES[2])  # Fortnite
        assert exe == "FortniteClient-Win64-Shipping.exe"
        # _BE and Launcher should be skipped
        all_exes = db.get_all_executables(SAMPLE_GAMES[2])
        assert "FortniteClient-Win64-Shipping_BE.exe" in all_exes  # all includes them

    def test_strips_leading_gt(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        all_exes = db.get_all_executables(SAMPLE_GAMES[0])
        assert "Minecraft.Windows.exe" in all_exes
        assert ">Minecraft.Windows.exe" not in all_exes


COD_GAMES = [
    {
        "id": "1511443377927880775",
        "name": "Call of Duty: Modern Warfare 4",
        "aliases": [],
        "executables": [
            {"os": "win32", "name": "sp26-cod.exe"},
            {"os": "win32", "name": "cod26-cod.exe"},
        ],
    },
    {
        "id": "bo6",
        "name": "Call of Duty: Black Ops 6",
        "aliases": ["Call of Duty"],
        "executables": [{"os": "win32", "name": "cod.exe"}],
    },
    {
        "id": "bo7",
        "name": "Call of Duty: Black Ops 7",
        "aliases": [],
        "executables": [{"os": "win32", "name": "bo7.exe"}],
    },
    {
        "id": "1539812812854132867",
        "name": "Call of Duty",
        "aliases": [],
        "executables": [{"os": "win32", "name": "cod.exe"}],
    },
]


class TestSearchRanking:
    def test_call_of_duty_exact_name_first_and_mw4_listed(self):
        db = _make_db_with_games(COD_GAMES)
        results = db.search_games("call of duty")
        ids = [g["id"] for g in results]
        assert ids[0] == "1539812812854132867"
        assert ids[1] == "bo6"  # exact alias ranks right after exact name
        assert "1511443377927880775" in ids

    def test_modern_warfare_4_returns_mw4_first(self):
        db = _make_db_with_games(COD_GAMES)
        assert db.search_games("modern warfare 4")[0]["id"] == "1511443377927880775"

    def test_full_name_returns_mw4_first(self):
        db = _make_db_with_games(COD_GAMES)
        results = db.search_games("Call of Duty: Modern Warfare 4")
        assert results[0]["id"] == "1511443377927880775"

    def test_token_match(self):
        db = _make_db_with_games(COD_GAMES)
        ids = [g["id"] for g in db.search_games("duty warfare")]
        assert ids == ["1511443377927880775"]

    def test_cap_applied_after_ranking(self, monkeypatch):
        from orbifier import config
        monkeypatch.setattr(config, "MAX_SEARCH_RESULTS", 5)
        filler = [
            {"id": f"f{i}", "name": f"Call of Duty Filler {i}", "aliases": [], "executables": []}
            for i in range(10)
        ]
        db = _make_db_with_games(filler + [COD_GAMES[3]])
        results = db.search_games("call of duty")
        assert len(results) == 5
        assert results[0]["id"] == "1539812812854132867"


class TestGetGameByAppId:
    def test_accepts_string_and_int(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        assert db.get_game_by_app_id("1")["name"] == "Minecraft"
        assert db.get_game_by_app_id(2)["name"] == "Minecraft Dungeons"

    def test_returns_none_for_unknown_or_missing(self):
        db = _make_db_with_games(SAMPLE_GAMES)
        assert db.get_game_by_app_id("999") is None
        assert db.get_game_by_app_id(None) is None

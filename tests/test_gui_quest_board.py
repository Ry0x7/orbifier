"""Tk-level tests for the Quest Board screen (no network or launching)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from orbifier import gui
from orbifier.quest_board import QuestBoard, QuestInfo, RegionAvailability

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
KNOWN = frozenset({"DE", "FR", "US"})


class FakeDB:
    def __init__(self):
        self.games = {
            "111": {"id": "111", "name": "US Game",
                    "executables": [{"os": "win32", "name": "usgame.exe"}]},
            "222": {"id": "222", "name": "DE Game",
                    "executables": [{"os": "win32", "name": "degame.exe"}]},
            "333": {"id": "333", "name": "Global Game",
                    "executables": [{"os": "win32", "name": "global.exe"}]},
            "444": {"id": "444", "name": "Video Game",
                    "executables": [{"os": "win32", "name": "video.exe"}]},
        }

    def get_game_by_app_id(self, app_id):
        return self.games.get(str(app_id))

    def get_win32_executable(self, game):
        for exe in game.get("executables", []):
            if exe.get("os") == "win32":
                return exe["name"]
        return None

    def _filter_win32_exes(self, game, skip_patterns=True):
        return [
            exe["name"] for exe in game.get("executables", [])
            if exe.get("os") == "win32"
        ]


def make_quest(qid, name, app_id, *, tasks=("PLAY_ON_DESKTOP",),
               is_global=False, include=(), exclude=()):
    if is_global:
        availability = RegionAvailability(True, frozenset(), KNOWN)
    elif include:
        availability = RegionAvailability(False, frozenset(include), KNOWN)
    else:
        availability = RegionAvailability(
            False, KNOWN - frozenset(exclude), KNOWN, exclude_based=True
        )
    return QuestInfo(
        quest_ids=(qid,),
        name=name,
        app_name=f"{name} Game",
        app_id=app_id,
        reward="100 Orbs",
        tasks=frozenset(tasks),
        starts_at=None,
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        availability=availability,
    )


@pytest.fixture(scope="module")
def app(gui_app):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gui_app, "ensure_quests_loaded", lambda force=False: None)
    monkeypatch.setattr(gui_app, "ensure_db_loaded", lambda: None)
    yield gui_app
    monkeypatch.undo()


@pytest.fixture
def board():
    return QuestBoard(
        quests=(
            make_quest("1", "US Quest", "111", include=("US",)),
            make_quest("2", "DE Quest", "222", include=("DE",)),
            make_quest("3", "Global Quest", "333", is_global=True),
            make_quest("4", "Video Quest", "444", tasks=("WATCH_VIDEO",), include=("DE",)),
        ),
        regions=tuple(sorted(KNOWN)),
        fetched_at=NOW,
    )


def load_board(app, board):
    app.quest_board_data = board
    app.db = FakeDB()
    app.db_loading = False
    app._rebuild_quest_region_menu(board)
    app._refresh_quest_list()


def test_quest_board_screen_fits_window(app):
    long_name = "A Very Long Quest Name That Still Has To Wrap Correctly " * 2
    load_board(
        app,
        QuestBoard(
            quests=(make_quest("long", long_name, "111", is_global=True),),
            regions=tuple(sorted(KNOWN)),
            fetched_at=NOW,
        ),
    )
    app.show("quests")
    app._resize_quest_detail(SimpleNamespace(width=gui.WIN_W))
    app.root.update_idletasks()
    screen = app.screens["quests"]
    assert screen.winfo_reqwidth() <= gui.WIN_W, screen.winfo_reqwidth()

    app._resize_quest_detail(SimpleNamespace(width=gui.DEFAULT_W))
    app.root.update_idletasks()
    assert screen.winfo_reqwidth() <= gui.DEFAULT_W, screen.winfo_reqwidth()
    assert screen.winfo_reqheight() <= gui.HOST_H, screen.winfo_reqheight()


def test_home_grid_has_quest_board_button(app):
    assert "quests" in app.home_buttons
    assert app.screens["quests"] is not None


def test_populated_board_defaults_to_desktop_only(app, board):
    load_board(app, board)
    assert app.quest_desktop_only.get()
    assert app.quest_list.size() == 3
    labels = [app.quest_list.get(i) for i in range(app.quest_list.size())]
    assert any("US QUEST" in label for label in labels)
    assert any("DE QUEST" in label for label in labels)
    assert any("GLOBAL QUEST" in label for label in labels)
    assert not any("VIDEO QUEST" in label for label in labels)
    assert "1 hidden" in app.quest_status_var.get()


def test_region_filter_changes_visible_rows(app, board):
    load_board(app, board)

    app._set_quest_region("US")
    labels = [app.quest_list.get(i) for i in range(app.quest_list.size())]
    assert len(labels) == 2
    assert any("US QUEST" in label for label in labels)
    assert any("GLOBAL QUEST" in label for label in labels)
    assert not any("DE QUEST" in label for label in labels)

    app._set_quest_region("DE")
    labels = [app.quest_list.get(i) for i in range(app.quest_list.size())]
    assert len(labels) == 2
    assert any("DE QUEST" in label for label in labels)
    assert any("GLOBAL QUEST" in label for label in labels)
    assert not any("US QUEST" in label for label in labels)

    app.quest_desktop_only.set(False)
    app._refresh_quest_list()
    labels = [app.quest_list.get(i) for i in range(app.quest_list.size())]
    assert len(labels) == 3
    assert any("VIDEO QUEST" in label and "OTHER" in label for label in labels)


def test_selection_updates_detail_and_launch_state(app, board):
    load_board(app, board)
    app._set_quest_region("US")
    for index in range(app.quest_list.size()):
        if "US QUEST" in app.quest_list.get(index):
            app.quest_list.selection_clear(0, "end")
            app.quest_list.selection_set(index)
            break
    app._quest_selection_changed()

    assert "US Quest" in app.quest_detail_var.get()
    assert "usgame.exe" in app.quest_detail_var.get()
    assert app.quest_launch_btn.enabled


def test_unsupported_quest_is_blocked(app, board, monkeypatch):
    load_board(app, board)
    app.quest_desktop_only.set(False)
    app._set_quest_region("DE")
    app._refresh_quest_list()

    for index in range(app.quest_list.size()):
        if "VIDEO QUEST" in app.quest_list.get(index):
            app.quest_list.selection_clear(0, "end")
            app.quest_list.selection_set(index)
            break
    app._quest_selection_changed()

    confirmations = []
    monkeypatch.setattr(gui.messagebox, "askyesno",
                        lambda *a, **kw: confirmations.append(a) or False)
    app.quest_launch()

    assert not app.quest_launch_btn.enabled
    assert confirmations == []


def test_unresolved_app_id_is_blocked(app, monkeypatch):
    board = QuestBoard(
        quests=(make_quest("missing", "Missing Game", "999", is_global=True),),
        regions=tuple(sorted(KNOWN)),
        fetched_at=NOW,
    )
    load_board(app, board)
    app.quest_list.selection_set(0)
    app._quest_selection_changed()

    confirmations = []
    monkeypatch.setattr(gui.messagebox, "askyesno",
                        lambda *a, **kw: confirmations.append(a) or False)
    app.quest_launch()

    assert "Not found in Discord's detectable database" in app.quest_detail_var.get()
    assert not app.quest_launch_btn.enabled
    assert confirmations == []


def test_find_game_opens_database(app, board):
    load_board(app, board)
    app.quest_list.selection_set(0)
    app._quest_selection_changed()

    app.quest_find_game()

    assert app.current == "database"
    assert app.db_query.get() == app.quest_board_results[0].app_name

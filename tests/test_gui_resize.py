"""Tk tests for the resizable window and expandable result lists."""
from types import SimpleNamespace

import pytest

from orbifier import gui


@pytest.fixture(scope="module")
def app(gui_app):
    return gui_app


@pytest.mark.parametrize(
    ("screen", "expected"),
    [
        ((1920, 1080), (900, 640)),
        ((1280, 720), (900, 600)),
        ((800, 600), (800, 560)),
    ],
)
def test_initial_window_size_clamps_to_display(screen, expected):
    assert gui.initial_window_size(*screen) == expected


def test_window_is_resizable_with_minimum_size(app):
    assert all(app.root.resizable())
    assert app.root.minsize() == (gui.WIN_W, gui.WIN_H)
    assert int(app.host.pack_info()["expand"]) == 1
    assert int(app.log_wrap.pack_info()["expand"]) == 0
    assert int(app.status_bar.pack_info()["expand"]) == 0


def test_result_lists_expand_vertically(app):
    for widget in (app.quest_list, app.db_list, app.steam_list):
        assert int(widget.pack_info()["expand"]) == 1


def test_quest_detail_rewraps_to_width(app):
    app._resize_quest_detail(SimpleNamespace(width=1000))
    assert int(app.quest_detail_label.cget("wraplength")) == 952

    app._resize_quest_detail(SimpleNamespace(width=200))
    assert int(app.quest_detail_label.cget("wraplength")) == 400

    app._resize_quest_detail(SimpleNamespace(width=gui.DEFAULT_W))

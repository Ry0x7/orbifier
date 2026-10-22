"""Pure tests for the Quest Board data layer (no network calls)."""
from datetime import datetime, timezone

import pytest

from orbifier import config
from orbifier.errors import QuestBoardError
from orbifier.quest_board import (
    RegionAvailability,
    build_quest_board,
    load_quest_board,
)

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
LONG_AGO = "2025-01-01T00:00:00+00:00"
FAR = "2030-01-01T00:00:00+00:00"


def make_quest(
    qid,
    *,
    name="Test Quest",
    app_id="123",
    app_name="Test Game",
    reward="100 Orbs",
    starts="2026-01-01T00:00:00+00:00",
    expires=FAR,
    tasks=("PLAY_ON_DESKTOP",),
    age_gate=False,
):
    return {
        "id": qid,
        "config": {
            "application": {"id": app_id, "name": app_name},
            "messages": {"quest_name": name},
            "rewards_config": {"rewards": [{"messages": {"name": reward}}]},
            "task_config_v2": {"tasks": {task: {"type": task} for task in tasks}},
            "starts_at": starts,
            "expires_at": expires,
            "show_age_gate": age_gate,
        },
    }


def make_region(qid, *, include=(), exclude=(), is_global=False, age=False):
    return {
        "id": qid,
        "is_global": is_global,
        "show_age_gate": age,
        "regions": {"include": list(include), "exclude": list(exclude)},
    }


def known_entries(*codes):
    """Region entries that only exist to publish the known-region set."""
    return [make_region(f"known-{code}", include=[code]) for code in codes]


def build(quests, regions=(), now=NOW):
    return build_quest_board({"quests": quests}, {"quests": list(regions)}, now=now)


def test_active_window_filters_future_and_expired():
    board = build([
        make_quest("active", name="Active"),
        make_quest("future", name="Future", starts="2027-01-01T00:00:00+00:00"),
        make_quest("expired", name="Expired", expires="2026-05-31T00:00:00+00:00"),
    ])
    assert [q.name for q in board.quests] == ["Active"]


def test_missing_dates_are_treated_as_active():
    board = build([
        make_quest("no-dates", name="No Dates", starts=None, expires=None),
    ])
    assert [q.name for q in board.quests] == ["No Dates"]
    assert board.quests[0].expires_label() == "NO END"


def test_missing_region_entry_is_global():
    board = build([make_quest("1")])
    quest = board.quests[0]
    assert quest.availability.is_global
    assert quest.availability.label() == "GLOBAL"
    assert quest.availability.available_in("DE")


def test_global_include_and_exclude_rules():
    board = build(
        [
            make_quest("missing", name="Missing"),
            make_quest("global", name="Global"),
            make_quest("us", name="US"),
            make_quest("not-de", name="Not DE"),
            make_quest("us-de", name="US and DE"),
        ],
        known_entries("US", "DE", "FR")
        + [
            make_region("global", is_global=True),
            make_region("us", include=["US"]),
            make_region("not-de", exclude=["DE"]),
            make_region("us-de", include=["US", "DE"], exclude=["DE"]),
        ],
    )
    by_name = {q.name: q for q in board.quests}

    assert by_name["Missing"].availability.label() == "GLOBAL"
    assert by_name["Global"].availability.label() == "GLOBAL"
    assert by_name["US"].availability.label() == "US"
    assert by_name["US"].availability.available_in("US")
    assert not by_name["US"].availability.available_in("DE")
    assert by_name["Not DE"].availability.label() == "GLOBAL EXCEPT DE"
    assert by_name["Not DE"].availability.available_in("US")
    assert not by_name["Not DE"].availability.available_in("DE")
    assert by_name["US and DE"].availability.label() == "US"


def test_group_merges_regional_variants_and_unions_availability():
    board = build(
        [
            make_quest("1", name="Grouped", app_id="999"),
            make_quest("2", name="Grouped", app_id="999"),
            make_quest("3", name="Grouped", app_id="999"),
            make_quest("4", name="Partial", app_id="998"),
            make_quest("5", name="Partial", app_id="998"),
        ],
        known_entries("US", "DE", "FR")
        + [
            make_region("1", include=["US"]),
            make_region("2", include=["DE"]),
            make_region("3", include=["FR"]),
            make_region("4", include=["US"]),
            make_region("5", include=["DE"]),
        ],
    )
    by_name = {q.name: q for q in board.quests}

    grouped = by_name["Grouped"]
    assert grouped.variant_count == 3
    assert set(grouped.quest_ids) == {"1", "2", "3"}
    assert grouped.availability.is_global
    assert grouped.availability.label() == "GLOBAL"

    partial = by_name["Partial"]
    assert partial.variant_count == 2
    assert partial.availability.label() == "DE, US"
    assert partial.availability.available_in("US")
    assert partial.availability.available_in("DE")
    assert not partial.availability.available_in("FR")


def test_group_covering_all_known_regions_becomes_global():
    board = build(
        [
            make_quest("1", name="Clean Crew", app_id="777"),
            make_quest("2", name="Clean Crew", app_id="777"),
            make_quest("3", name="Clean Crew", app_id="777"),
            make_quest("4", name="Clean Crew", app_id="777"),
        ],
        known_entries("US", "DE", "FR")
        + [
            make_region("1", exclude=["US", "DE", "FR"]),
            make_region("2", include=["US"]),
            make_region("3", include=["DE"]),
            make_region("4", include=["FR"]),
        ],
    )
    quest = board.quests[0]
    assert quest.name == "Clean Crew"
    assert quest.variant_count == 4
    assert quest.availability.is_global
    assert quest.availability.label() == "GLOBAL"


def test_desktop_only_filter_and_supported_flag():
    board = build([
        make_quest("desktop", name="Desktop", tasks=("PLAY_ON_DESKTOP",)),
        make_quest("video", name="Video", tasks=("WATCH_VIDEO",)),
        make_quest("both", name="Both", tasks=("PLAY_ON_DESKTOP", "WATCH_VIDEO")),
    ])
    by_name = {q.name: q for q in board.quests}

    assert by_name["Desktop"].supported
    assert by_name["Both"].supported
    assert not by_name["Video"].supported
    assert [q.name for q in board.filter(desktop_only=True)] == ["Both", "Desktop"]
    assert [q.name for q in board.filter(desktop_only=False)] == ["Both", "Desktop", "Video"]


def test_region_filter_all_global_and_country():
    board = build(
        [
            make_quest("global", name="Global"),
            make_quest("us", name="US Only"),
            make_quest("de", name="DE Only"),
        ],
        known_entries("US", "DE", "FR")
        + [
            make_region("global", is_global=True),
            make_region("us", include=["US"]),
            make_region("de", include=["DE"]),
        ],
    )
    assert {q.name for q in board.filter("ALL")} == {"Global", "US Only", "DE Only"}
    assert [q.name for q in board.filter("GLOBAL")] == ["Global"]
    assert {q.name for q in board.filter("US")} == {"Global", "US Only"}
    assert [q.name for q in board.filter("FR")] == ["Global"]
    assert {q.name for q in board.filter("us")} == {"Global", "US Only"}


def test_region_label_variants():
    known = frozenset({"US", "CA", "DE", "FR", "IT", "ES", "PL", "UK"})
    assert RegionAvailability(True, frozenset(), known).label() == "GLOBAL"
    assert RegionAvailability(False, frozenset({"US"}), known).label() == "US"
    assert RegionAvailability(False, frozenset({"US", "CA"}), known).label() == "CA, US"
    assert (
        RegionAvailability(False, frozenset({"US", "CA", "DE", "FR", "IT", "ES"}), known).label()
        == "GLOBAL EXCEPT PL, UK"
    )
    assert (
        RegionAvailability(
            False,
            frozenset({"US", "CA", "DE", "FR", "IT", "ES"}),
            frozenset({"US", "CA", "DE", "FR", "IT", "ES"}),
        ).label()
        == "CA, DE, ES, FR, IT, US"
    )
    assert (
        RegionAvailability(
            False,
            frozenset({f"R{i}" for i in range(7)}),
            frozenset({f"R{i}" for i in range(20)}),
        ).label()
        == "7 REGIONS"
    )
    assert RegionAvailability(False, known - {"DE", "FR"}, known).label() == "GLOBAL EXCEPT DE, FR"
    assert RegionAvailability(False, frozenset(), known).label() == "UNAVAILABLE"


def test_malformed_entries_are_skipped():
    board = build([
        None,
        {},
        {"id": "bad-config", "config": {}},
        make_quest("good", name="Good"),
    ])
    assert [q.name for q in board.quests] == ["Good"]
    assert board.skipped == 3


def test_empty_payload_raises_quest_board_error():
    with pytest.raises(QuestBoardError):
        build([])


def test_load_quest_board_uses_injected_fetcher():
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append(url)
        assert kwargs["timeout"] == config.QUEST_API_TIMEOUT
        if url == config.DISCORD_QUEST_API_URL:
            return {"quests": [make_quest("1", name="Fetched")]}
        return {"quests": []}

    board = load_quest_board(fetcher=fake_fetch, now=NOW)
    assert [q.name for q in board.quests] == ["Fetched"]
    assert calls == [
        config.DISCORD_QUEST_API_URL,
        config.DISCORD_QUEST_REGIONS_URL,
    ]

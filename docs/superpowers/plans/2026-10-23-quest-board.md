# Quest Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a read-only Quest Board screen that lists active Discord quests across regions and launches supported desktop quests through Orbifier's existing fake-process flow.

**Architecture:** A new pure-data `orbifier/quest_board.py` fetches and normalizes the public DiscordQuest dataset, groups regional variants, and exposes filtering. `gui.py` adds one screen, one home entry, and launch handlers that reuse `_create_and_launch`; `discord_db.py` gains an app-id lookup.

**Tech Stack:** Python 3, `requests`, Tkinter, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-quest-board-design.md`

**Status:** Implemented and verified on 2026-10-23. `python -m pytest tests -q` in the project venv: 103 passed. Live smoke test loaded 32 grouped campaigns (10 desktop) from 37 region codes. Released as `v1.5.0`.

## Global Constraints

- Windows-first Tk app, 800×560 window, 392 px screen host.
- Only `requests` beyond the Python standard library.
- Network/file/launch work stays off the Tk main thread via `run_task`.
- No Discord token, login, VPN/proxy, region bypass, or auto-claiming.
- The public dataset is unofficial; credit `discordquest.com` and never imply guaranteed eligibility.
- Keep the CLI untouched and all existing tests passing.
- Cache the board in memory only; no disk cache.

## Review Focus

- Timezone-aware ISO parsing and the active window (`start <= now < expiry`).
- Region-rule merging, especially many regional ids for one campaign collapsing correctly.
- Malformed/renamed API fields: skip bad entries, fail clearly when nothing usable remains.
- No blocking network work on the Tk thread; stale data must remain usable after a failed refresh.
- App-id/executable resolution and launch guards for unsupported or unresolved quests.

## File Structure

- `orbifier/quest_board.py` (new) — dataclasses, parsing, grouping, region/filter logic, loader.
- `tests/test_quest_board.py` (new) — pure data tests, no network.
- `orbifier/discord_db.py` — `get_game_by_app_id`.
- `tests/test_discord_db.py` — lookup tests.
- `orbifier/config.py` — quest endpoints, cache TTL, timeout.
- `orbifier/errors.py` — `QuestBoardError`.
- `orbifier/gui.py` — home grid, Quest Board screen, load/refresh/launch handlers.
- `tests/test_gui_quest_board.py` (new) — screen fit, filtering, selection, launch guard.
- `orbifier/ui.py` — credits line for the data source.
- `README.md` — feature, limits, source, project layout.

---

### Task 1: Quest data model and loader

**Files:**
- Create: `orbifier/quest_board.py`
- Create: `tests/test_quest_board.py`
- Modify: `orbifier/config.py`
- Modify: `orbifier/errors.py`

**Interfaces:**
- Consumes: `config.DISCORD_QUEST_API_URL`, `config.DISCORD_QUEST_REGIONS_URL`, `config.QUEST_API_TIMEOUT`, `fetch_json`, `QuestBoardError`.
- Produces:
  - `QuestInfo` frozen dataclass: `quest_ids`, `name`, `app_name`, `app_id`, `reward`, `tasks`, `starts_at`, `expires_at`, `availability`, `age_gate`; properties `supported`, `variant_count`, `expires_label()`.
  - `RegionAvailability` frozen dataclass: `is_global`, `regions`, `known_regions`; methods `available_in(code)`, `label()`.
  - `QuestBoard` frozen dataclass: `quests`, `regions`, `fetched_at`, `skipped`; method `filter(region="ALL", desktop_only=True) -> list[QuestInfo]`.
  - `build_quest_board(quests_payload, regions_payload, now=None) -> QuestBoard`.
  - `load_quest_board(fetcher=fetch_json, now=None) -> QuestBoard`.
  - `SUPPORTED_TASKS = frozenset({"PLAY_ON_DESKTOP"})`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_quest_board.py` with fixtures and these tests:

```python
def test_active_window_filters_future_and_expired()
def test_missing_dates_are_treated_as_active()
def test_missing_region_entry_is_global()
def test_global_include_and_exclude_rules()
def test_group_merges_regional_variants_and_unions_availability()
def test_group_covering_all_known_regions_becomes_global()
def test_desktop_only_filter_and_supported_flag()
def test_region_filter_all_global_and_country()
def test_region_label_variants()
def test_malformed_entries_are_skipped()
def test_empty_payload_raises_quest_board_error()
def test_load_quest_board_uses_injected_fetcher()
```

Assertions must pin: only active quests remain; missing dates stay; no rule/global means available everywhere; include/exclude produce the expected set; grouped variant count and union; `Clean Crew`-style variants become global; `PLAY_ON_DESKTOP` is supported and `WATCH_VIDEO` is not; `ALL`/`GLOBAL`/country filters; labels `GLOBAL`, `US`, `US, CA`, `7 REGIONS`, `GLOBAL EXCEPT DE, FR`, `UNAVAILABLE`; malformed entries increment `skipped`; empty input raises `QuestBoardError`; the injected fetcher is called for both URLs.

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_quest_board.py -q`
Expected: collection/import failure because `orbifier.quest_board` does not exist.

- [x] **Step 3: Add config and error types**

In `orbifier/config.py`, under the network endpoints:

```python
DISCORD_QUEST_API_URL     = "https://api.discordquest.com/api/quests"
DISCORD_QUEST_REGIONS_URL = "https://api.discordquest.com/api/regions"
```

Under HTTP settings:

```python
QUEST_API_TIMEOUT   = 20
QUEST_CACHE_SECONDS = 300
```

In `orbifier/errors.py`:

```python
class QuestBoardError(OrbifierError):
    """Quest board data could not be loaded or parsed."""
```

- [x] **Step 4: Implement `orbifier/quest_board.py`**

Use the exact interfaces above. Parsing rules:

- Outer entry: `{id, config}`; read app from `config.application`, name from
  `config.messages.quest_name` (fall back to `messages.name`), reward from the first
  `config.rewards_config.rewards[].messages.name`, tasks from
  `task_config_v2.tasks` then `task_config.tasks`, times from `starts_at`/`expires_at`.
- Skip entries without a usable id/name/app id; count them in `skipped`.
- Region entry lookup by string quest id. Missing entry, `is_global`, or empty
  include/exclude means global. Include minus exclude otherwise; no include means
  all known regions minus exclude.
- Known region codes are collected from every region entry's include/exclude lists.
- Group by `(name.casefold(), app_id, reward.casefold(), expires_at, frozenset(tasks))`.
  Merge ids, tasks, and region availability; a group is global if any variant is
  global or the union covers every known region. `age_gate` is OR across variants.
- Only `PLAY_ON_DESKTOP` is supported; other tasks remain visible when the desktop
  filter is off.
- `filter()` sorts supported quests first, then case-insensitive name; a country
  filter keeps global quests and quests listing that country; `GLOBAL` keeps only
  global quests; `ALL` keeps everything that passes the desktop filter.
- Raise `QuestBoardError` when the quest payload is not a list or no usable active
  quests remain.

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_quest_board.py -q`
Expected: all tests pass.

- [x] **Step 6: Commit**

```bash
git add orbifier/quest_board.py orbifier/config.py orbifier/errors.py tests/test_quest_board.py
git commit -m "Add quest board data model and region logic"
```

---

### Task 2: Discord app-id lookup

**Files:**
- Modify: `orbifier/discord_db.py`
- Modify: `tests/test_discord_db.py`

**Interfaces:**
- Consumes: `DiscordGamesDB.games`.
- Produces: `DiscordGamesDB.get_game_by_app_id(app_id) -> dict | None`.

- [x] **Step 1: Write the failing tests**

Add to `tests/test_discord_db.py`:

```python
def test_get_game_by_app_id_accepts_string_and_int()
def test_get_game_by_app_id_returns_none_for_unknown_or_missing()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_discord_db.py -q`
Expected: FAIL because the method does not exist.

- [x] **Step 3: Implement the lookup**

```python
def get_game_by_app_id(self, app_id) -> dict | None:
    """Return the game whose Discord application id matches *app_id*."""
    if app_id is None:
        return None
    key = str(app_id)
    for game in self.games:
        if str(game.get("id")) == key:
            return game
    return None
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_discord_db.py -q`
Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add orbifier/discord_db.py tests/test_discord_db.py
git commit -m "Add Discord app-id lookup for quest launches"
```

---

### Task 3: Quest Board GUI

**Files:**
- Modify: `orbifier/gui.py`
- Create: `tests/test_gui_quest_board.py`

**Interfaces:**
- Consumes: `QuestBoard`, `QuestInfo`, `load_quest_board`, `DiscordGamesDB.get_game_by_app_id`, `config.QUEST_CACHE_SECONDS`, existing `run_task`, `_create_and_launch`, `_screen`, `_row`, `_label`, `_entry`, `_listbox`.
- Produces:
  - `OrbifierApp._build_quests() -> tk.Frame`
  - `OrbifierApp._on_show_quests()`
  - `OrbifierApp.ensure_quests_loaded(force=False)`
  - `OrbifierApp.quest_refresh()`
  - `OrbifierApp._refresh_quest_list()`
  - `OrbifierApp._quest_selection_changed(_event=None)`
  - `OrbifierApp._selected_quest() -> QuestInfo | None`
  - `OrbifierApp.quest_launch()`
  - `OrbifierApp.quest_find_game()`
  - Screen key `"quests"`, widgets `quest_list`, `quest_detail_var`, `quest_status_var`, `quest_region_var`, `quest_desktop_only`, `quest_launch_btn`, `quest_find_btn`.

- [x] **Step 1: Write the failing GUI tests**

Create `tests/test_gui_quest_board.py` with a hidden Tk app fixture, monkeypatched `ensure_quests_loaded`/`ensure_db_loaded`, and a synthetic `QuestBoard`. Tests:

```python
def test_quest_board_screen_fits_window(app)
def test_home_grid_has_quest_board_button(app)
def test_populated_board_defaults_to_desktop_only(app)
def test_region_filter_changes_visible_rows(app)
def test_selection_updates_detail_and_launch_state(app)
def test_unsupported_quest_is_blocked(app)
```

Set `app.quest_board_data` directly, call `app._refresh_quest_list()`, and assert listbox contents, detail text, and `quest_launch_btn.enabled`. For the blocked-launch test, monkeypatch `messagebox.askyesno` and assert it is not called.

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gui_quest_board.py -q`
Expected: FAIL because the screen and attributes do not exist.

- [x] **Step 3: Implement the screen and home entry**

In `OrbifierApp.__init__` initialize:

```python
self.quest_board_data = None
self.quest_board_loading = False
self.quest_board_fetched_at = 0.0
self.quest_board_results = []
```

Add `"quests": self._build_quests()` to `self.screens` and change the home grid to
three columns × two rows with 240×48 scale-2 buttons:

`DATABASE QUEST`, `QUEST BOARD`, `MANUAL EXE`, `STEAM QUEST`, `ACTIVE QUESTS`,
`CREDITS`. Keep the existing colors for old entries; use `MAGENTA` for the board and
`GREEN` for active.

Build the screen with `_screen("QUEST BOARD")`:

- toolbar: `REGION` option menu, `DESKTOP ONLY` checkbox (default `True`), `REFRESH`
  button, status label;
- `quest_list` height 6 with a selection binding;
- detail label with `wraplength=WIN_W - 48`;
- action row: `LAUNCH` and `FIND GAME`.

Loading behavior:

- `_on_show_quests()` calls `ensure_db_loaded()` and `ensure_quests_loaded()`.
- `ensure_quests_loaded(force=False)` returns if loading; returns from cache when
  fresh; otherwise runs `load_quest_board` via `run_task`, stores the board and a
  `time.monotonic()` stamp, rebuilds the region menu, and refreshes the list.
- On failure keep existing data; if there is none, clear the list and show a retry
  message. Never raise out of the callback.
- `quest_refresh()` calls `ensure_quests_loaded(force=True)`.

List/detail behavior:

- `_refresh_quest_list()` uses `board.filter(region, desktop_only)`, fills the list,
  selects the first row, and updates the status line with visible/hidden counts.
- Row text: `NAME · APP · REGION · ENDS <local date>`; mark unsupported rows with
  `· OTHER`.
- Detail text: name, variant count, game + app id, reward, task, region, expiry,
  resolved executable (or the reason it is missing), and the unofficial-data /
  eligibility note.
- Rebuild the region menu from `("ALL", "GLOBAL", *board.regions)`.

Launch behavior:

- `_selected_quest()` returns the quest at the listbox selection or `None`.
- `_refresh_quest_list()`/selection updates `quest_launch_btn.set_enabled(...)`
  (add an `enabled` flag and disabled draw state to `PixelButton`; existing buttons
  default to enabled).
- `quest_launch()` blocks with a log message when the quest is unsupported, the game
  is not in `self.db`, or no Windows executable resolves. It then shows the existing
  confirmation dialog (quest, game, app id, region, exe, path, timer, auto-close,
  region warning) and calls `_create_and_launch` with `config.QUEST_MINUTES` and
  `config.AUTO_CLOSE`.
- `quest_find_game()` fills `db_query` with the app name, shows the database screen,
  and logs the exact app id to select.

Also refresh the quest detail after `ensure_db_loaded` finishes so executable
information appears without reopening the screen.

- [x] **Step 4: Run the GUI tests to verify they pass**

Run: `python -m pytest tests/test_gui_quest_board.py -q`
Expected: all tests pass (Tk integration tests skip only if no display exists).

- [x] **Step 5: Run adjacent GUI tests**

Run: `python -m pytest tests/test_gui_custom_setup.py tests/test_gui_quest_board.py -q`
Expected: all pass; the existing screens still fit.

- [x] **Step 6: Commit**

```bash
git add orbifier/gui.py tests/test_gui_quest_board.py
git commit -m "Add Quest Board screen and launch flow"
```

---

### Task 4: Credits and README

**Files:**
- Modify: `orbifier/ui.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `discordquest.com` dataset URLs already in `config.py`.
- Produces: user-visible attribution and feature documentation.

- [x] **Step 1: Update the credits text**

Add a `Quest Board Data` section to `credits_text()` stating that quest and region
data come from the unofficial `discordquest.com` public dataset, that region
availability is informational, and that Discord decides final eligibility.

- [x] **Step 2: Update the README**

Add a `Quest Board` section covering:

- what the screen shows and the `ALL` / `GLOBAL` / country filter;
- `DESKTOP ONLY` and why watch-video/console/activity quests cannot be launched;
- launch reuse of the fake-process flow and app-id resolution;
- the fact that Orbifier does not bypass region locks;
- the unofficial data source and attribution;
- no Discord token is used.

Add `quest_board.py` to the project layout and mention the screen in the intro or
screens table without inventing a screenshot.

- [x] **Step 3: Run the full test suite**

Run: `python -m pytest tests -q`
Expected: all tests pass.

- [x] **Step 4: Commit**

```bash
git add orbifier/ui.py README.md
git commit -m "Document Quest Board and data source"
```

---

### Task 5: Full verification

**Files:** none (verification only).

- [x] **Step 1: Run the full suite**

Run: `python -m pytest tests -q`
Expected: all tests pass.

- [x] **Step 2: Compile-check the package**

Run: `python -m compileall -q orbifier`
Expected: exit code 0.

- [x] **Step 3: Manual smoke test**

Launch `python orbifier.py` (or `run.bat`), open `QUEST BOARD`, confirm:

- the screen fits without clipping;
- quests load and the region filter changes the list;
- selecting a quest shows the executable and region detail;
- cancelling the launch confirmation leaves the app unchanged;
- `BACK`, `ACTIVE`, and `TRAY` still work.

- [x] **Step 4: Final commit (if any smoke-test fix was needed)**

```bash
git add -A
git commit -m "Finish Quest Board verification"
```

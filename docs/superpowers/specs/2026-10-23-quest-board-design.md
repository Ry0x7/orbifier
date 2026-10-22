# Quest Board — Design

- Date: 2026-10-23
- Status: proposed
- Size: small feature

## Intent

Discord quests are region-dependent, but Orbifier currently only searches Discord's
game database by name. A user cannot see which quests are active, which regions they
are available in, or jump straight from a quest to the executable Orbifier should fake.

Add a read-only **QUEST BOARD** screen that lists active quests, shows their region
availability and reward, and launches supported desktop quests through the existing
fake-process flow.

The board is an information tool. It does not make a region-locked quest eligible;
Discord decides eligibility server-side from the account and connection region.

## Goals

- Fetch active quests and their region rules from the public DiscordQuest dataset.
- Show each quest's game, Discord application id, reward, task type, expiry, and
  region availability.
- Filter the board by region (`ALL`, `GLOBAL`, or a country code).
- Let the user select a quest and launch the matching executable with the existing
  `_create_and_launch` / `QuestTracker` path.
- Keep the feature self-contained, testable without network access, and invisible
  to the CLI.
- Fail gracefully when the dataset is unavailable or changes shape.

## Non-goals

- Discord login, user tokens, or reading the user's own quest progress.
- VPN/proxy integration or any attempt to bypass region restrictions.
- Automatically completing, accepting, or claiming quests.
- Watch-video, mobile, console, or activity quests.
- A disk cache, offline mode, or background refresh timer.
- A CLI version of the board.

## Anti-goals

- Do not imply that a listed quest is guaranteed to be eligible for the user.
- Do not block app startup or the rest of the UI while the dataset loads.
- Do not add a new runtime dependency or require an account.
- Do not duplicate the existing launch/cleanup logic.
- Do not break the current Database, Manual, Steam, or Active screens.

## Constraints

- Windows-first Tk application, single 800×560 window with a 392 px screen host.
- Python stdlib `tkinter` only; existing `requests` is the only HTTP dependency.
- Network and launch work run on daemon threads through `OrbifierApp.run_task`;
  UI updates return through `post()`.
- The dataset is an unofficial public source and may change or disappear.
- The `/api/quests` payload is currently about 2.9 MB, so it must load lazily and
  off the UI thread.
- Existing test suite must continue to pass.

## Approaches

### Surface (chosen)

1. **Dedicated QUEST BOARD screen (chosen).** New `quest_board.py` for data handling,
   new `_build_quest_board` screen in `gui.py`, and a home entry. Keeps quest
   discovery separate from game search and follows the existing screen pattern.
2. **Database Quest mode.** Add a quest mode/tab to the existing database screen.
   Rejected: the screen already holds search, list, override, timer, delete, and
   launch controls inside 392 px; adding region badges and details would be cramped.
3. **Separate browser window.** Rejected: breaks the one-window/tray flow and
   duplicates lifecycle code.

### Data source (chosen)

- **Public DiscordQuest dataset (chosen):**
  - `GET https://api.discordquest.com/api/quests`
  - `GET https://api.discordquest.com/api/regions`
- **Official `/quests/@me` endpoint:** rejected. It requires a user token and only
  returns quests for that account's region, so it cannot answer "what exists in other
  regions?" without multiple accounts or proxies.
- **Bundled static snapshot:** rejected. It would go stale quickly and add a manual
  maintenance burden. The URL stays configurable in `config.py` if the source moves.

## How it works

### Data model

New `orbifier/quest_board.py`:

- `QuestInfo` — one grouped quest:
  `name`, `app_name`, `app_id`, `reward`, `tasks`, `quest_ids`, `starts_at`,
  `expires_at`, `age_gate`, `availability`, `supported`.
- `RegionAvailability` — `is_global: bool`, `regions: frozenset[str]`,
  `known_regions: frozenset[str]`, plus `available_in(code)` and `label()`.
- `QuestBoard` — `quests`, `regions`, `fetched_at`; plus `filter(region=None,
  desktop_only=True)`.
- `load_quest_board(fetcher=fetch_json, now=None)` — fetch both endpoints, parse,
  group, and return the board. Dependency injection keeps tests offline.
- `QuestBoardError(OrbifierError)` for unusable schema/empty data.

### Fetch and cache

- `config.py` gets:
  - `DISCORD_QUEST_API_URL`
  - `DISCORD_QUEST_REGIONS_URL`
  - `QUEST_CACHE_SECONDS = 300`
  - `QUEST_API_TIMEOUT = 20`
- The GUI keeps the last `QuestBoard` and a monotonic fetch time.
- Opening the screen loads once if empty. If the cached board is older than five
  minutes, the current board is shown immediately and a refresh runs in the
  background. `REFRESH` forces a fetch.
- On a failed refresh with existing data: keep the data and log a warning.
  On a failed first load: show an error state and a retry hint.
- Both endpoints are required. A partial board would be misleading, so a failure of
  either produces the error state.

### Normalization and grouping

- Parse each `{id, config}` entry; skip malformed entries instead of failing the
  whole board. Raise `QuestBoardError` only if no usable quests remain.
- Active means `starts_at <= now < expires_at`. Missing start means active; missing
  expiry means no known end.
- Task keys come from `config.task_config_v2.tasks` (fall back to
  `config.task_config.tasks`). Only `PLAY_ON_DESKTOP` is supported by Orbifier.
  `STREAM_ON_DESKTOP`, console, mobile, watch-video, and activity tasks are shown
  when `DESKTOP ONLY` is unchecked but cannot be launched.
- Group variants by
  `(name, app_id, reward, expires_at, frozenset(tasks))`. This collapses the many
  regional ids for the same campaign (for example the nine `Clean Crew` variants)
  while keeping genuinely different campaigns separate.
- Merge region rules across a group:
  - no region entry, `is_global: true`, or empty include/exclude → global;
  - otherwise build the available set from include minus exclude;
  - union the sets across variants;
  - if any variant is global, or the union covers every known region code, the
    grouped quest is global.
- `age_gate` is true if any variant has `show_age_gate`.
- Keep `quest_ids` for the detail text (for example "9 regional variants").

### Region semantics

- Known region codes come from `/api/regions` (currently 32 codes).
- `RegionAvailability.label()`:
  - `GLOBAL` when available everywhere;
  - `US, CA` for a short explicit list;
  - `N REGIONS` for a long list;
  - `GLOBAL EXCEPT DE, FR` when the set is everything except a short list.
- The region filter options are `ALL`, `GLOBAL`, then sorted country codes.
  Default is `ALL`.
- If a country is selected, the list only includes quests whose availability covers
  that country. `GLOBAL` shows only globally available quests.
- The detail pane always shows the full region label and a warning that Discord makes
  the final eligibility decision.

### Application and executable mapping

- Add `DiscordGamesDB.get_game_by_app_id(app_id)`; compare ids as strings.
- Resolve the executable with the existing `get_win32_executable`.
- If the app id is missing from the Discord database, or the game has no Windows
  executable, show the reason in the detail pane and disable `LAUNCH`.
- `FIND GAME` opens the Database Quest screen with the game name pre-filled, so the
  user can use the existing override field.
- For a missing exe, mention that Steam-verified quests may need the Steam Quest
  screen.
- The existing Database screen remains the place to change the executable or timer.

### UI

Home screen:

- Change the button grid to 3 columns × 2 rows and use 240×48 buttons at scale 2.
- Buttons: `DATABASE QUEST`, `QUEST BOARD`, `MANUAL EXE`, `STEAM QUEST`,
  `ACTIVE QUESTS`, `CREDITS`. This adds the new entry and a useful full-screen active
  shortcut while using less vertical space than the current 2×2 grid.
- `QUEST BOARD` uses `MAGENTA`; `ACTIVE QUESTS` uses `GREEN`.

QUEST BOARD screen (built with the existing `_screen()` header):

- Toolbar row: `REGION` option menu (`ALL`, `GLOBAL`, country codes), `DESKTOP ONLY`
  checkbutton (default on), `REFRESH` button, and a status label.
- Listbox (height 6) with one line per grouped quest:
  `NAME · APP · REGION · ENDS <local date>`.
- Detail label below the list: quest name, game and app id, reward, tasks, region
  label, expiry, number of variants, resolved executable, and the data-source/
  eligibility note.
- Action row: `LAUNCH` (green) and `FIND GAME` (cyan). `LAUNCH` is disabled for
  unsupported quests, missing executables, or while the initial data is loading.
- Empty/loading/error states use the status label and log panel; no modal dialogs.
- A small muted line gives credit: `Region data: discordquest.com (unofficial)`.

### Launch flow

- Selection resolves the quest's app id to a game and executable.
- `LAUNCH` opens the existing confirmation dialog, including quest name, game,
  app id, region label, executable, target path, timer, and auto-close setting.
- The dialog warns that region availability is not guaranteed and that Orbifier
  cannot bypass region locks.
- On confirmation, call the existing `_create_and_launch(exe_name, ...)`; the active
  quest then appears in the shared ACTIVE QUESTS panels.
- The board uses `config.QUEST_MINUTES` and `config.AUTO_CLOSE`. Users who need a
  different timer or executable use the Database screen.

### Error behavior

- `NetworkError` from either endpoint → error state; log the failing URL and retry
  hint.
- Schema/parse errors → `QuestBoardError`; skip malformed entries and log how many
  were skipped.
- Unknown app ids or missing executables are normal, not errors; the detail pane
  explains the next step.
- The board never raises into the Tk callback: loading and mapping happen inside
  `run_task` or guarded handlers.

## Files

- New: `orbifier/quest_board.py`
- New: `tests/test_quest_board.py`
- New: `tests/test_gui_quest_board.py` (or extend the existing GUI test file)
- Modified: `orbifier/gui.py` — home grid, screen, handlers, loader
- Modified: `orbifier/config.py` — endpoints, cache, timeout
- Modified: `orbifier/errors.py` — `QuestBoardError`
- Modified: `orbifier/discord_db.py` — `get_game_by_app_id`
- Modified: `orbifier/ui.py` — data-source credit in the credits text
- Modified: `README.md` — feature section, source/limits, project layout
- Possibly modified: `settings.py` — only if a persistent default is wanted; this
  design does not require a new user setting.

## Tests

Unit tests (`tests/test_quest_board.py`, no network):

- active vs future/expired filtering;
- missing `starts_at`/`expires_at` handling;
- global, include, exclude, and missing-region rules;
- grouping of regional variants and union of availability;
- `Clean Crew`-style variants collapsing to one global quest;
- `DESKTOP ONLY` filtering and unsupported task detection;
- region filter behavior for `ALL`, `GLOBAL`, and a country code;
- region label formatting (`GLOBAL`, short list, long list, exceptions);
- malformed entries skipped; empty board raises `QuestBoardError`;
- app-id lookup with string/numeric ids and a missing id.

GUI tests (monkeypatched loader, no network/launch):

- Quest Board screen fits inside `WIN_W` × `HOST_H`;
- populated board lists the expected quests and defaults to `DESKTOP ONLY`;
- region filter changes the visible rows;
- selecting a quest updates the detail pane;
- `LAUNCH` is disabled/blocked for unsupported or unresolved quests.

Verification: `python -m pytest tests -q`, plus a manual GUI smoke test that opens the
board, changes the region filter, and cancels a launch confirmation.

## Builder calls

- 3×2 home grid with six buttons rather than a compact header button; keeps the new
  feature prominent and gives a full-screen Active Quests shortcut.
- Grouping key and region-union logic above; this is needed to avoid duplicate
  regional rows and is covered by tests.
- `DESKTOP ONLY` defaults on; the user can uncheck it to inspect all active quests.
- Manual region filter only; no IP/OS region detection and no extra network call.
- Session-only cache; no disk cache in this version.
- Board uses the global timer/auto-close defaults; per-quest changes stay in the
  Database screen.
- Release versioning is separate from the feature implementation; this release
  uses `v1.5.0`.

## Open questions

None.

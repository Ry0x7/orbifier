# In-App Settings — Design

- Date: 2026-10-23
- Status: proposed
- Size: project

## Intent

Orbifier's user defaults live in `settings.py`, which is fine for source runs but
not for an installed one-file exe: the bundled file is extracted to a temporary
folder and cannot be written back. Users also have no way to stop active fake
quests when they close the main window, and `AUTO_CLEAN` exists but is not wired
to anything.

Add a SETTINGS screen that edits the timer default, auto-close, auto-clean, the
close-on-exit behavior, the default output folder, and the update check. Save the
values in a writable JSON file under `%APPDATA%\Orbifier`, overlaid on top of
`settings.py`.

## Goals

- Add a dedicated SETTINGS screen in the existing pixel style.
- Edit and persist these values without restarting:
  - default timer minutes (shipped default 20);
  - auto-close when the timer ends;
  - auto-clean files after a quest stops;
  - stop all active quests when Orbifier closes;
  - default output folder;
  - check for updates at startup (applies next launch).
- Store overrides in `%APPDATA%\Orbifier\settings.json` (or the platform fallback),
  with atomic writes and validation.
- Keep `settings.py` as the shipped fallback. Precedence is:
  code defaults < `settings.py` < JSON overrides.
- Add a RESET action that deletes the JSON file and restores the `settings.py`
  values.
- Wire `AUTO_CLEAN` into the stop/cleanup path for the first time.
- Stop active quests on exit by default, while leaving a setting to keep the
  current behavior.

## Non-goals

- Editing arbitrary `settings.py` keys (developer name, repo coordinates, sleep
  timings, cache timeout).
- A settings screen for the CLI. The screen is GUI-only. The CLI keeps its
  explicit output-folder prompt and delete prompts; its shared-config behavior is
  limited to the timer, auto-close, and update-check defaults (see Builder calls).
- Per-quest/session settings. The screen edits defaults; per-launch controls stay
  on the Database, Manual, and Steam screens.
- Portable mode next to the exe or a registry backend.
- Theme, language, or layout settings.
- A settings file watcher. External edits are picked up on the next launch.

## Anti-goals

- Do not rewrite `settings.py` from the app.
- Do not let a malformed settings file prevent startup.
- Do not delete a user's fake files when auto-clean is off.
- Do not stop active quests on exit when the user has turned that option off.
- Do not add a third-party dependency.

## Constraints

- Python standard library only: `json`, `os`, `pathlib`, `tkinter`.
- Windows-first; use `%APPDATA%` when available, otherwise a home-directory
  fallback.
- The SETTINGS screen must fit the 800×560 minimum window.
- Existing tests must keep passing; tests must not read or write the developer's
  real `%APPDATA%` file.
- `ORBIFIER_SETTINGS` environment variable overrides the settings path for tests
  and portable use.

## Approaches

### Storage

1. **APPDATA JSON overrides (chosen).** A small `user_settings.py` module loads,
   validates, and atomically writes a JSON file. It works in source and frozen
   runs, is inspectable and testable, and does not execute user data.
2. **Portable JSON next to the exe (rejected).** Easier to carry, but fails when
   the exe is under Program Files or another read-only directory. Supporting both
   locations would add a precedence rule for little benefit.
3. **Windows registry (rejected).** Native but opaque, harder to back up and
   test, and ties the feature to Windows only.

### UI placement

1. **Dedicated SETTINGS screen with a home top-bar button (chosen).** Follows the
   existing `_screen()` pattern, leaves room for six controls, and does not add a
   third row to the home grid.
2. **Seventh home-grid tile (rejected).** Makes the grid 3×3 and risks clipping
   the ACTIVE QUESTS strip at the 800×560 minimum.
3. **Modal Toplevel dialog (rejected).** Less consistent with the one-window
   screen flow and needs its own lifecycle/styling.

## Builder calls

The design review left four decisions open; the close-on-exit default is also
called out for clarity. They are settled here as builder calls; each keeps the
user's request intact and avoids a second approval round.

1. **CLI scope.** The screen is GUI-only, but shared config is not. The CLI keeps
   its explicit output-folder prompt and its own delete prompts. It honors
   `QUEST_MINUTES` and `AUTO_CLOSE` because `GameFaker.launch_executable()` uses
   those config values when callers do not pass explicit values, and it honors
   `CHECK_UPDATES` because `main.main()` skips `auto_update()` when the setting
   is off. `OUTPUT_DIR`, `AUTO_CLEAN`, and `CLOSE_QUESTS_ON_EXIT` are GUI-only.
2. **Cleanup ownership.** Auto-clean covers every way a quest can stop: the STOP
   and STOP ALL buttons, timer-end auto-close, the user closing the keep-alive
   window, and close-on-exit. `_tick_quests()` also notices a quest that has
   already exited (status `STOPPED`) and cleans it when `AUTO_CLEAN` is on.
   When `AUTO_CLEAN` is off, STOPPED rows stay until CLEAR; CLEAR dismisses the
   row but leaves files, and the Database/Manual/Steam DELETE buttons still
   remove files explicitly.
3. **Blank output folder.** `OUTPUT_DIR = ""` means
   `Desktop\<FAKE_EXE_DIR>` at use time, so changing `FAKE_EXE_DIR` in
   `settings.py` still works. The settings field shows blank for that default;
   non-blank values are stored stripped and expanded with `Path.expanduser()`
   when used.
4. **Steam manifest.** Auto-clean and close-on-exit handle only the placeholder
   process/exe and owned helper files. The Steam `appmanifest_<appid>.acf` stays,
   matching the README; the Steam DELETE button remains the explicit way to
   remove it.
5. **Close-on-exit default.** `CLOSE_QUESTS_ON_EXIT` ships as True. Closing
   Orbifier is the natural end of a session, and leaving detached fake processes
   running is the surprise. Users who want quests to outlive the window can turn
   it off.

## How it works

### Settings file

New `orbifier/user_settings.py`:

- `settings_path() -> Path`:
  - `ORBIFIER_SETTINGS` if set;
  - else `%APPDATA%\Orbifier\settings.json` on Windows;
  - else `~/.orbifier/settings.json`.
- `SETTINGS_KEYS = ("QUEST_MINUTES", "AUTO_CLOSE", "AUTO_CLEAN",
  "CLOSE_QUESTS_ON_EXIT", "OUTPUT_DIR", "CHECK_UPDATES")`.
- `load_overrides() -> dict`: read the JSON if present, keep valid known keys,
  ignore unknown keys, and record a human-readable `LOAD_ERROR` instead of
  raising. A missing file is normal.
- `validate(values) -> dict`: normalize and validate a full or partial mapping.
  - `QUEST_MINUTES`: number from 1 to 1440.
  - Booleans: actual bools (the screen supplies bools).
  - `OUTPUT_DIR`: string; strip whitespace; blank means
    `Desktop\<FAKE_EXE_DIR>` and stays blank in the file.
  - Unknown keys are dropped.
  - Raise `SettingsError(ValueError)` with a field-specific message.
- `save_overrides(values) -> Path`: validate, create the parent directory, write
  a temporary file in the same directory, then `os.replace()` it over the target.
- `delete_overrides() -> bool`: remove the file if present.
- `LOAD_ERROR` module attribute for the GUI/CLI to report once.

### Config precedence and runtime updates

`orbifier/config.py`:

- Import `user_settings` and call `load_overrides()` before resolving values.
- `_get(name, default)` records the base value from `settings.py`/default in a
  module-level `_BASE` map and returns the JSON override when present.
- New values:
  - `CLOSE_QUESTS_ON_EXIT = _get("CLOSE_QUESTS_ON_EXIT", True)`
  - `OUTPUT_DIR = _get("OUTPUT_DIR", "")`
  - `CHECK_UPDATES = _get("CHECK_UPDATES", True)`
- Add `apply_overrides(values)` to set the module attributes and update the
  in-memory override map.
- Add `reset_overrides()` to clear the override map and restore the `_BASE`
  values.

`settings.py` gains the three new keys and uses 20 for `QUEST_MINUTES`.

### SETTINGS screen

- Add a `SETTINGS` PixelButton to the home top bar, immediately left of `TRAY`.
- Register `"settings": self._build_settings()` in `self.screens`.
- Build with `_screen("SETTINGS")` so BACK/TRAY/ACTIVE behave like other screens.
- Compact two-column layout:
  - DEFAULT TIMER (MIN) entry;
  - AUTO-CLOSE ON TIMER END checkbox;
  - AUTO-CLEAN FILES checkbox;
  - CLOSE QUESTS ON ORBIFIER EXIT checkbox;
  - CHECK FOR UPDATES checkbox;
  - DEFAULT OUTPUT FOLDER entry with BROWSE (blank = `Desktop\<FAKE_EXE_DIR>`).
- Buttons: SAVE (green) and RESET (red, confirms first).
- A status label reports the saved path or a validation error.
- A muted line shows the effective settings file path.
- `_on_show_settings()` reloads the fields from `config` so the screen always
  reflects the active values. The output field shows the raw `config.OUTPUT_DIR`
  (blank when the Desktop default is active).
- On SAVE:
  1. Validate the fields through `user_settings.validate`.
  2. Write the JSON with `save_overrides`.
  3. Call `config.apply_overrides`.
  4. Update `self.output_directory` (resolved to the Desktop default when blank),
     the three per-launch MIN entries, and the three per-launch auto-close
     checkboxes.
  5. Log the saved path; note that the update-check change applies next launch.
- On RESET:
  1. Confirm.
  2. `user_settings.delete_overrides()` and `config.reset_overrides()`.
  3. Reload the screen fields and the per-launch defaults.
  4. Log that the shipped defaults are active again.
- On startup, if `user_settings.LOAD_ERROR` is set, log it once as a warning.

### Stop-on-exit and auto-clean

- `CLOSE_QUESTS_ON_EXIT` defaults to True. `OrbifierApp.close()` calls a new
  `_stop_quests_for_exit()` helper that stops every active quest synchronously
  before destroying the root. This terminates the fake processes and closes their
  timer/tray windows.
- If the option is off, close keeps the current behavior: the detached fake
  processes keep running.
- `QuestTracker.cleanup(quest, clean_files=True)`, `stop(quest, clean_files=True)`,
  and `stop_all(clean_files=True)` gain a `clean_files` flag. When false, the
  process is stopped but the copied exe, helpers, and folders are left alone.
- `OrbifierApp._stop_quests` passes `clean_files=config.AUTO_CLEAN` to cleanup.
  This covers STOP, STOP ALL, timer-end auto-close, and close-on-exit.
- `_tick_quests()` also handles a process that exited on its own (the keep-alive
  timer self-closing after 00:00, or the user closing its window):
  - `DONE` with auto-close on: stop and clean as today;
  - `STOPPED` with `AUTO_CLEAN` on: remove the row and clean the files;
  - `STOPPED` with `AUTO_CLEAN` off: keep the row for CLEAR;
  - `DONE` with auto-close off: keep the process and row (the user may leave the
    timer open).
- Explicit DELETE buttons call cleanup with the default `clean_files=True`, so
  they always remove files. CLEAR uses `_stop_quests` and therefore respects
  `AUTO_CLEAN`: with the setting off it dismisses the row but leaves files.
- Steam appmanifest files are never part of the quest cleanup set. Auto-clean and
  close-on-exit leave `appmanifest_<appid>.acf` in place, as documented.

### Update check and output folder

- `run_gui()` passes `check_updates=config.CHECK_UPDATES` to `OrbifierApp`.
- `main.main()` wraps `auto_update()` in `if config.CHECK_UPDATES:` so the CLI
  honors the same startup setting. The settings screen notes that the toggle
  applies next launch.
- `GameFaker.launch_executable()` uses `config.QUEST_MINUTES * 60` and
  `config.AUTO_CLOSE` as defaults when the caller passes no explicit values. GUI
  callers always pass both, so their per-launch controls still win; CLI callers
  inherit the configured defaults.
- `OrbifierApp` seeds `self.output_directory` from `config.OUTPUT_DIR` when set,
  otherwise from `Desktop\<FAKE_EXE_DIR>` as today. Saving a new output folder
  updates the shared output-folder field immediately.
- The CLI keeps its output-folder prompt and its blank-means-Desktop behavior;
  `OUTPUT_DIR` is a GUI default only.

## Files

- New: `orbifier/user_settings.py` — path, load/validate/save/delete, load error.
- New: `tests/test_user_settings.py` — unit tests with `tmp_path`.
- New: `tests/test_gui_settings.py` — screen, save, reset, close-on-exit tests.
- Modified: `orbifier/config.py` — override loading, new keys, apply/reset.
- Modified: `settings.py` — new keys, timer default 20.
- Modified: `orbifier/gui.py` — SETTINGS screen, home button, output-folder seed,
  update-check wiring, close-on-exit helper, auto-clean pass-through.
- Modified: `orbifier/quests.py` — `clean_files` flag on cleanup/stop/stop_all.
- Modified: `orbifier/faker.py` — launch defaults from config; embedded 20-minute
  timer default.
- Modified: `orbifier/main.py` — gate the startup update check on
  `config.CHECK_UPDATES`.
- Modified: `orbifier/timer.py`, `orbifier/ui.py` — 20-minute default and credits
  copy.
- Modified: `tests/conftest.py` — test settings path and reset fixture.
- Modified: `tests/test_quests.py` — auto-clean on/off behavior.
- Modified: `README.md` — settings screen, file location, precedence, new keys.

## Tests

Unit tests (`tests/test_user_settings.py`, no GUI):

- path honors `ORBIFIER_SETTINGS`, then APPDATA, then the home fallback;
- save/load roundtrip for all six keys;
- atomic save leaves no `.tmp` file;
- invalid minutes, booleans, and output types raise `SettingsError`;
- malformed JSON loads as empty overrides and records `LOAD_ERROR`;
- unknown keys are ignored;
- delete removes the file and is safe when missing.

Config tests:

- JSON overrides beat `settings.py`;
- `apply_overrides` changes attributes immediately;
- `reset_overrides` restores the base values.

Quest/CLI tests:

- `clean_files=False` stops the process and keeps the exe/helpers;
- `clean_files=True` still removes them;
- `launch_executable()` uses `config.QUEST_MINUTES` and `config.AUTO_CLOSE` when
  its arguments are omitted, and explicit arguments still win.

GUI tests (`tests/test_gui_settings.py`):

- home exposes a SETTINGS button;
- SETTINGS screen fits the 800×560 minimum;
- opening the screen seeds fields from config, with a blank output field for the
  Desktop default;
- SAVE writes the JSON, updates config, the output-folder field, and the three
  per-launch MIN/auto-close controls;
- invalid timer shows an error and leaves the file unchanged;
- RESET deletes the JSON and restores base values;
- close-on-exit stops quests when enabled and leaves them alone when disabled;
- auto-clean off stops the process but keeps the fake exe;
- a STOPPED quest is auto-cleaned when `AUTO_CLEAN` is on and remains when off;
- CLEAR with `AUTO_CLEAN` off removes the row but keeps the fake exe.

Test isolation:

- `tests/conftest.py` sets `ORBIFIER_SETTINGS` to a temp path before importing
  `orbifier`, and an autouse fixture clears the file and calls
  `config.reset_overrides()` around every test.

## Verification

- `python -m pytest tests -q`
- Manual smoke test:
  - open SETTINGS from home;
  - change the timer to 25, disable auto-clean and close-on-exit, set an output
    folder, save, restart, and confirm the values persist;
  - launch a quest, stop it with auto-clean off, and confirm the fake exe remains;
  - close a keep-alive timer window manually with auto-clean on and confirm the
    ACTIVE QUESTS row and files disappear;
  - turn close-on-exit back on and confirm closing Orbifier terminates active
    quests and their timer windows;
  - toggle update check off, restart, and confirm no update check runs in the GUI
    or the CLI;
  - reset to defaults and confirm the shipped values return, including a blank
    output folder that resolves to `Desktop\<FAKE_EXE_DIR>`.

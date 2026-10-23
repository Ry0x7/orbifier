# In-App Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent SETTINGS screen for the timer, auto-close, auto-clean, close-on-exit, output-folder, and update-check defaults.

**Architecture:** A small `user_settings.py` module owns the `%APPDATA%\Orbifier\settings.json` file with validation and atomic writes. `config.py` overlays those values on `settings.py`, and the existing single-window GUI gets a dedicated SETTINGS screen plus stop-path wiring for auto-clean and close-on-exit.

**Tech Stack:** Python 3, tkinter (stdlib), json/pathlib/os, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-settings-screen-design.md`

## Global Constraints

- Prerequisite: execute `docs/superpowers/plans/2026-10-23-resizable-window.md` first. Its Task 3 establishes the 20-minute timer default and credits copy; this plan assumes that work is complete.
- Python standard library only; no new dependencies.
- Precedence: code defaults < `settings.py` < `%APPDATA%\Orbifier\settings.json`.
- `ORBIFIER_SETTINGS` overrides the settings path. Without `%APPDATA%`, use `~/.orbifier/settings.json`.
- Shipped defaults: `QUEST_MINUTES = 20`, `AUTO_CLOSE = True`, `AUTO_CLEAN = True`, `CLOSE_QUESTS_ON_EXIT = True`, `OUTPUT_DIR = ""`, `CHECK_UPDATES = True`.
- `OUTPUT_DIR = ""` resolves to `Desktop\<FAKE_EXE_DIR>` at use time and stays blank in the JSON.
- `AUTO_CLEAN` covers STOP, STOP ALL, timer self-close, external timer-window close, and close-on-exit. Explicit DELETE still deletes files.
- Steam `appmanifest_<appid>.acf` files are never removed by auto-clean or close-on-exit.
- The SETTINGS screen and the home screen with its new button fit the 800×560 minimum.
- Tests never read or write the developer's real `%APPDATA%` file.
- `python -m pytest tests -q` must pass.

## Review Focus

- **Corrupt or unreadable settings JSON:** the app must start with `settings.py` values and log a warning, never crash. Pinned by `test_malformed_json_is_ignored` in Task 1.
- **Unwritable settings path:** SAVE must show an error and leave the running config unchanged. Pinned by `test_save_failure_does_not_apply_config` in Task 4.
- **Invalid timer entry:** SAVE must reject it and leave any existing file untouched. Pinned by `test_save_invalid_timer_keeps_file_unchanged` in Task 4.
- **Timer process exits before the GUI observes DONE:** a STOPPED quest must still auto-clean when enabled. Pinned by `test_tick_auto_cleans_stopped_quests` in Task 5.
- **Blank or whitespace output folder:** it must resolve to the Desktop default, not the current working directory. Pinned by `test_save_blank_output_uses_desktop_default` in Task 4.

---

### Task 1: Settings persistence module

**Files:**
- Create: `orbifier/user_settings.py`
- Create: `tests/test_user_settings.py`
- Modify: `tests/conftest.py:1-12`

**Interfaces:**
- Produces: `SettingsError(ValueError)`, `SETTINGS_KEYS`, `LOAD_ERROR: str | None`, `settings_path() -> Path`, `load_overrides() -> dict`, `validate(values: dict) -> dict`, `save_overrides(values: dict) -> Path`, `delete_overrides() -> bool`.
- Internal test seam: `_home_dir() -> Path`.

- [ ] **Step 1: Set the test settings path before importing Orbifier**

In `tests/conftest.py`, add `tempfile` and `Path` imports, then place this
above `from orbifier import gui, ui`:

```python
_TEST_SETTINGS = Path(tempfile.gettempdir()) / f"orbifier-test-settings-{os.getpid()}.json"
_TEST_SETTINGS.unlink(missing_ok=True)
os.environ["ORBIFIER_SETTINGS"] = str(_TEST_SETTINGS)
```

- [ ] **Step 2: Write the failing unit tests**

Create `tests/test_user_settings.py`:

```python
import json
import pytest
from orbifier import user_settings


def test_settings_path_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(tmp_path / "s.json"))
    assert user_settings.settings_path() == tmp_path / "s.json"


def test_settings_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("ORBIFIER_SETTINGS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert user_settings.settings_path() == tmp_path / "Orbifier" / "settings.json"


def test_settings_path_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("ORBIFIER_SETTINGS", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(user_settings, "_home_dir", lambda: tmp_path)
    assert user_settings.settings_path() == tmp_path / ".orbifier" / "settings.json"


def test_save_load_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    values = {"QUEST_MINUTES": 25, "AUTO_CLOSE": False, "AUTO_CLEAN": False,
              "CLOSE_QUESTS_ON_EXIT": False, "OUTPUT_DIR": str(tmp_path / "out"),
              "CHECK_UPDATES": False}
    assert user_settings.save_overrides(values) == path
    assert user_settings.load_overrides() == {**values, "QUEST_MINUTES": 25.0}
    assert user_settings.LOAD_ERROR is None


def test_save_is_atomic(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    user_settings.save_overrides({"AUTO_CLOSE": False})
    assert not (tmp_path / "settings.json.tmp").exists()


@pytest.mark.parametrize("values", [
    {"QUEST_MINUTES": 0}, {"QUEST_MINUTES": "abc"}, {"QUEST_MINUTES": True},
    {"AUTO_CLOSE": "yes"}, {"OUTPUT_DIR": 123},
])
def test_validate_rejects_invalid_values(values):
    with pytest.raises(user_settings.SettingsError):
        user_settings.validate(values)


def test_malformed_json_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {}
    assert "Could not read" in user_settings.LOAD_ERROR


def test_unknown_keys_are_ignored(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"NOPE": 1, "AUTO_CLOSE": False}), encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {"AUTO_CLOSE": False}
    assert user_settings.LOAD_ERROR is None


def test_invalid_key_is_skipped(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"QUEST_MINUTES": 0, "AUTO_CLOSE": False}), encoding="utf-8")
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.load_overrides() == {"AUTO_CLOSE": False}
    assert "QUEST_MINUTES" in user_settings.LOAD_ERROR


def test_delete_is_safe_when_missing(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ORBIFIER_SETTINGS", str(path))
    assert user_settings.delete_overrides() is False
    user_settings.save_overrides({"AUTO_CLOSE": True})
    assert user_settings.delete_overrides() is True
    assert not path.exists()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_user_settings.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'orbifier.user_settings'`.

- [ ] **Step 4: Implement `orbifier/user_settings.py`**

Implement these exact interfaces:

```python
SETTINGS_KEYS = ("QUEST_MINUTES", "AUTO_CLOSE", "AUTO_CLEAN",
                 "CLOSE_QUESTS_ON_EXIT", "OUTPUT_DIR", "CHECK_UPDATES")

class SettingsError(ValueError):
    pass

LOAD_ERROR: str | None = None

def _home_dir() -> Path: ...
def settings_path() -> Path: ...
def validate(values: dict) -> dict: ...
def load_overrides() -> dict: ...
def save_overrides(values: dict) -> Path: ...
def delete_overrides() -> bool: ...
```

Behavior:

- `settings_path()`: non-empty `ORBIFIER_SETTINGS`, expanded; else non-empty
  `APPDATA` / `"Orbifier"` / `"settings.json"`; else `_home_dir()` /
  `".orbifier"` / `"settings.json"`. `_home_dir()` returns `Path.home()`.
- `validate()`: keep only `SETTINGS_KEYS`; drop unknown keys. `QUEST_MINUTES`
  rejects `bool`, converts with `float` (wrap conversion errors), requires
  `1 <= value <= 1440`, and rejects non-finite values. Use the message
  `QUEST_MINUTES must be between 1 and 1440 minutes.` so the GUI test can match
  `between 1 and 1440`. Booleans require `isinstance(value, bool)`.
  `OUTPUT_DIR` requires a string and is `.strip()`ed. Raise `SettingsError`
  with the key name in the message.
- `load_overrides()`: reset `LOAD_ERROR = None`; missing file returns `{}`.
  Read/parse errors (`OSError`, `UnicodeDecodeError`, `json.JSONDecodeError`)
  or a non-dict JSON value return `{}` and set `LOAD_ERROR` to a message
  containing `"Could not read"` and the path.
  Validate each known key independently; keep valid keys, skip invalid ones,
  and append a message containing the key name to `LOAD_ERROR`.
- `save_overrides()`: validate first, create the parent directory, write
  `json.dumps(valid, indent=2) + "\n"` to `path.with_name(path.name + ".tmp")`
  with UTF-8, then `os.replace(tmp, path)`. On `OSError`, remove the temp file
  and raise `SettingsError("Could not save settings: ...")`. Return `path`.
- `delete_overrides()`: call `path.unlink()`; return `True` on success and
  `False` on `FileNotFoundError`. Wrap other `OSError` values in
  `SettingsError("Could not delete settings: ...")`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_user_settings.py -v`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add orbifier/user_settings.py tests/test_user_settings.py tests/conftest.py
git commit -m "Add persistent user settings storage"
```

---

### Task 2: Config overrides and new settings keys

**Files:**
- Modify: `orbifier/config.py:10-24` and the UI block near line 67
- Modify: `settings.py:24-27`
- Modify: `tests/conftest.py` (import `config`; add autouse reset fixture)
- Create: `tests/test_config_overrides.py`

**Interfaces:**
- Consumes: `user_settings.load_overrides()`, `user_settings.validate()`, `user_settings.SETTINGS_KEYS`.
- Produces: `config.CLOSE_QUESTS_ON_EXIT: bool`, `config.OUTPUT_DIR: str`, `config.CHECK_UPDATES: bool`, `config.apply_overrides(values: dict) -> None`, `config.reset_overrides() -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_overrides.py`:

```python
from orbifier import config


def test_new_keys_have_expected_defaults():
    assert config.CLOSE_QUESTS_ON_EXIT is True
    assert config.OUTPUT_DIR == ""
    assert config.CHECK_UPDATES is True


def test_apply_overrides_changes_values():
    base_minutes = config.QUEST_MINUTES
    config.apply_overrides({"QUEST_MINUTES": 25, "AUTO_CLEAN": False})
    assert config.QUEST_MINUTES == 25
    assert config.AUTO_CLEAN is False
    config.reset_overrides()
    assert config.QUEST_MINUTES == base_minutes
    assert config.AUTO_CLEAN is True


def test_loaded_override_wins(monkeypatch):
    monkeypatch.setitem(config._overrides, "QUEST_MINUTES", 33)
    assert config._get("QUEST_MINUTES", 20) == 33


def test_reset_restores_output_and_close_on_exit():
    config.apply_overrides({"OUTPUT_DIR": "C:/out", "CLOSE_QUESTS_ON_EXIT": False})
    assert config.OUTPUT_DIR == "C:/out"
    assert config.CLOSE_QUESTS_ON_EXIT is False
    config.reset_overrides()
    assert config.OUTPUT_DIR == ""
    assert config.CLOSE_QUESTS_ON_EXIT is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config_overrides.py -v`

Expected: FAIL because the new attributes and methods do not exist.

- [ ] **Step 3: Implement the override layer and add the keys**

In `orbifier/config.py`:

```python
from . import user_settings

_overrides = user_settings.load_overrides()
_BASE: dict = {}

def _get(name: str, default):
    base = getattr(_user, name, default) if _user else default
    _BASE[name] = base
    return _overrides.get(name, base)
```

- Add `CLOSE_QUESTS_ON_EXIT = _get("CLOSE_QUESTS_ON_EXIT", True)`,
  `OUTPUT_DIR = _get("OUTPUT_DIR", "")`, and
  `CHECK_UPDATES = _get("CHECK_UPDATES", True)` to the UI/UX block.
- Add:

```python
def apply_overrides(values: dict) -> None:
    normalized = user_settings.validate(values)
    for key, value in normalized.items():
        globals()[key] = value
        _overrides[key] = value


def reset_overrides() -> None:
    _overrides.clear()
    for key in user_settings.SETTINGS_KEYS:
        if key in _BASE:
            globals()[key] = _BASE[key]
```

In `settings.py`, append below `AUTO_CLEAN`:

```python
CLOSE_QUESTS_ON_EXIT = True  # stop active fake quests when Orbifier closes
OUTPUT_DIR = ""              # blank = Desktop\<FAKE_EXE_DIR>
CHECK_UPDATES = True         # check GitHub releases at startup
```

In `tests/conftest.py`, import `config` alongside `gui` and `ui`, then add:

```python
@pytest.fixture(autouse=True)
def _isolate_user_settings():
    config.reset_overrides()
    _TEST_SETTINGS.unlink(missing_ok=True)
    yield
    config.reset_overrides()
    _TEST_SETTINGS.unlink(missing_ok=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config_overrides.py tests/test_user_settings.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add orbifier/config.py settings.py tests/conftest.py tests/test_config_overrides.py
git commit -m "Overlay JSON user settings on config"
```

---

### Task 3: Add a `clean_files` flag to quest cleanup

**Files:**
- Modify: `orbifier/quests.py:124-173`
- Test: `tests/test_quests.py` (append)

**Interfaces:**
- Produces: `QuestTracker.cleanup(quest, clean_files: bool = True)`, `QuestTracker.stop(quest, clean_files: bool = True)`, `QuestTracker.stop_all(clean_files: bool = True)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quests.py`:

```python
def test_stop_without_clean_stops_process_and_keeps_files(tmp_path):
    tracker, _clock = make_tracker()
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"x")
    helper = tmp_path / "helper.pyw"
    helper.write_text("x")
    proc = FakeProc()
    quest = tracker.add("Game", proc, exe, cleanup_root=tmp_path,
                        cleanup_files=(helper,))
    tracker.stop(quest, clean_files=False)
    assert proc.terminated
    assert tracker.quests == []
    assert exe.exists()
    assert helper.exists()


def test_stop_all_without_clean_keeps_each_exe(tmp_path):
    tracker, _clock = make_tracker()
    exes = []
    for i in range(2):
        exe = tmp_path / f"game{i}.exe"
        exe.write_bytes(b"x")
        tracker.add(f"Game{i}", FakeProc(), exe)
        exes.append(exe)
    tracker.stop_all(clean_files=False)
    assert tracker.quests == []
    assert all(exe.exists() for exe in exes)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_quests.py -v`

Expected: FAIL with `TypeError: stop() got an unexpected keyword argument 'clean_files'`.

- [ ] **Step 3: Implement the flag**

Change the three methods to accept `clean_files: bool = True`. `stop()` forwards it
to `cleanup()`; `cleanup()` always calls `_stopper(quest.proc)` but returns
before any file or directory deletes when `clean_files` is false; `stop_all()`
forwards it to each `stop()` call.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_quests.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add orbifier/quests.py tests/test_quests.py
git commit -m "Make quest file cleanup optional"
```

---

### Task 4: Build the SETTINGS screen

**Files:**
- Modify: `orbifier/gui.py` (imports, `__init__`, screens dict, home top bar, new methods)
- Create: `tests/test_gui_settings.py`

**Interfaces:**
- Consumes: `user_settings.validate()`, `save_overrides()`, `delete_overrides()`, `LOAD_ERROR`; `config.apply_overrides()`, `reset_overrides()`.
- Produces: `OrbifierApp.home_settings_button`, `.settings_minutes`, `.settings_autoclose`, `.settings_autoclean`, `.settings_close_on_exit`, `.settings_check_updates`, `.settings_output`, `.settings_status_var`, `.settings_save()`, `.settings_reset()`, `._apply_settings_to_gui()`, `._default_output_dir() -> str`.

- [ ] **Step 1: Write the failing GUI tests**

Create `tests/test_gui_settings.py`:

```python
import json
import pytest
from orbifier import config, gui, user_settings


@pytest.fixture(scope="module")
def app(gui_app):
    return gui_app


@pytest.fixture(autouse=True)
def _clear_app_quests(app):
    app.quests.quests.clear()
    yield
    app.quests.quests.clear()


def _show(app):
    app.show("settings")
    app.root.update_idletasks()


def test_home_has_settings_button(app):
    assert app.home_settings_button.text == "SETTINGS"
    app.home_settings_button.invoke()
    assert app.current == "settings"


def test_settings_and_home_fit_minimum_window(app):
    for name in ("home", "settings"):
        app.show(name)
        app.root.update_idletasks()
        screen = app.screens[name]
        assert screen.winfo_reqwidth() <= gui.WIN_W, name
        assert screen.winfo_reqheight() <= gui.HOST_H, name


def test_settings_screen_seeds_from_config(app, monkeypatch):
    monkeypatch.setattr(config, "QUEST_MINUTES", 33.0)
    monkeypatch.setattr(config, "AUTO_CLOSE", False)
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", False)
    monkeypatch.setattr(config, "CHECK_UPDATES", False)
    monkeypatch.setattr(config, "OUTPUT_DIR", "C:/tmp/out")
    _show(app)
    assert app.settings_minutes.get() == "33"
    assert app.settings_autoclose.get() is False
    assert app.settings_autoclean.get() is False
    assert app.settings_close_on_exit.get() is False
    assert app.settings_check_updates.get() is False
    assert app.settings_output.get() == "C:/tmp/out"


def test_save_writes_json_and_applies(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    app.settings_autoclose.set(False)
    app.settings_autoclean.set(False)
    app.settings_close_on_exit.set(False)
    app.settings_check_updates.set(False)
    app.settings_output.set(str(tmp_path / "out"))
    app.settings_save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["QUEST_MINUTES"] == 25.0
    assert data["AUTO_CLEAN"] is False
    assert config.QUEST_MINUTES == 25.0
    assert config.AUTO_CLOSE is False
    assert config.AUTO_CLEAN is False
    assert config.CLOSE_QUESTS_ON_EXIT is False
    assert config.CHECK_UPDATES is False
    assert config.OUTPUT_DIR == str(tmp_path / "out")
    assert app.output_directory.get() == str(tmp_path / "out")
    for entry in (app.db_minutes, app.manual_minutes, app.steam_minutes):
        assert entry.get() == "25"
    for var in (app.db_autoclose, app.manual_autoclose, app.steam_autoclose):
        assert var.get() is False


def test_save_blank_output_uses_desktop_default(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    app.settings_output.set("   ")
    app.settings_save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["OUTPUT_DIR"] == ""
    assert config.OUTPUT_DIR == ""
    assert app.settings_output.get() == ""
    assert app.output_directory.get() == str(
        app.faker.desktop_path / config.FAKE_EXE_DIR)


def test_save_invalid_timer_keeps_file_unchanged(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"AUTO_CLOSE": true}', encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    _show(app)
    base = config.QUEST_MINUTES
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "0")
    app.settings_save()
    assert "between 1 and 1440" in app.settings_status_var.get()
    assert config.QUEST_MINUTES == base
    assert path.read_text(encoding="utf-8") == before


def test_save_failure_does_not_apply_config(app, monkeypatch):
    base = config.QUEST_MINUTES
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    monkeypatch.setattr(user_settings, "save_overrides",
                        lambda values: (_ for _ in ()).throw(
                            user_settings.SettingsError("disk full")))
    app.settings_save()
    assert "disk full" in app.settings_status_var.get()
    assert config.QUEST_MINUTES == base


def test_reset_deletes_file_and_restores_defaults(app, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "settings_path", lambda: path)
    base = config.QUEST_MINUTES
    _show(app)
    app.settings_minutes.delete(0, "end")
    app.settings_minutes.insert(0, "25")
    app.settings_save()
    assert path.exists()
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.settings_reset()
    assert not path.exists()
    assert config.QUEST_MINUTES == base
    assert "RESET" in app.settings_status_var.get()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gui_settings.py -v`

Expected: FAIL because `settings` is not in `app.screens` and the settings widgets do not exist.

- [ ] **Step 3: Implement the screen**

In `orbifier/gui.py`:

- Change the import to `from . import config, ui, user_settings`.
- In `__init__`, seed the shared output field with
  `tk.StringVar(value=self._default_output_dir())`, add
  `"settings": self._build_settings()` to `self.screens`, and after the
  `ready` log add:
  ```python
  if user_settings.LOAD_ERROR:
      self.log(f"[!] {user_settings.LOAD_ERROR}", "warn")
  ```
  After `self.screens` is built, call `self._apply_settings_to_gui()` so the
  per-launch fields show compact values such as `25`, not `25.0`.
- In `_build_home`, after the TRAY button:
  ```python
  self.home_settings_button = PixelButton(
      top, "SETTINGS", lambda: self.show("settings"),
      width=140, height=40, color=YELLOW, scale=2)
  self.home_settings_button.pack(side="right", padx=(0, 8))
  ```
- Add `_default_output_dir()`:
  ```python
  def _default_output_dir(self) -> str:
      raw = str(config.OUTPUT_DIR or "").strip()
      if raw:
          return str(Path(raw).expanduser())
      return str(self.faker.desktop_path / config.FAKE_EXE_DIR)
  ```
- Add `_build_settings()` using `_screen("SETTINGS")` and this exact layout:
  - Row: `DEFAULT TIMER (MIN)` label, `self.settings_minutes = self._entry(row, width=6)`,
    and `AUTO-CLOSE WHEN TIMER ENDS` checkbutton bound to
    `self.settings_autoclose = tk.BooleanVar(value=config.AUTO_CLOSE)`.
  - Row: `AUTO-CLEAN FILES AFTER STOP` checkbutton bound to
    `self.settings_autoclean = tk.BooleanVar(value=config.AUTO_CLEAN)`, and
    `STOP QUESTS WHEN ORBIFIER CLOSES` bound to
    `self.settings_close_on_exit = tk.BooleanVar(value=config.CLOSE_QUESTS_ON_EXIT)`.
  - Row: `CHECK FOR UPDATES AT STARTUP` bound to
    `self.settings_check_updates = tk.BooleanVar(value=config.CHECK_UPDATES)`,
    plus a muted `(APPLIES NEXT LAUNCH)` label.
  - `self.settings_output = tk.StringVar(value=str(config.OUTPUT_DIR or ""))`,
    then `self._directory_row(frame, self.settings_output, "DEFAULT OUTPUT FOLDER")`.
  - Muted hint: `BLANK = DESKTOP\<FAKE_EXE_DIR>`.
  - Actions row: SAVE button calling `self.settings_save`, RESET button calling
    `self.settings_reset` (both `width=120, height=38`), and
    `self.settings_status_var = tk.StringVar(value="EDIT SETTINGS")`
    in a label with `wraplength=WIN_W - 300`, `justify="left"`, and
    `pack(side="left", fill="x", expand=True, padx=12)`.
  - Bottom muted label: `FILE: {user_settings.settings_path()}` with
    `wraplength=WIN_W - 48`, `justify="left"`, `anchor="w"`, packed
    `side="bottom", fill="x", padx=12, pady=(0, 8)`.
  Use the existing checkbutton styling: `bg=BG`, `fg=TEXT`,
  `selectcolor=PANEL_DARK`, `activebackground=BG`, `activeforeground=TEXT`,
  `font=self.font_small`.
- Add `_on_show_settings()`: set `settings_minutes` to
  `f"{config.QUEST_MINUTES:g}"`, set the four BooleanVars from `config`, set
  `settings_output` to `str(config.OUTPUT_DIR or "")`, and set the status to
  `EDIT SETTINGS`.
- Add `settings_save()`: build a six-key dict from the widgets; call
  `user_settings.validate`, then `user_settings.save_overrides`, then
  `config.apply_overrides`; on `ValueError` set the status and log the error;
  on success call `_apply_settings_to_gui()`, normalize `settings_output` to
  `str(config.OUTPUT_DIR or "")`, set `SAVED TO {path}`, log an OK line and
  `Update-check changes apply on the next launch.`
- Add `settings_reset()`: ask `messagebox.askyesno`; on yes call
  `user_settings.delete_overrides()` and `config.reset_overrides()`; on
  `ValueError` show/log the error; otherwise call `_on_show_settings()` and
  `_apply_settings_to_gui()`, set `RESET TO SETTINGS.PY DEFAULTS`, and log.
- Add `_apply_settings_to_gui()`: replace the text in `db_minutes`,
  `manual_minutes`, and `steam_minutes` with `f"{config.QUEST_MINUTES:g}"`;
  set the three autoclose vars to `config.AUTO_CLOSE`; set
  `self.quests.duration = float(config.QUEST_MINUTES) * 60`; set
  `self.output_directory` to `_default_output_dir()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gui_settings.py tests/test_gui_custom_setup.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add orbifier/gui.py tests/test_gui_settings.py
git commit -m "Add the in-app settings screen"
```

---

### Task 5: Wire auto-clean and close-on-exit

**Files:**
- Modify: `orbifier/gui.py` (`_tick_quests`, `_stop_quests`, `close`, `run_gui`)
- Test: `tests/test_gui_settings.py` (append)

**Interfaces:**
- Consumes: `QuestTracker.stop_all(clean_files=...)`, `config.AUTO_CLEAN`, `config.CLOSE_QUESTS_ON_EXIT`.
- Produces: `OrbifierApp._stop_quests_for_exit() -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_settings.py`:

```python
class FakeProc:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def test_close_on_exit_stops_all_quests(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.quests, "stop_all",
                        lambda clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", True)
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    app._stop_quests_for_exit()
    assert calls == [False]


def test_close_on_exit_disabled_does_nothing(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.quests, "stop_all",
                        lambda clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(config, "CLOSE_QUESTS_ON_EXIT", False)
    app._stop_quests_for_exit()
    assert calls == []


def test_tick_auto_cleans_stopped_quests(app, monkeypatch):
    quest = app.quests.add("Stopped.exe", FakeProc(returncode=0))
    calls = []
    monkeypatch.setattr(app, "_stop_quests", lambda quests: calls.extend(quests))
    monkeypatch.setattr(config, "AUTO_CLEAN", True)
    app._tick_quests()
    assert quest in calls
    app.quests.quests.remove(quest)


def test_tick_keeps_stopped_quest_when_auto_clean_off(app, monkeypatch):
    quest = app.quests.add("Stopped.exe", FakeProc(returncode=0))
    calls = []
    monkeypatch.setattr(app, "_stop_quests", lambda quests: calls.extend(quests))
    monkeypatch.setattr(config, "AUTO_CLEAN", False)
    app._tick_quests()
    assert calls == []
    assert quest in app.quests.quests
    app.quests.quests.remove(quest)


@pytest.mark.parametrize("auto_clean", [True, False])
def test_stop_quests_passes_auto_clean_flag(app, monkeypatch, auto_clean):
    quest = app.quests.add("Test.exe", FakeProc())
    calls = []
    monkeypatch.setattr(app.quests, "cleanup",
                        lambda q, clean_files=True: calls.append(clean_files))
    monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(config, "AUTO_CLEAN", auto_clean)
    app._stop_quests([quest])
    assert calls == [auto_clean]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gui_settings.py -v`

Expected: FAIL because `_stop_quests_for_exit` does not exist and `_stop_quests` does not pass the flag.

- [ ] **Step 3: Implement the wiring**

In `orbifier/gui.py`:

- Add:
  ```python
  def _stop_quests_for_exit(self) -> None:
      if not config.CLOSE_QUESTS_ON_EXIT:
          return
      self.quests.stop_all(clean_files=config.AUTO_CLEAN)
  ```
- Call `self._stop_quests_for_exit()` at the top of `close()`.
- In `_stop_quests`, capture `clean_files = config.AUTO_CLEAN` before starting
  the worker and call `tracker.cleanup(quest, clean_files=clean_files)`.
- In `_tick_quests`, keep the `auto_done` block but make its log message
  conditional: `Auto-closed and cleaned up.` when `config.AUTO_CLEAN` is true,
  otherwise `Auto-closed; files kept.` Update the comment above the block so it
  no longer claims files are always cleaned.
- After the `auto_done` block, add:
  ```python
  if config.AUTO_CLEAN:
      stopped = [q for q in list(self.quests.quests)
                 if self.quests.status(q) == STOPPED]
      if stopped:
          self._stop_quests(stopped)
  ```
- Change `run_gui()` to:
  ```python
  OrbifierApp(root, check_updates=config.CHECK_UPDATES)
  ```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gui_settings.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add orbifier/gui.py tests/test_gui_settings.py
git commit -m "Honor auto-clean and close-on-exit settings"
```

---

### Task 6: CLI defaults and update-check gate

**Files:**
- Modify: `orbifier/faker.py:36`, `orbifier/faker.py:188`, `orbifier/faker.py:355-364`
- Modify: `orbifier/main.py:18-23`
- Create: `tests/test_cli_defaults.py`

**Interfaces:**
- Produces: `GameFaker.launch_executable(exe_path, duration_s=None, start_time=None, auto_close=None)`; `main._run_update_check() -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_defaults.py`:

```python
from orbifier import config, faker, main


class FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args


def _game(monkeypatch):
    monkeypatch.setattr(faker.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(faker, "loading_animation", lambda *a, **k: None)
    monkeypatch.setattr(faker, "print_color", lambda *a, **k: None)
    return faker.GameFaker()


def test_launch_defaults_from_config(tmp_path, monkeypatch):
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(config, "QUEST_MINUTES", 25)
    monkeypatch.setattr(config, "AUTO_CLOSE", False)
    proc = _game(monkeypatch).launch_executable(exe)
    assert proc.args[proc.args.index("--duration") + 1] == "1500"
    assert proc.args[proc.args.index("--auto-close") + 1] == "0"


def test_launch_explicit_arguments_win(tmp_path, monkeypatch):
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")
    proc = _game(monkeypatch).launch_executable(exe, duration_s=60, auto_close=True)
    assert proc.args[proc.args.index("--duration") + 1] == "60"
    assert proc.args[proc.args.index("--auto-close") + 1] == "1"


def test_embedded_timer_defaults_to_twenty():
    assert "DEFAULT_MINS  = 20" in faker._TIMER_PYW_CODE


def test_update_check_can_be_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "auto_update", lambda: calls.append(1))
    monkeypatch.setattr(config, "CHECK_UPDATES", False)
    main._run_update_check()
    assert calls == []
    monkeypatch.setattr(config, "CHECK_UPDATES", True)
    main._run_update_check()
    assert calls == [1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cli_defaults.py -v`

Expected: FAIL because the defaults are 15/True and `_run_update_check` does not exist.

- [ ] **Step 3: Implement the defaults and gate**

- In `faker.py`, change the embedded `DEFAULT_MINS` from 15 to 20. The embedded
  `TimerApp` and `run_timer` already derive their defaults from that constant.
- Change `launch_executable` to accept `duration_s: float | None = None` and
  `auto_close: bool | None = None`. At the start of the method:
  ```python
  if duration_s is None:
      duration_s = float(config.QUEST_MINUTES) * 60
  if auto_close is None:
      auto_close = bool(config.AUTO_CLOSE)
  ```
- In `main.py`, add:
  ```python
  def _run_update_check() -> None:
      if not config.CHECK_UPDATES:
          return
      try:
          auto_update()
      except Exception:
          pass
  ```
  Replace the existing try/except `auto_update()` block in `main()` with a call
  to `_run_update_check()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_defaults.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add orbifier/faker.py orbifier/main.py tests/test_cli_defaults.py
git commit -m "Honor settings in CLI defaults and update check"
```

---

### Task 7: Documentation and end-to-end verification

**Files:**
- Modify: `README.md`
- Verification only; fixes go into the owning task's files.

- [ ] **Step 1: Update the README settings section**

Replace the current `## Settings` section with:

```markdown
## Settings

Open **SETTINGS** from the home screen to edit the timer, auto-close,
auto-clean, close-on-exit, output-folder, and update-check defaults. Changes are
saved to `%APPDATA%\Orbifier\settings.json` (or `~/.orbifier/settings.json`) and
override `settings.py`; the bundled `settings.py` remains the fallback.
**RESET** deletes the JSON file and restores the values from `settings.py` (the
shipped defaults unless you edited that file). External edits to `settings.py`
are picked up on the next launch when no JSON override exists. The CLI keeps its
own output-folder and delete prompts; it honors `QUEST_MINUTES`, `AUTO_CLOSE`,
and `CHECK_UPDATES`, and does not apply `AUTO_CLEAN`, `CLOSE_QUESTS_ON_EXIT`, or
`OUTPUT_DIR`.

| Key | Default | Meaning |
|---|---|---|
| `VERSION` | `"1.5.0"` | Version shown in the window and used by the update check. |
| `DEVELOPER` | `"Ry0x7"` | Name shown in the status bar. |
| `GITHUB_REPO_OWNER` | `"Ry0x7"` | Owner of the repo the exe checks for updates. |
| `GITHUB_REPO_NAME` | `"orbifier"` | Repo the exe checks for updates. |
| `FAKE_EXE_DIR` | `"Win64"` | Folder on the Desktop that holds the placeholder copies. |
| `SLEEP_SHORT` | `1.0` | Short pause (seconds) in the console menu. |
| `SLEEP_LONG` | `2.0` | Long pause (seconds) in the console menu. |
| `MAX_SEARCH_RESULTS` | `50` | Maximum games listed per database search. |
| `QUEST_MINUTES` | `20` | Default length of the ACTIVE QUESTS countdown per game. |
| `AUTO_CLOSE` | `True` | Automatically close the fake game process when timer completes. |
| `AUTO_CLEAN` | `True` | Remove fake exe and owned helper files after any stop (STOP, timer end, external close, or app exit when close-on-exit is on). |
| `CLOSE_QUESTS_ON_EXIT` | `True` | Stop active fake quests when Orbifier closes. |
| `OUTPUT_DIR` | `""` | Default GUI output folder; blank uses `Desktop\<FAKE_EXE_DIR>`. |
| `CHECK_UPDATES` | `True` | Check for updates at startup in the GUI and CLI. |
```

- [ ] **Step 2: Update the quest-run and Steam behavior text**

In `README.md`, under "How a quest run works" step 2, replace the default-output
sentence with:

```markdown
Manual and Database screens share this folder selection; it defaults to the
`OUTPUT_DIR` setting when set, otherwise `Desktop\<FAKE_EXE_DIR>\`.
```

Replace step 6 with:

```markdown
6. ACTIVE QUESTS counts down in perfect sync with the keep-alive window. When time elapses:
   - If **AUTO-CLOSE** is on (default), the process terminates; **AUTO-CLEAN**
     removes the `.exe` and empty directories when it is on.
   - If off, STOP terminates the process. STOP and STOP ALL respect **AUTO-CLEAN**;
     when it is off, CLEAR dismisses a stopped row without deleting files.
   - Explicit DELETE in the setup screens still removes the placeholder files.
   - Closing the keep-alive window manually is also a stop; **AUTO-CLEAN** removes
     files when it is on.
   - Closing Orbifier stops active quests when **CLOSE_QUESTS_ON_EXIT** is on (default).
```

In the Steam section, replace the automatic-cleanup paragraph with:

```markdown
Orbifier does **not** remove the manifest automatically. STOP removes the placeholder exe
when **AUTO_CLEAN** is on, but the `.acf` file remains until you delete it, and Steam may
show the game as installed in the meantime. Empty game subfolders may be removed during
cleanup; the selected output folder and the library's `common` directory are preserved.
The SETTINGS auto-clean and close-on-exit options do not remove the appmanifest; use the
Steam DELETE button for that.
```

In the project layout, replace the `config.py` line and add `user_settings.py`
after it:

```
  config.py              defaults merged with settings.py and user settings
  user_settings.py       %APPDATA% settings overrides and validation
```

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest tests -q`

Expected: all tests pass.

- [ ] **Step 4: Smoke-test the GUI manually**

Run: `python orbifier.py`

Check:

- The home screen shows SETTINGS to the left of TRAY and still fits at the
  minimum window size.
- SETTINGS opens, its six controls fit, and the file path is shown.
- Change the timer to 25, disable auto-clean and close-on-exit, set an output
  folder, disable update check, save, restart, and confirm the values persist.
- With auto-clean off, launch a quest, stop it, and confirm the fake exe remains.
- Turn auto-clean on, launch a quest, close its keep-alive window manually, and
  confirm the ACTIVE QUESTS row and files disappear.
- Turn close-on-exit on, launch a quest, close Orbifier, and confirm the fake
  process and timer window terminate.
- Confirm no update check runs in the GUI or the CLI while the setting is off.
- RESET deletes the JSON file and restores the values from `settings.py`,
  including a blank output folder that resolves to `Desktop\<FAKE_EXE_DIR>`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document the settings screen and new defaults"
```





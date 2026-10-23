# Resizable Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Orbifier's fixed 800×560 window resizable with expandable result lists and a 20-minute default timer.

**Architecture:** Keep the existing single-window pack layout. Unlock the root window with a display-aware initial size and an 800×560 minimum, let the screen host absorb extra height, and switch the three result listboxes to vertical expansion. Change the timer default in the settings/config/timer fallbacks and in the docs/credits copy.

**Tech Stack:** Python 3, tkinter (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-resizable-window-design.md`

## Global Constraints

- tkinter and the Python standard library only; no new dependencies.
- Minimum client size is 800×560; default client size is 900×640, clamped to `screen_w - 80` and `screen_h - 120`.
- The screen host expands; the log stays 136 px and the status bar stays 32 px.
- Quest Board, Database, and Steam result lists expand vertically. Their listbox `height` values remain the requested minimum.
- The default timer is 20 minutes in `settings.py`, the `config.py` fallback, `timer.DEFAULT_MINS`, the embedded `faker.py` keep-alive, the `launch_executable` default, credits text, and the README settings table.
- Preserve the pixel-art style and all launch, cleanup, and quest-tracking behavior.
- `python -m pytest tests -q` must pass.

## Review Focus

- **Display smaller than the default window:** the window must clamp to the usable screen but never go below 800×560. Pinned by `test_initial_window_size_clamps_to_display` in Task 1.
- **User resizes down to the minimum:** headers, detail text, and action rows must not clip or force horizontal overflow. Pinned by the updated `test_quest_board_screen_fits_window` and `test_changed_screens_fit_window` in Task 2.
- **User enlarges the window:** extra height must go to the active screen and its result list, not to the log or status bar. Pinned by `test_window_is_resizable_with_minimum_size` in Task 1 and `test_result_lists_expand_vertically` in Task 2.
- **Long Quest Board detail names:** the detail label must wrap to the current width instead of widening the screen. Pinned by `test_quest_detail_rewraps_to_width` in Task 2.
- **Timer default drift:** settings, config fallback, timer fallback, embedded
  keep-alive, CLI launcher, credits, and README must all report 20 minutes.
  Pinned by `test_default_timer_is_twenty_minutes`,
  `test_credits_mention_twenty_minutes`, `test_embedded_timer_defaults_to_twenty`,
  and `test_launch_uses_configured_timer_default` in Task 3.

---

### Task 1: Resizable window with display-aware initial size

**Files:**
- Modify: `orbifier/gui.py` (geometry constants near line 48, `OrbifierApp.__init__` near line 398, `_build_layout` near line 538)
- Test: `tests/test_gui_resize.py` (create)

**Interfaces:**
- Consumes: existing `gui.WIN_W`, `gui.WIN_H`.
- Produces: `gui.DEFAULT_W: int`, `gui.DEFAULT_H: int`, `gui.initial_window_size(screen_w: int, screen_h: int) -> tuple[int, int]`, `OrbifierApp.log_wrap`, `OrbifierApp.status_bar`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui_resize.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gui_resize.py -v`

Expected: FAIL with `AttributeError: module 'orbifier.gui' has no attribute 'initial_window_size'` and `AttributeError: 'OrbifierApp' object has no attribute 'log_wrap'`.

- [ ] **Step 3: Implement the window sizing and host expansion**

In `orbifier/gui.py`, replace the geometry block with:

```python
# ── Geometry ──────────────────────────────────────────────────────────────────
WIN_W, WIN_H         = 800, 560   # minimum client size
DEFAULT_W, DEFAULT_H = 900, 640   # initial client size where the display allows it
HOST_H               = 392        # screen area at the minimum window size
LOG_H                = 136        # log panel
STATUS_H             = 32         # status bar
PX                   = 3         # chunky border thickness
BTN_SHADOW           = 4         # drop-shadow / press offset


def initial_window_size(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Initial client size, clamped to the display and the minimum window."""
    width = min(DEFAULT_W, max(WIN_W, screen_w - 80))
    height = min(DEFAULT_H, max(WIN_H, screen_h - 120))
    return width, height
```

In `OrbifierApp.__init__`, replace the `root.geometry(...)` and
`root.resizable(False, False)` lines with:

```python
root.minsize(WIN_W, WIN_H)
width, height = initial_window_size(root.winfo_screenwidth(), root.winfo_screenheight())
root.geometry(f"{width}x{height}")
root.resizable(True, True)
```

In `_build_layout`, change the host pack line to:

```python
self.host.pack(side="top", fill="both", expand=True)
```

Keep `self.host.pack_propagate(False)` and the `width=WIN_W, height=HOST_H` frame
arguments.

Store the fixed bars for the test:

```python
self.log_wrap = log_wrap
```

Place that after the `log_wrap` frame is created. Do the same for the status frame:

```python
self.status_bar = status
```

Place that after the `status` frame is created. Leave both pack calls unchanged
(no `expand=True`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gui_resize.py -v`

Expected: 4 passed.

- [ ] **Step 5: Run the existing GUI tests to catch layout regressions**

Run: `python -m pytest tests/test_gui_custom_setup.py tests/test_gui_quest_board.py -q`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add orbifier/gui.py tests/test_gui_resize.py
git commit -m "Make the main window resizable"
```

---

### Task 2: Expand result lists and rewrap the Quest Board detail

**Files:**
- Modify: `orbifier/gui.py` (Quest Board list/detail near line 952, Database list near line 741, Steam list near line 1422)
- Modify: `tests/test_gui_quest_board.py` (fit test near line 96)
- Modify: `tests/test_gui_custom_setup.py` (fit test near line 12)
- Test: `tests/test_gui_resize.py`

**Interfaces:**
- Consumes: `gui.WIN_W`, `gui.DEFAULT_W` from Task 1.
- Produces: `OrbifierApp.quest_detail_label` (a `tk.Label`), `OrbifierApp._resize_quest_detail(event) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gui_resize.py`:

```python
def test_result_lists_expand_vertically(app):
    for widget in (app.quest_list, app.db_list, app.steam_list):
        assert int(widget.pack_info()["expand"]) == 1


def test_quest_detail_rewraps_to_width(app):
    app._resize_quest_detail(SimpleNamespace(width=1000))
    assert int(app.quest_detail_label.cget("wraplength")) == 952

    app._resize_quest_detail(SimpleNamespace(width=200))
    assert int(app.quest_detail_label.cget("wraplength")) == 400

    app._resize_quest_detail(SimpleNamespace(width=gui.DEFAULT_W))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gui_resize.py -v`

Expected: FAIL because the lists report `expand == 0` and `_resize_quest_detail` does not exist.

- [ ] **Step 3: Implement vertical expansion and detail wrapping**

Quest Board list:

```python
list_wrap.pack(side="top", fill="both", expand=True, padx=12, pady=4)
self.quest_list.pack(side="left", fill="both", expand=True)
```

Quest Board detail label — replace the anonymous `tk.Label(...)` with a stored
widget and bind the frame:

```python
self.quest_detail_label = tk.Label(
    frame, textvariable=self.quest_detail_var, bg=BG, fg=TEXT,
    font=self.font_small, anchor="w", justify="left",
    wraplength=WIN_W - 48,
)
self.quest_detail_label.pack(side="top", fill="x", padx=12, pady=(2, 4))
frame.bind("<Configure>", self._resize_quest_detail)
```

Add this method after `_build_quests`:

```python
def _resize_quest_detail(self, event):
    """Keep the quest detail text inside the current window width."""
    self.quest_detail_label.configure(wraplength=max(400, event.width - 48))
```

Database list:

```python
self.db_list.pack(side="top", fill="both", expand=True, padx=12, pady=4)
```

Steam list:

```python
self.steam_list.pack(side="top", fill="both", expand=True, padx=12, pady=4)
```

- [ ] **Step 4: Update the fit tests for both widths**

In `tests/test_gui_quest_board.py`, add `from types import SimpleNamespace` at the
top. Replace the assertions in `test_quest_board_screen_fits_window` with:

```python
    app.show("quests")
    app._resize_quest_detail(SimpleNamespace(width=gui.WIN_W))
    app.root.update_idletasks()
    screen = app.screens["quests"]
    assert screen.winfo_reqwidth() <= gui.WIN_W, screen.winfo_reqwidth()

    app._resize_quest_detail(SimpleNamespace(width=gui.DEFAULT_W))
    app.root.update_idletasks()
    assert screen.winfo_reqwidth() <= gui.DEFAULT_W, screen.winfo_reqwidth()
    assert screen.winfo_reqheight() <= gui.HOST_H, screen.winfo_reqheight()
```

In `tests/test_gui_custom_setup.py`, parametrize the existing fit test over both
client widths:

```python
@pytest.mark.parametrize("width", [gui.WIN_W, gui.DEFAULT_W])
def test_changed_screens_fit_window(app, width):
    for name in ("manual", "database", "steam"):
        app.show(name)
        app.root.update_idletasks()
        screen = app.screens[name]
        assert screen.winfo_reqwidth() <= width, (name, width, screen.winfo_reqwidth())
        assert screen.winfo_reqheight() <= gui.HOST_H, (name, screen.winfo_reqheight())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gui_resize.py tests/test_gui_quest_board.py tests/test_gui_custom_setup.py -v`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add orbifier/gui.py tests/test_gui_resize.py tests/test_gui_quest_board.py tests/test_gui_custom_setup.py
git commit -m "Expand result lists with the window"
```

---

### Task 3: Default quest timer to 20 minutes

**Files:**
- Modify: `settings.py:25`, `orbifier/config.py:72`, `orbifier/timer.py:23`,
  `orbifier/faker.py` (`DEFAULT_MINS` near line 36 and `launch_executable` near
  line 369), `orbifier/ui.py:172`, `README.md:157`
- Test: `tests/test_timer_default.py` (create)

**Interfaces:**
- Consumes: existing `config.QUEST_MINUTES`, `timer.DEFAULT_MINS`, `ui.credits_text`.
- Produces: `GameFaker.launch_executable(exe_path, duration_s=None, ...)`; all
  shipped default timer values are 20.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_timer_default.py`:

```python
"""The shipped timer default stays consistent across code and credits."""
import settings

from orbifier import config, faker, timer
from orbifier.ui import _NoColors, credits_text


class FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args


def test_default_timer_is_twenty_minutes():
    assert settings.QUEST_MINUTES == 20
    assert config.QUEST_MINUTES == 20
    assert timer.DEFAULT_MINS == 20


def test_credits_mention_twenty_minutes():
    assert "20 minutes" in credits_text(c=_NoColors, enter_prompt=False)


def test_embedded_timer_defaults_to_twenty():
    assert "DEFAULT_MINS  = 20" in faker._TIMER_PYW_CODE


def test_launch_uses_configured_timer_default(tmp_path, monkeypatch):
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(faker.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(faker, "loading_animation", lambda *a, **k: None)
    monkeypatch.setattr(faker, "print_color", lambda *a, **k: None)
    monkeypatch.setattr(config, "QUEST_MINUTES", 25)
    proc = faker.GameFaker().launch_executable(exe)
    assert proc.args[proc.args.index("--duration") + 1] == "1500"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_timer_default.py -v`

Expected: FAIL because the defaults are 15, the credits text uses 15, and the
launcher starts at 900 seconds.

- [ ] **Step 3: Change the defaults**

- `settings.py`: `QUEST_MINUTES = 20`
- `orbifier/config.py`: `_get("QUEST_MINUTES", 20)`
- `orbifier/timer.py`: `DEFAULT_MINS = 20`
- `orbifier/faker.py`: change the embedded `DEFAULT_MINS` from 15 to 20; change
  `launch_executable` to accept `duration_s: float | None = None` and resolve it
  at the start of the method:
  ```python
  if duration_s is None:
      duration_s = float(config.QUEST_MINUTES) * 60
  ```
  Leave the `auto_close` default unchanged; the settings plan handles it.
- `orbifier/ui.py`: change the credits line to
  `• Complete ALL orb quests simultaneously in just {config.QUEST_MINUTES} minutes`
- `README.md`: change the `QUEST_MINUTES` default row from `15` to `20`

No GUI field logic changes are needed; the fields already seed from
`config.QUEST_MINUTES`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_timer_default.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add settings.py orbifier/config.py orbifier/timer.py orbifier/faker.py orbifier/ui.py README.md tests/test_timer_default.py
git commit -m "Default quest timer to 20 minutes"
```

---

### Task 4: Full-suite and manual verification

**Files:**
- None (fixes go into the owning task's files)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests -q`

Expected: all tests pass.

- [ ] **Step 2: Smoke-test the GUI manually**

Run: `python orbifier.py`

Check:
- The window opens at 900×640 on a large display, is resizable, and cannot be
  dragged below 800×560.
- Quest Board grows its result list when the window grows; the scrollbar still
  works; long detail text wraps and does not clip.
- Database and Steam result lists grow with the window.
- The log panel and status bar keep their heights.
- The MIN fields on Database, Manual, and Steam show 20.
- Opening a Launch confirmation shows `Timer: 20 minutes`.

- [ ] **Step 3: Fix and re-run if needed**

If a layout clips, commit the fix in the task that owns the affected screen and
re-run `python -m pytest tests -q`.

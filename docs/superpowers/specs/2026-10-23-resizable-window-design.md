# Resizable Window — Design

- Date: 2026-10-23
- Status: proposed
- Size: small change

## Intent

The main window is fixed at 800×560 and the result lists are fixed at six rows
(three for Steam), so the Quest Board and Database results feel cramped. Make the
window resizable and let the list consume the extra height. Also raise the default
quest timer from 15 to 20 minutes.

This supersedes the "single 800×560 window" constraint from the Quest Board design.

## Goals

- Make the main window resizable, with 800×560 as the minimum client size.
- Start at 900×640 where the display allows it, clamped to the usable screen area.
- Let the Quest Board, Database, and Steam result lists grow vertically with the window.
- Keep the log panel and status bar at their current fixed heights.
- Rewrap the Quest Board detail text when the window width changes.
- Make 20 minutes the default timer for the GUI fields, CLI manual launches,
  keep-alive fallback, README, and credits text.

## Non-goals

- A draggable splitter between the screen area and the log.
- Saving window geometry across launches.
- Redesigning the pixel-art style, the ACTIVE QUESTS rows, or the home grid.
- Horizontal scrollbars for result rows.
- Per-user settings migration: an explicit `QUEST_MINUTES` in `settings.py` still wins.

## Anti-goals

- Do not break any screen at the 800×560 minimum.
- Do not change launch, cleanup, or quest-tracking behavior.
- Do not add a runtime dependency or a new settings file.

## Constraints

- Tkinter only, Windows-first, and the existing screen structure.
- 800×560 stays the minimum because the headers, Database action row, and Steam
  controls are laid out for that width.
- Existing GUI tests assume `WIN_W` / `HOST_H`; update the fit test for the new
  default client area where needed.
- `settings.py` is user-editable, so code fallbacks must also use 20.

## Approaches

1. **Responsive pack layout (chosen).** Unlock the window, keep the log and status
   bar fixed, and switch the result lists from fixed `fill="x"` packing to
   `fill="both", expand=True`. The screen host already expands inside the root.
2. **Vertical PanedWindow splitter (rejected).** Same responsive layout plus a
   draggable sash between the screen and log. More adjustable, but it changes the
   window structure, adds sash styling/handling, and goes beyond the request.
3. **Responsive layout with persisted geometry (rejected).** Same as 1 plus saving
   the window size on exit. Convenient, but adds disk state and off-screen-restore
   edge cases for little benefit now.

## How it works

### Window and host

- Keep `WIN_W, WIN_H = 800, 560` as the minimum size.
- Add `DEFAULT_W, DEFAULT_H = 900, 640` for the initial client size.
- Compute the initial geometry from the display size so 900×640 is used when it
  fits and the window does not open larger than the screen.
- Call `root.minsize(WIN_W, WIN_H)` and `root.resizable(True, True)`.
- Pack the screen host with `fill="both", expand=True`. The log panel and status
  bar remain fixed-height, so extra vertical space goes to the current screen.

### Result lists

- **Quest Board:** change the list wrapper and listbox to expand vertically. The
  detail label and action row keep their positions below the list.
- Bind the Quest Board frame's `<Configure>` event to set the detail label's
  `wraplength` to the available width (minimum 400 px).
- **Database:** let `db_list` expand vertically.
- **Steam:** let `steam_list` expand vertically.
- Leave each listbox's `height` value as its requested minimum. At the larger
  initial window the lists show more rows automatically; at the minimum size they
  keep today's layout.

### Timer default

- `settings.py` and the `config.py` fallback become 20.
- `timer.DEFAULT_MINS` becomes 20.
- The embedded keep-alive script in `faker.py` gets the same 20-minute default,
  and `faker.launch_executable` defaults to `config.QUEST_MINUTES * 60` so CLI
  manual launches use the configured default instead of a hard-coded 900 seconds.
- README's `QUEST_MINUTES` default row and the credits text say 20 (the credits
  text interpolates `config.QUEST_MINUTES`).
- The GUI fields already seed from `config.QUEST_MINUTES`, so no per-screen logic
  changes are needed.

## Files

- `orbifier/gui.py` — window sizing, host packing, list expansion, detail wrapping.
- `orbifier/config.py` — fallback timer default.
- `settings.py` — user-visible timer default.
- `orbifier/timer.py` — keep-alive fallback.
- `orbifier/faker.py` — embedded keep-alive default and CLI launch default.
- `orbifier/ui.py` — credits text.
- `README.md` — settings table.
- `tests/test_gui_quest_board.py`, `tests/test_gui_custom_setup.py` — fit tests for
  the new default width.
- New GUI test file for resize/list-expansion assertions.

## Tests

- Existing suite continues to pass.
- GUI tests assert the window reports resizable, the minimum size is 800×560, and
  the three result listboxes have vertical expansion enabled.
- Update the "screen fits window" assertions to use the default client width.
- Manual smoke test: open Quest Board, Database, Steam, and Active Quest screens;
  resize larger and back to the minimum; confirm lists grow, scroll, and nothing
  clips. Confirm the GUI timer fields show 20 minutes.

## Verification

- `python -m pytest tests -q`
- Manual GUI smoke test as above.

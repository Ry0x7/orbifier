"""
gui.py – Orbifier desktop GUI (tkinter, 2D pixel-art style).

Everything is drawn with stdlib tkinter: no PIL, no bundled fonts.
Network / file / launch work runs on daemon threads; results come back to
the Tk main thread through a queue polled with ``root.after``.

The CLI (``--cli``) is untouched; this module only reuses the
non-interactive building blocks of discord_db / faker / steam / updater.
"""

import queue
import sys
import time
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import messagebox, filedialog

from . import config, ui
from . import steam
from .ui import Colors
from .errors import OrbifierError
from .discord_db import DiscordGamesDB
from .faker import GameFaker, is_process_elevated, ELEVATED_WARNING
from .quests import QuestTracker, format_mmss, RUNNING, DONE, STOPPED
from .updater import auto_update

# ── Palette ───────────────────────────────────────────────────────────────────
BG         = "#1a1b26"
PANEL      = "#24283b"
PANEL_DARK = "#16161e"
BORDER     = "#414868"
SHADOW     = "#0d0e14"
CYAN       = "#7dcfff"
MAGENTA    = "#bb9af7"
GREEN      = "#9ece6a"
RED        = "#f7768e"
YELLOW     = "#e0af68"
TEXT       = "#c0caf5"
MUTED      = "#565f89"
WHITE      = "#e6f7ff"

# ── Geometry ──────────────────────────────────────────────────────────────────
WIN_W, WIN_H   = 800, 560
HOST_H         = 392   # swapped screen area
LOG_H          = 136   # log panel
STATUS_H       = 32    # status bar
PX             = 3     # chunky border thickness
BTN_SHADOW     = 4     # drop-shadow / press offset

FONT_CANDIDATES = (("Press Start 2P", 8), ("Fixedsys", 10), ("Terminal", 10))
FONT_FALLBACK   = ("Consolas", 10)

# ── 5x7 bitmap glyphs for pixel text ──────────────────────────────────────────
_GLYPHS = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    "-": [".....", ".....", ".....", ".###.", ".....", ".....", "....."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "/": ["....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."],
    "&": [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "<": ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    ">": [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
}
GLYPH_W, GLYPH_H = 5, 7


def pixel_text_width(text: str, scale: int) -> int:
    """Width in screen pixels of *text* rendered with draw_pixel_text."""
    return max(0, len(text) * (GLYPH_W + 1) * scale - scale)


def draw_pixel_text(canvas, x, y, text, scale, color, shadow=None, tags=()):
    """Draw *text* on *canvas* from the 5x7 glyph table. Returns the width."""
    if shadow:
        draw_pixel_text(canvas, x + scale, y + scale, text, scale, shadow, None, tags)
    cx = x
    for ch in text.upper():
        rows = _GLYPHS.get(ch, _GLYPHS[" "])
        for ry, row in enumerate(rows):
            # merge horizontal runs into one rectangle (fewer canvas items)
            run_start = None
            for rx, cell in enumerate(row + "."):
                if cell == "#" and run_start is None:
                    run_start = rx
                elif cell != "#" and run_start is not None:
                    canvas.create_rectangle(
                        cx + run_start * scale, y + ry * scale,
                        cx + rx * scale, y + (ry + 1) * scale,
                        fill=color, width=0, tags=tags,
                    )
                    run_start = None
        cx += (GLYPH_W + 1) * scale
    return pixel_text_width(text, scale)


# ── Orb sprite (16x16 palette indices) ────────────────────────────────────────
# 0 transparent · 1 outline · 2 deep · 3 body · 4 rim light · 5 specular · 6 halo
ORB_SPRITE = [
    "0000006666000000",
    "0000661111660000",
    "0006112222116000",
    "0061223333221600",
    "0612335533332160",
    "0612355333333216",
    "6123553333333216",
    "6123533333333216",
    "6123333333334216",
    "6122333333344216",
    "0612233333442160",
    "0612223334422160",
    "0061222244221600",
    "0006112222116000",
    "0000661111660000",
    "0000006666000000",
]

# Glow cycle: each frame overrides some palette entries.
ORB_BASE_PALETTE = {"1": SHADOW, "2": "#3d2a6b", "3": MAGENTA, "4": CYAN, "5": WHITE, "6": BG}
ORB_GLOW_FRAMES = [
    {"6": "#2a2f4a", "5": WHITE, "4": CYAN},
    {"6": "#5b4a8a", "5": CYAN, "4": "#a9e1ff"},
    {"6": MAGENTA, "5": WHITE, "4": WHITE},
    {"6": "#5b4a8a", "5": CYAN, "4": "#a9e1ff"},
]


class OrbLogo(tk.Canvas):
    """Animated pixel orb drawn from ORB_SPRITE."""

    def __init__(self, master, scale=5, bg=BG, interval=260):
        size = len(ORB_SPRITE) * scale
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0)
        self._interval = interval
        self._frame = 0
        for y, row in enumerate(ORB_SPRITE):
            for x, idx in enumerate(row):
                if idx == "0":
                    continue
                self.create_rectangle(
                    x * scale, y * scale, (x + 1) * scale, (y + 1) * scale,
                    fill=ORB_BASE_PALETTE[idx], width=0, tags=(f"pal{idx}",),
                )
        self._animate()

    def _animate(self):
        for idx, color in ORB_GLOW_FRAMES[self._frame].items():
            self.itemconfigure(f"pal{idx}", fill=color)
        self._frame = (self._frame + 1) % len(ORB_GLOW_FRAMES)
        self.after(self._interval, self._animate)


# ── Widgets ───────────────────────────────────────────────────────────────────

class PixelButton(tk.Canvas):
    """Flat chunky button: 3px border, drop shadow, hover colour, press offset."""

    def __init__(self, master, text, command, width=300, height=56,
                 color=CYAN, scale=3, bg=BG):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.color, self.scale = text, command, color, scale
        self._bw, self._bh = width, height
        self._hover = self._pressed = False
        self._draw()
        self.bind("<Enter>", lambda _e: self._set(hover=True))
        self.bind("<Leave>", lambda _e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda _e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _set(self, hover=None, pressed=None):
        if hover is not None:
            self._hover = hover
        if pressed is not None:
            self._pressed = pressed
        self._draw()

    def _on_release(self, event):
        was_pressed = self._pressed
        self._set(pressed=False)
        inside = 0 <= event.x < self._bw and 0 <= event.y < self._bh
        if was_pressed and inside and self.command:
            self.command()

    def invoke(self):
        """Programmatic click (used by tests / keyboard shortcuts)."""
        if self.command:
            self.command()

    def _draw(self):
        self.delete("all")
        w, h, s = self._bw, self._bh, BTN_SHADOW
        off = s if self._pressed else 0
        if not self._pressed:
            self.create_rectangle(s, s, w, h, fill=SHADOW, width=0)
        x0, y0, x1, y1 = off, off, w - s + off, h - s + off
        face = self.color if self._hover else PANEL
        ink = BG if self._hover else self.color
        self.create_rectangle(x0, y0, x1, y1, fill=self.color, width=0)
        self.create_rectangle(x0 + PX, y0 + PX, x1 - PX, y1 - PX, fill=face, width=0)
        # notch the corners so the outline reads as pixel art, not a box
        for cx, cy in ((x0, y0), (x1 - PX, y0), (x0, y1 - PX), (x1 - PX, y1 - PX)):
            self.create_rectangle(cx, cy, cx + PX, cy + PX, fill=self["bg"], width=0)
        tw = pixel_text_width(self.text, self.scale)
        th = GLYPH_H * self.scale
        tx = x0 + ((x1 - x0) - tw) // 2
        ty = y0 + ((y1 - y0) - th) // 2
        draw_pixel_text(self, tx, ty, self.text, self.scale, ink)


class QuestPanel(tk.Frame):
    """ACTIVE QUESTS list: one row per launched fake process.

    Rows are created/destroyed only when the quest set changes; refresh()
    redraws the row canvases in place so the STOP buttons keep working.
    """

    ROW_H     = 30
    BLOCKS    = 20      # progress bar segments
    BLOCK_W   = 8
    BLOCK_GAP = 2
    STATUS_COLOR = {RUNNING: CYAN, DONE: GREEN, STOPPED: RED}

    def __init__(self, master, app, max_rows, view_all=False):
        super().__init__(master, bg=BORDER, padx=PX, pady=PX)
        self.app, self.max_rows = app, max_rows
        inner = tk.Frame(self, bg=PANEL_DARK)
        inner.pack(fill="both", expand=True)

        head = tk.Frame(inner, bg=PANEL_DARK)
        head.pack(side="top", fill="x", padx=6, pady=(4, 2))
        self.head_c = tk.Canvas(head, width=420, height=24, bg=PANEL_DARK,
                                highlightthickness=0, bd=0)
        self.head_c.pack(side="left")
        PixelButton(head, "STOP ALL", app.stop_all_quests, width=124, height=26,
                    color=RED, scale=2, bg=PANEL_DARK).pack(side="right")
        if view_all:
            PixelButton(head, "VIEW ALL", lambda: app.show("active"), width=124, height=26,
                        color=CYAN, scale=2, bg=PANEL_DARK).pack(side="right", padx=(0, 8))

        self.body = tk.Frame(inner, bg=PANEL_DARK)
        self.body.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 4))
        self.empty = tk.Label(self.body, text="No active quests - launch a game to start one.",
                              bg=PANEL_DARK, fg=MUTED, font=app.font_small, anchor="w")
        self.rows: dict = {}   # qid -> (frame, canvas, button)
        self.refresh()

    def refresh(self) -> None:
        tracker = self.app.quests
        shown = tracker.quests[: self.max_rows]
        shown_ids = [q.qid for q in shown]

        for qid in list(self.rows):
            if qid not in shown_ids:
                self.rows.pop(qid)[0].destroy()
        for quest in shown:
            if quest.qid not in self.rows:
                self.rows[quest.qid] = self._make_row(quest)
                self.rows[quest.qid][0].pack(side="top", fill="x", pady=1)

        if shown:
            self.empty.pack_forget()
        else:
            self.empty.pack(side="top", fill="x", pady=4)

        c = self.head_c
        c.delete("all")
        x = draw_pixel_text(c, 0, 5, "ACTIVE QUESTS", 2, CYAN)
        x += 12 + draw_pixel_text(c, x + 12, 5, str(len(tracker.quests)), 2, MAGENTA)
        extra = len(tracker.quests) - len(shown)
        if extra > 0:
            draw_pixel_text(c, x + 16, 5, f"{extra} MORE", 2, MUTED)

        for quest in shown:
            self._draw_row(quest)

    def _make_row(self, quest):
        frame = tk.Frame(self.body, bg=PANEL_DARK)
        canvas = tk.Canvas(frame, width=640, height=self.ROW_H - 4, bg=PANEL_DARK,
                           highlightthickness=0, bd=0)
        canvas.pack(side="left")
        btn = PixelButton(frame, "STOP", lambda qid=quest.qid: self.app.stop_quest(qid),
                          width=96, height=self.ROW_H - 4, color=RED, scale=2, bg=PANEL_DARK)
        btn.pack(side="right")
        return frame, canvas, btn

    def _draw_row(self, quest):
        tracker = self.app.quests
        _frame, c, btn = self.rows[quest.qid]
        status = tracker.status(quest)
        h = self.ROW_H - 4
        c.delete("all")
        name = quest.name if len(quest.name) <= 26 else quest.name[:25] + "~"
        c.create_text(4, h // 2, text=name, anchor="w", fill=TEXT, font=self.app.font_small)

        bx, by = 236, 5
        filled = round(tracker.fraction_left(quest) * self.BLOCKS)
        if status == RUNNING:
            filled = max(1, filled)
        for i in range(self.BLOCKS):
            x0 = bx + i * (self.BLOCK_W + self.BLOCK_GAP)
            if status == DONE:
                fill = GREEN
            elif i < filled:
                fill = CYAN if status == RUNNING else MUTED
            else:
                fill = PANEL
            c.create_rectangle(x0, by, x0 + self.BLOCK_W, h - by, fill=fill, width=0)

        ty = (h - GLYPH_H * 2) // 2
        draw_pixel_text(c, 452, ty, format_mmss(tracker.remaining(quest)), 2, WHITE)
        draw_pixel_text(c, 532, ty, status, 2, self.STATUS_COLOR[status])

        label = "CLEAR" if status == STOPPED else "STOP"
        if btn.text != label:
            btn.text = label
            btn.color = MUTED if status == STOPPED else RED
            btn._draw()


def _tag_for_color(color) -> str:
    """Map an ANSI colour from ui.Colors to a log tag."""
    return {
        Colors.GREEN: "ok", Colors.YELLOW: "warn", Colors.RED: "err",
        Colors.CYAN: "info", Colors.MAGENTA: "tip", Colors.GRAY: "muted",
    }.get(color, "plain")


def _pick_font_family(root) -> tuple:
    families = set(tkfont.families(root))
    for family, size in FONT_CANDIDATES:
        if family in families:
            return (family, size)
    return FONT_FALLBACK


# ── Application ───────────────────────────────────────────────────────────────

class OrbifierApp:
    """Single-window app: a header-less screen host, shared log and status bar."""

    def __init__(self, root: tk.Tk, check_updates: bool = True):
        self.root = root
        self.font = _pick_font_family(root)
        self.font_small = (self.font[0], max(8, self.font[1] - 1))

        root.title("Orbifier")
        try:
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
            root.iconbitmap(str(base / "docs" / "orbifier.ico"))
        except Exception:
            pass  # icon is cosmetic; keep the Tk default if it cannot load
        root.geometry(f"{WIN_W}x{WIN_H}")
        root.resizable(False, False)
        root.configure(bg=BG)

        self.faker = GameFaker()
        self.db: DiscordGamesDB | None = None
        self.db_loading = False
        self.busy_count = 0
        self._busy_phase = 0
        self._queue: "queue.Queue" = queue.Queue()

        self.db_results: list = []
        self.steam_results: list = []
        self.output_directory = tk.StringVar(value=str(self.faker.desktop_path / config.FAKE_EXE_DIR))

        self.quests = QuestTracker(config.QUEST_MINUTES * 60)
        self.quest_panels: list = []

        self._build_layout()
        self.screens = {
            "home":     self._build_home(),
            "database": self._build_database(),
            "manual":   self._build_manual(),
            "steam":    self._build_steam(),
            "credits":  self._build_credits(),
            "active":   self._build_active(),
        }
        self.current = None

        # Route every print_color() from the service modules into the log panel.
        ui.set_output_hook(lambda text, color: self.post(
            lambda: self.log(str(text).strip("\n"), _tag_for_color(color))))
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.show("home")
        self.log(f"Orbifier v{config.VERSION} ready.", "ok")
        self.log("Educational use only. Use at your own risk. Faking game activity may violate Discord's ToS.", "warn")
        if is_process_elevated():
            self.log(f"[!] {ELEVATED_WARNING}", "warn")
        self._drain_queue()
        self._animate_busy()
        self._tick_quests()
        if check_updates:
            self._start_update_check()

    # ── threading plumbing ────────────────────────────────────────────────────
    def post(self, fn) -> None:
        """Schedule *fn* on the Tk main thread (safe from any thread)."""
        self._queue.put(fn)

    def _drain_queue(self):
        try:
            while True:
                fn = self._queue.get_nowait()
                try:
                    fn()
                except Exception as e:  # never let a callback kill the pump
                    self.log(f"[ERROR] UI callback failed: {e}", "err")
        except queue.Empty:
            pass
        self.root.after(30, self._drain_queue)

    def run_task(self, label: str, fn, on_done=None, on_error=None) -> None:
        """Run *fn* on a daemon thread; deliver its result to *on_done* on the UI thread.

        Errors are logged to the log panel; *on_error* (if given) is then called
        on the UI thread with no arguments.
        """
        self._busy(+1, label)

        def worker():
            try:
                result = fn()
            except SystemExit:
                # updater restarts the app via sys.exit(0) after launching the new exe
                self.post(self.close)
                return
            except OrbifierError as e:
                self.post(lambda e=e: self.log(f"[ERROR] {e}", "err"))
                if on_error is not None:
                    self.post(on_error)
            except Exception as e:
                traceback.print_exc()
                self.post(lambda e=e: self.log(f"[ERROR] Unexpected error: {e}", "err"))
                if on_error is not None:
                    self.post(on_error)
            else:
                if on_done is not None:
                    self.post(lambda: on_done(result))
            finally:
                self.post(lambda: self._busy(-1))

        threading.Thread(target=worker, daemon=True).start()

    def _busy(self, delta: int, label: str = "") -> None:
        self.busy_count = max(0, self.busy_count + delta)
        if self.busy_count and label:
            self.status_var.set(label.upper())
        elif not self.busy_count:
            self.status_var.set("READY")

    def _guard_busy(self) -> bool:
        if self.busy_count:
            self.log("[!] Please wait for the current task to finish", "warn")
            return True
        return False

    def _animate_busy(self):
        c = self.busy_canvas
        blocks = c.find_withtag("blk")
        if self.busy_count:
            self._busy_phase = (self._busy_phase + 1) % len(blocks)
            for i, item in enumerate(blocks):
                dist = (self._busy_phase - i) % len(blocks)
                c.itemconfigure(item, fill=CYAN if dist == 0 else MAGENTA if dist == 1
                                else "#3d2a6b" if dist == 2 else PANEL)
        else:
            for item in blocks:
                c.itemconfigure(item, fill=PANEL)
            c.itemconfigure(blocks[0], fill=GREEN)
        self.root.after(120, self._animate_busy)

    # ── layout ────────────────────────────────────────────────────────────────
    def _build_layout(self):
        self.host = tk.Frame(self.root, bg=BG, width=WIN_W, height=HOST_H)
        self.host.pack(side="top", fill="x")
        self.host.pack_propagate(False)

        log_wrap = tk.Frame(self.root, bg=BG, width=WIN_W, height=LOG_H)
        log_wrap.pack(side="top", fill="x")
        log_wrap.pack_propagate(False)
        border = tk.Frame(log_wrap, bg=BORDER, padx=PX, pady=PX)
        border.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self.log_text = tk.Text(
            border, bg=PANEL_DARK, fg=TEXT, font=self.font_small, relief="flat",
            bd=0, padx=8, pady=4, wrap="word", state="disabled", cursor="arrow",
            highlightthickness=0, insertbackground=CYAN,
        )
        self.log_text.pack(fill="both", expand=True)
        for tag, color in (("ok", GREEN), ("warn", YELLOW), ("err", RED),
                           ("info", CYAN), ("tip", MAGENTA), ("muted", MUTED),
                           ("plain", TEXT)):
            self.log_text.tag_configure(tag, foreground=color)

        status = tk.Frame(self.root, bg=PANEL, height=STATUS_H)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        tk.Frame(status, bg=BORDER, height=PX).pack(side="top", fill="x")
        self.status_var = tk.StringVar(value="READY")
        tk.Label(status, textvariable=self.status_var, bg=PANEL, fg=CYAN,
                 font=self.font_small, anchor="w").pack(side="left", padx=12)
        tk.Label(status, text=f"v{config.VERSION}  ·  {config.DEVELOPER}  ·  Educational use only", bg=PANEL,
                 fg=MUTED, font=self.font_small).pack(side="right", padx=12)
        self.busy_canvas = tk.Canvas(status, width=8 * 10, height=12, bg=PANEL,
                                     highlightthickness=0, bd=0)
        self.busy_canvas.pack(side="right", padx=8)
        for i in range(8):
            self.busy_canvas.create_rectangle(i * 10, 2, i * 10 + 8, 10, fill=PANEL,
                                              width=0, tags=("blk",))

    def log(self, message: str, tag: str = "plain") -> None:
        t = self.log_text
        t.configure(state="normal")
        t.insert("end", message + "\n", tag)
        t.configure(state="disabled")
        t.see("end")

    def show(self, name: str) -> None:
        if self.current:
            self.screens[self.current].pack_forget()
        self.current = name
        self.screens[name].pack(fill="both", expand=True)
        hook = getattr(self, f"_on_show_{name}", None)
        if hook:
            hook()

    def close(self) -> None:
        if hasattr(self, "tray") and self.tray:
            try:
                self.tray.stop()
                self.tray = None
            except Exception:
                pass
        ui.set_output_hook(None)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def hide_to_tray(self) -> None:
        """Minimize the main Orbifier window to system tray."""
        if sys.platform != "win32":
            self.root.iconify()
            return
        self._saved_geometry = self.root.geometry()
        self.root.withdraw()
        try:
            from .tray import TrayIcon
            active = len(self.quests.quests)
            tip = f"Orbifier ({active} active quest{'s' if active != 1 else ''})"

            def _open():
                self.root.after(0, self.restore_from_tray)

            def _exit():
                self.root.after(0, self.close)

            icon_file = Path(__file__).parent.parent / "docs" / "orbifier.ico"
            self.tray = TrayIcon(
                tooltip=tip,
                icon_path=str(icon_file) if icon_file.exists() else None,
                on_open=_open,
                on_exit=_exit,
            )
            self.tray.start()
        except Exception as e:
            self.log(f"[!] Could not hide to tray: {e}", "warn")
            self.root.deiconify()

    def restore_from_tray(self) -> None:
        """Restore the main window from system tray."""
        if hasattr(self, "tray") and self.tray:
            self.tray.stop()
            self.tray = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # ── shared building helpers ──────────────────────────────────────────────
    def _screen(self, title: str, active_button: bool = True) -> tk.Frame:
        """Sub-screen frame with a pixel header, a BACK and an ACTIVE button."""
        frame = tk.Frame(self.host, bg=BG)
        header = tk.Frame(frame, bg=BG)
        header.pack(side="top", fill="x", padx=12, pady=(10, 6))
        OrbLogo(header, scale=2).pack(side="left")
        title_c = tk.Canvas(header, width=pixel_text_width(title, 4) + 8, height=7 * 4 + 8,
                            bg=BG, highlightthickness=0, bd=0)
        title_c.pack(side="left", padx=12)
        draw_pixel_text(title_c, 2, 2, title, 4, CYAN, shadow=ORB_BASE_PALETTE["2"])
        PixelButton(header, "< BACK", lambda: self.show("home"), width=120, height=40,
                    color=MAGENTA, scale=2).pack(side="right")
        if active_button:
            PixelButton(header, "ACTIVE", lambda: self.show("active"), width=120, height=40,
                        color=GREEN, scale=2).pack(side="right", padx=(0, 8))
        PixelButton(header, "TRAY", self.hide_to_tray, width=90, height=40,
                    color=CYAN, scale=2).pack(side="right", padx=(0, 8))
        tk.Frame(frame, bg=BORDER, height=PX).pack(side="top", fill="x", padx=12, pady=(0, 8))
        return frame

    def _label(self, master, text, fg=MUTED):
        return tk.Label(master, text=text, bg=BG, fg=fg, font=self.font, anchor="w")

    def _entry(self, master, width=40):
        return tk.Entry(
            master, width=width, bg=PANEL_DARK, fg=TEXT, font=self.font,
            relief="flat", bd=0, highlightthickness=PX, highlightbackground=BORDER,
            highlightcolor=CYAN, insertbackground=CYAN, insertwidth=6,
            selectbackground=MAGENTA, selectforeground=BG,
        )

    def _listbox(self, master, height=8):
        return tk.Listbox(
            master, height=height, bg=PANEL_DARK, fg=TEXT, font=self.font,
            relief="flat", bd=0, highlightthickness=PX, highlightbackground=BORDER,
            highlightcolor=CYAN, selectbackground=MAGENTA, selectforeground=BG,
            activestyle="none", exportselection=False,
        )

    def _row(self, frame, pady=4):
        row = tk.Frame(frame, bg=BG)
        row.pack(side="top", fill="x", padx=12, pady=pady)
        return row

    # ── Home ──────────────────────────────────────────────────────────────────
    def _build_home(self) -> tk.Frame:
        frame = tk.Frame(self.host, bg=BG)
        top = tk.Frame(frame, bg=BG)
        top.pack(side="top", fill="x", pady=(14, 4), padx=12)
        PixelButton(top, "TRAY", self.hide_to_tray, width=100, height=40,
                    color=CYAN, scale=2).pack(side="right")
        self.home_logo = OrbLogo(top, scale=6)
        self.home_logo.pack(side="left", padx=(0, 18))
        title = "ORBIFIER"
        c = tk.Canvas(top, width=pixel_text_width(title, 8) + 10, height=96,
                      bg=BG, highlightthickness=0, bd=0)
        c.pack(side="left")
        draw_pixel_text(c, 2, 4, title, 8, CYAN, shadow=MAGENTA)
        sub = f"V{config.VERSION}  -  DISCORD QUEST HELPER"
        draw_pixel_text(c, 4, 7 * 8 + 18, sub, 2, MUTED)
        tk.Label(frame, text="EDUCATIONAL USE ONLY  -  USE AT YOUR OWN RISK", bg=BG, fg=RED,
                 font=self.font_small).pack(side="top")

        grid = tk.Frame(frame, bg=BG)
        grid.pack(side="top", pady=(8, 0))
        buttons = [
            ("DATABASE QUEST", "database", CYAN),
            ("MANUAL EXE", "manual", GREEN),
            ("STEAM QUEST", "steam", MAGENTA),
            ("CREDITS", "credits", YELLOW),
        ]
        self.home_buttons = {}
        for i, (text, target, color) in enumerate(buttons):
            btn = PixelButton(grid, text, lambda t=target: self.show(t),
                              width=350, height=56, color=color, scale=3)
            btn.grid(row=i // 2, column=i % 2, padx=10, pady=6)
            self.home_buttons[target] = btn

        self.home_quests = QuestPanel(frame, self, max_rows=2, view_all=True)
        self.home_quests.pack(side="top", fill="x", padx=12, pady=(10, 0))
        self.quest_panels.append(self.home_quests)
        return frame

    # ── Database ──────────────────────────────────────────────────────────────
    def _build_database(self) -> tk.Frame:
        frame = self._screen("DATABASE QUEST")
        self._directory_row(frame, self.output_directory, "OUTPUT FOLDER")
        row = self._row(frame)
        self._label(row, "SEARCH").pack(side="left")
        self.db_query = self._entry(row, width=44)
        self.db_query.pack(side="left", padx=8, ipady=4)
        self.db_query.bind("<Return>", lambda _e: self.db_search())
        PixelButton(row, "SEARCH", self.db_search, width=120, height=38,
                    scale=2).pack(side="left")

        self.db_list = self._listbox(frame, height=6)
        self.db_list.pack(side="top", fill="x", padx=12, pady=4)

        row2 = self._row(frame)
        self._label(row2, "OVERRIDE EXE").pack(side="left")
        self.db_override = self._entry(row2, width=16)
        self.db_override.pack(side="left", padx=4, ipady=4)
        self._label(row2, "MIN").pack(side="left", padx=(4, 0))
        self.db_minutes = self._entry(row2, width=3)
        self.db_minutes.insert(0, str(config.QUEST_MINUTES))
        self.db_minutes.pack(side="left", padx=4, ipady=4)
        self.db_autoclose = tk.BooleanVar(value=config.AUTO_CLOSE)
        tk.Checkbutton(row2, text="AUTO", variable=self.db_autoclose, bg=BG, fg=TEXT,
                       selectcolor=PANEL_DARK, activebackground=BG, activeforeground=TEXT,
                       font=self.font_small).pack(side="left", padx=4)
        PixelButton(row2, "DELETE", self.db_delete, width=90, height=38,
                    color=RED, scale=2).pack(side="right", padx=(4, 0))
        PixelButton(row2, "LAUNCH", self.db_launch, width=110, height=38,
                    color=GREEN, scale=2).pack(side="right")
        self.db_info = tk.StringVar(value="Database not loaded")
        tk.Label(row2, textvariable=self.db_info, bg=BG, fg=MUTED,
                 font=self.font_small).pack(side="right", padx=6)
        return frame

    def _on_show_database(self):
        self.db_query.focus_set()
        self.ensure_db_loaded()

    def ensure_db_loaded(self):
        if self.db is not None or self.db_loading:
            return
        self.db_loading = True
        self.db_info.set("Loading...")

        def done(db):
            self.db = db
            self.db_loading = False
            self.db_info.set(f"{db.source} ({len(db.games)} games)")
            self.log("[*] Search by name or abbreviation (PUBG, Fortnite, Valorant...)", "info")

        def failed():
            self.db_loading = False
            self.db_info.set("Load failed - search to retry")

        self.run_task("Loading games database", DiscordGamesDB, done, failed)

    def db_search(self):
        query = self.db_query.get().strip()
        if self.db is None:
            self.log("[!] Database not loaded yet", "warn")
            self.ensure_db_loaded()
            return
        if not query:
            self.log("[!] Type a game name to search", "warn")
            return
        self.db_results = self.db.search_games(query)
        self.db_list.delete(0, "end")
        if not self.db_results:
            self.log(f"[ERROR] No games found for '{query}'", "err")
            self.log("[!] Try a different search term or abbreviation", "warn")
            return
        for game in self.db_results:
            exe = self.db.get_win32_executable(game) or "(no win32 exe)"
            self.db_list.insert("end", f"{game.get('name', 'Unknown')} — {exe}"
                                       f"   · app id {game.get('id', 'N/A')}")
        self.db_list.selection_set(0)
        self.log(f"[OK] Found {len(self.db_results)} game(s) for '{query}'", "ok")

    def db_launch(self):
        if self._guard_busy():
            return
        sel = self.db_list.curselection()
        if self.db is None or not sel:
            self.log("[!] Search and select a game first", "warn")
            return
        game = self.db_results[sel[0]]
        exe_name = self.db_override.get().strip() or self.db.get_win32_executable(game)
        if not exe_name:
            self.log("[ERROR] No Windows executable found for this game", "err")
            self.log("[!] Type the exe name in OVERRIDE EXE and launch again", "warn")
            return
        try:
            target = self.faker.game_path(exe_name, Path(self.output_directory.get()))
        except ValueError as e:
            self.log(str(e), "err")
            return
        exe_hint = ""
        candidates = self.db._filter_win32_exes(game, skip_patterns=True)
        if not self.db_override.get().strip() and len(candidates) > 1:
            shown = ", ".join(candidates[:5])
            if len(candidates) > 5:
                shown += f" (+{len(candidates) - 5} more)"
            exe_hint = (f"\nThis game has {len(candidates)} executables: {shown}\n"
                        "The first is used; type another in OVERRIDE EXE to change it.\n")
        try:
            mins = float(self.db_minutes.get().strip())
            if mins <= 0:
                mins = config.QUEST_MINUTES
        except ValueError:
            mins = config.QUEST_MINUTES
        auto_close = self.db_autoclose.get()

        if not messagebox.askyesno(
            "Orbifier",
            f"Game: {game.get('name')}\nDiscord app id: {game.get('id')}\n"
            "The quest only progresses if this exact app id matches the quest's game.\n\n"
            f"Executable: {exe_name}\nPath: {target}\n"
            f"Timer: {mins:g} minutes  ·  Auto-close: {'Yes' if auto_close else 'No'}\n"
            f"{exe_hint}"
            "\nUse at your own risk.\nCreate and launch?",
            parent=self.root,
        ):
            self.log("[!] Operation cancelled", "warn")
            return
        self._create_and_launch(
            exe_name,
            "[OK] Setup complete! Discord should detect the game.",
            minutes=mins,
            auto_close=auto_close,
        )

    def db_delete(self):
        if self._guard_busy():
            return
        sel = self.db_list.curselection()
        if not sel:
            self.log("[!] Search and select a game first", "warn")
            return
        game = self.db_results[sel[0]]
        override = self.db_override.get().strip()
        exe_name = override or self.db.get_win32_executable(game)
        if not exe_name:
            self.log("[ERROR] No Windows executable found for this game", "err")
            return
        output_dir = Path(self.output_directory.get())
        try:
            target = self.faker.game_path(exe_name, output_dir)
        except ValueError as e:
            self.log(str(e), "err")
            return

        if not target.exists() and not (target.parent.exists() and target.parent != output_dir):
            self.log(f"[!] No existing executable found at {target} to delete.", "warn")
            return

        if not messagebox.askyesno(
            "Orbifier - Delete Game Setup",
            f"Game: {game.get('name')}\nExecutable: {exe_name}\nPath: {target}\n\n"
            "Proceed with delete?",
            parent=self.root,
        ):
            self.log("[!] Delete cancelled", "warn")
            return

        def work():
            for q in list(self.quests.quests):
                if q.exe_path and Path(q.exe_path).resolve() == target.resolve():
                    self.quests.stop(q)
            return self.faker.delete_fake_game(exe_name, output_dir=output_dir)

        def done(res):
            if res.get("executable") and res["executable"][1]:
                self.log(f"[OK] Deleted executable: {res['executable'][0].name}", "ok")
                if res.get("folder") and res["folder"][1]:
                    self.log(f"[OK] Cleaned up folder: {res['folder'][0].name}", "ok")
                self.log(f"[OK] Deletion complete for {game.get('name')}.", "ok")
            else:
                self.log("[*] No executable found to delete.", "info")

        self.run_task(f"Deleting {exe_name}", work, done)

    # ── Manual ────────────────────────────────────────────────────────────────
    def _build_manual(self) -> tk.Frame:
        frame = self._screen("MANUAL EXE")
        self._directory_row(frame, self.output_directory, "OUTPUT FOLDER")
        for line, fg in (
            ("Enter the exact process name Discord expects.", TEXT),
            ("Examples:  TslGame.exe (PUBG)   League of Legends.exe   Overwatch.exe", MUTED),
            ("The name must match exactly (case-sensitive on some systems).", MUTED),
        ):
            self._label(self._row(frame, pady=2), line, fg=fg).pack(side="left")
        row = self._row(frame, pady=16)
        self._label(row, "EXE NAME").pack(side="left")
        self.manual_exe = self._entry(row, width=24)
        self.manual_exe.pack(side="left", padx=4, ipady=4)
        self.manual_exe.bind("<Return>", lambda _e: self.manual_launch())
        self._label(row, "MIN").pack(side="left", padx=(4, 0))
        self.manual_minutes = self._entry(row, width=4)
        self.manual_minutes.insert(0, str(config.QUEST_MINUTES))
        self.manual_minutes.pack(side="left", padx=4, ipady=4)
        self.manual_autoclose = tk.BooleanVar(value=config.AUTO_CLOSE)
        tk.Checkbutton(row, text="AUTO-CLOSE", variable=self.manual_autoclose, bg=BG, fg=TEXT,
                       selectcolor=PANEL_DARK, activebackground=BG, activeforeground=TEXT,
                       font=self.font_small).pack(side="left", padx=4)
        PixelButton(row, "DELETE", self.manual_delete, width=90, height=38,
                    color=RED, scale=2).pack(side="left", padx=4)
        PixelButton(row, "LAUNCH", self.manual_launch, width=120, height=38,
                    color=GREEN, scale=2).pack(side="left", padx=4)
        return frame

    def _on_show_manual(self):
        self.manual_exe.focus_set()

    def manual_launch(self):
        if self._guard_busy():
            return
        exe_name = self.manual_exe.get().strip()
        if not exe_name:
            self.log("[!] Type an executable name first", "warn")
            return
        try:
            target = self.faker.game_path(exe_name, Path(self.output_directory.get()))
        except ValueError as e:
            self.log(str(e), "err")
            return
        try:
            mins = float(self.manual_minutes.get().strip())
            if mins <= 0:
                mins = config.QUEST_MINUTES
        except ValueError:
            mins = config.QUEST_MINUTES
        auto_close = self.manual_autoclose.get()

        if not messagebox.askyesno(
            "Orbifier",
            f"Executable: {exe_name}\nPath: {target}\n"
            f"Timer: {mins:g} minutes  ·  Auto-close: {'Yes' if auto_close else 'No'}\n\n"
            "Use at your own risk.\nCreate and launch?",
            parent=self.root,
        ):
            self.log("[!] Operation cancelled", "warn")
            return
        self._create_and_launch(
            exe_name,
            "[OK] Setup complete!",
            minutes=mins,
            auto_close=auto_close,
        )

    def manual_delete(self):
        if self._guard_busy():
            return
        exe_name = self.manual_exe.get().strip()
        if not exe_name:
            self.log("[!] Type an executable name first", "warn")
            return
        output_dir = Path(self.output_directory.get())
        try:
            target = self.faker.game_path(exe_name, output_dir)
        except ValueError as e:
            self.log(str(e), "err")
            return

        if not target.exists() and not (target.parent.exists() and target.parent != output_dir):
            self.log(f"[!] No existing executable found at {target} to delete.", "warn")
            return

        if not messagebox.askyesno(
            "Orbifier - Delete Game Setup",
            f"Executable: {exe_name}\nPath: {target}\n\nProceed with delete?",
            parent=self.root,
        ):
            self.log("[!] Delete cancelled", "warn")
            return

        def work():
            for q in list(self.quests.quests):
                if q.exe_path and Path(q.exe_path).resolve() == target.resolve():
                    self.quests.stop(q)
            return self.faker.delete_fake_game(exe_name, output_dir=output_dir)

        def done(res):
            if res.get("executable") and res["executable"][1]:
                self.log(f"[OK] Deleted executable: {res['executable'][0].name}", "ok")
                if res.get("folder") and res["folder"][1]:
                    self.log(f"[OK] Cleaned up folder: {res['folder'][0].name}", "ok")
                self.log(f"[OK] Deletion complete.", "ok")
            else:
                self.log("[*] No executable found to delete.", "info")

        self.run_task(f"Deleting {exe_name}", work, done)

    def _create_and_launch(
        self,
        exe_name: str,
        done_msg: str,
        minutes: float = 15.0,
        auto_close: bool = True,
    ) -> None:
        """Shared by Database and Manual: copy to the selected folder and launch."""
        faker = self.faker
        output_dir = Path(self.output_directory.get())
        duration_s = max(1.0, float(minutes) * 60.0)
        start_time = time.time()

        def work():
            path = faker.create_fake_game(exe_name, output_dir=output_dir)
            if not path:
                return False
            proc = faker.launch_executable(
                path,
                duration_s=duration_s,
                start_time=start_time,
                auto_close=auto_close,
            )
            return path, proc

        def done(ok):
            if ok:
                path, proc = ok
                self._track_quest(path, proc, duration_s=duration_s, auto_close=auto_close,
                                  cleanup_root=output_dir)
                self.log(done_msg, "ok")
                self.log("[!] IMPORTANT: Discord MUST be running for the spoofing to work", "warn")
                self.log("[*] Keep the process running or in tray until quest is complete", "info")

        self.run_task(f"Creating {exe_name}", work, done)

    # ── Steam ─────────────────────────────────────────────────────────────────
    def _directory_row(self, frame, variable, label):
        row = self._row(frame, pady=2)
        self._label(row, label).pack(side="left")
        entry = self._entry(row, width=38)
        entry.configure(textvariable=variable)
        entry.pack(side="left", fill="x", expand=True, padx=8, ipady=3)

        def browse():
            chosen = filedialog.askdirectory(parent=self.root, initialdir=variable.get() or str(Path.home()))
            if chosen:
                variable.set(chosen)

        PixelButton(row, "BROWSE", browse, width=100, height=30, scale=2).pack(side="right")

    def _build_steam(self) -> tk.Frame:
        frame = self._screen("STEAM QUEST")
        row = self._row(frame, pady=2)
        self._label(row, "STEAM PATH").pack(side="left")
        self.steam_path = self._entry(row, width=34)
        self.steam_path.pack(side="left", padx=8, ipady=3)
        PixelButton(row, "DETECT", self.steam_detect, width=120, height=36,
                    scale=2).pack(side="left")
        def browse_steam():
            chosen = filedialog.askdirectory(parent=self.root, title="Select Steam library or steamapps folder")
            if chosen:
                self.steam_path.delete(0, "end")
                self.steam_path.insert(0, chosen)
        PixelButton(row, "BROWSE", browse_steam, width=100, height=36,
                    scale=2).pack(side="left", padx=4)

        row2 = self._row(frame, pady=2)
        self._label(row2, "NAME / APP ID").pack(side="left")
        self.steam_query = self._entry(row2, width=36)
        self.steam_query.pack(side="left", padx=8, ipady=3)
        self.steam_query.bind("<Return>", lambda _e: self.steam_search())
        PixelButton(row2, "SEARCH", self.steam_search, width=120, height=36,
                    scale=2).pack(side="left")

        self.steam_list = self._listbox(frame, height=3)
        self.steam_list.pack(side="top", fill="x", padx=12, pady=4)

        details = self._row(frame, pady=2)
        self._label(details, "INSTALL FOLDER").pack(side="left")
        self.steam_install = self._entry(details, width=26)
        self.steam_install.pack(side="left", padx=4, ipady=3)
        self._label(details, "blank = detected", fg=MUTED).pack(side="left")

        mode_row = self._row(frame, pady=2)
        self.steam_installed = tk.BooleanVar(value=True)
        tk.Checkbutton(mode_row, text="INSTALLED MANIFEST (4)  /  unchecked: LEGACY (1026)",
                       variable=self.steam_installed, bg=BG, fg=TEXT, selectcolor=PANEL_DARK,
                       activebackground=BG, activeforeground=TEXT,
                       font=self.font_small).pack(side="left")

        row3 = self._row(frame, pady=2)
        self._label(row3, "OVERRIDE EXE").pack(side="left")
        self.steam_override = self._entry(row3, width=20)
        self.steam_override.pack(side="left", padx=4, ipady=3)
        self._label(row3, "MIN").pack(side="left", padx=(4, 0))
        self.steam_minutes = self._entry(row3, width=4)
        self.steam_minutes.insert(0, str(config.QUEST_MINUTES))
        self.steam_minutes.pack(side="left", padx=4, ipady=3)
        self.steam_autoclose = tk.BooleanVar(value=config.AUTO_CLOSE)
        tk.Checkbutton(row3, text="AUTO-CLOSE", variable=self.steam_autoclose, bg=BG, fg=TEXT,
                       selectcolor=PANEL_DARK, activebackground=BG, activeforeground=TEXT,
                       font=self.font_small).pack(side="left", padx=4)
        PixelButton(row3, "DELETE", self.steam_delete, width=90, height=38,
                    color=RED, scale=2).pack(side="right", padx=(4, 0))
        PixelButton(row3, "CREATE & LAUNCH", self.steam_create, width=180, height=38,
                    color=GREEN, scale=2).pack(side="right")
        return frame

    def _on_show_steam(self):
        if not self.steam_path.get().strip():
            self.steam_detect()
        self.log("[*] Steam mode: fake appmanifest + exe for games that verify Steam ownership", "info")
        self.log("[*] Demos and DLCs are separate entries - pick the right one!", "warn")

    def steam_detect(self):
        def done(path):
            if path and path.exists():
                self.steam_path.delete(0, "end")
                self.steam_path.insert(0, str(path))
                self.log(f"[OK] Steam found at: {path}", "ok")
            else:
                self.log("[!] Could not locate Steam automatically.", "warn")
                self.log("[*] Enter the path manually (e.g. C:/Program Files (x86)/Steam)", "info")

        self.run_task("Detecting Steam", steam.get_steam_path, done)

    def steam_search(self):
        query = self.steam_query.get().strip()
        if not query:
            self.log("[!] Type a game name to search", "warn")
            return

        def done(results):
            self.steam_results = results
            self.steam_list.delete(0, "end")
            if not results:
                self.log(f"[ERROR] No results found for '{query}'", "err")
                self.log("[!] Try a different search term", "warn")
                return
            for game in results:
                self.steam_list.insert("end", f"{game['name']}  (AppID: {game['id']})")
            self.steam_list.selection_set(0)
            self.log(f"[OK] Found {len(results)} result(s)", "ok")

        if query.isascii() and query.isdigit() and int(query) > 0:
            done([{"id": int(query), "name": f"App {int(query)}"}])
        else:
            self.run_task(f"Searching Steam for '{query}'", lambda: steam.search_steam_games(query), done)

    def steam_create(self):
        if self._guard_busy():
            return
        raw_path = self.steam_path.get().strip()
        sel = self.steam_list.curselection()
        if not raw_path:
            self.log("[!] No Steam path provided.", "err")
            return
        if not sel:
            self.log("[!] Search and select a game first", "warn")
            return
        steam_path = Path(raw_path)
        game = self.steam_results[sel[0]]
        appid = int(game["id"])
        override = self.steam_override.get().strip()
        install_override = self.steam_install.get().strip()
        self.log(f"[OK] Selected: {game['name']} (AppID: {appid})", "ok")

        def got_info(info):
            if not info:
                # CLI asks for these interactively; GUI falls back to the search
                # result name and the override field.
                self.log("[!] Could not fetch app info automatically.", "warn")
                self.log("[*] Using the store name; set OVERRIDE EXE to the real exe path", "info")
                info = {"name": game["name"], "installdir": game["name"],
                        "executable": "Game.exe", "depot_id": None}
                if appid == 4080220:
                    info.update(name="EA SPORTS FC™ 27", installdir="EA SPORTS FC 27", executable="fc27.exe")
            if override:
                info["executable"] = override.replace("\\", "/")
            if install_override:
                info["installdir"] = install_override
            info["installdir"] = steam.sanitize_installdir(info["installdir"])
            self._steam_confirm_and_write(steam_path, appid, info)

        self.run_task(f"Fetching Steam app info for {appid}",
                      lambda: steam.fetch_steam_app_info(appid), got_info)

    def _steam_confirm_and_write(self, steam_path: Path, appid: int, info: dict):
        try:
            fake_exe_path = steam.steam_fake_exe_path(steam_path, info["installdir"], info["executable"])
        except ValueError as e:
            self.log(str(e), "err")
            return
        acf_path = steam.steamapps_path(steam_path) / f"appmanifest_{appid}.acf"
        manifest_mode = "installed" if self.steam_installed.get() else "legacy"
        warn = "" if steam_path.exists() else "\n\nWARNING: Steam path does not exist!"
        overwrite_note = "\n\n(Existing manifest or executable will be overwritten)" if (acf_path.exists() or fake_exe_path.exists()) else ""

        try:
            mins = float(self.steam_minutes.get().strip())
            if mins <= 0:
                mins = config.QUEST_MINUTES
        except ValueError:
            mins = config.QUEST_MINUTES
        auto_close = self.steam_autoclose.get()

        if not messagebox.askyesno(
            "Orbifier - Steam Quest",
            f"Name: {info['name']}\nInstall dir: {info['installdir']}\n"
            f"Executable: {info['executable']}\n\nAppManifest: {acf_path}\n"
            f"Manifest mode: {manifest_mode}\n"
            f"Fake exe: {fake_exe_path}\n"
            f"Timer: {mins:g} minutes  ·  Auto-close: {'Yes' if auto_close else 'No'}{warn}{overwrite_note}\n\n"
            "Use at your own risk.\nCreate and launch?",
            parent=self.root,
        ):
            self.log("[!] Operation cancelled.", "warn")
            return
        faker = self.faker
        duration_s = max(1.0, float(mins) * 60.0)
        start_time = time.time()

        def work():
            acf = steam.generate_appmanifest(appid, info["name"], info["installdir"],
                                             steam_path, depot_id=info.get("depot_id"),
                                             manifest_mode=manifest_mode)
            if not acf:
                ui.print_color("[ERROR] Failed to create appmanifest. Aborting.", Colors.RED)
                return False
            if not steam.create_steam_fake_exe(faker, fake_exe_path, info["executable"]):
                acf.unlink(missing_ok=True)
                return False
            return faker.launch_executable(
                fake_exe_path,
                duration_s=duration_s,
                start_time=start_time,
                auto_close=auto_close,
            )

        def done(proc):
            if proc:
                self._track_quest(fake_exe_path, proc, duration_s=duration_s, auto_close=auto_close,
                                  cleanup_root=steam.steamapps_path(steam_path) / "common")
                self.log("[OK] Steam Quest setup complete!", "ok")
                self.log("[!] Discord MUST be running for detection to work.", "warn")
                self.log("[*] Keep the process running or in tray until the quest is done.", "info")

        self.run_task("Writing appmanifest + exe", work, done)

    def steam_delete(self):
        if self._guard_busy():
            return
        raw_path = self.steam_path.get().strip()
        sel = self.steam_list.curselection()
        if not raw_path:
            self.log("[!] No Steam path provided.", "err")
            return
        if not sel:
            self.log("[!] Search and select a game first", "warn")
            return
        steam_path = Path(raw_path)
        game = self.steam_results[sel[0]]
        appid = int(game["id"])
        override = self.steam_override.get().strip()
        install_override = self.steam_install.get().strip()

        name = game["name"]
        installdir = install_override or name
        executable = override or "Game.exe"
        if appid == 4080220:
            name = "EA SPORTS FC™ 27"
            if not install_override:
                installdir = "EA SPORTS FC 27"
            if not override:
                executable = "fc27.exe"

        installdir = steam.sanitize_installdir(installdir)
        try:
            fake_exe_path = steam.steam_fake_exe_path(steam_path, installdir, executable)
        except ValueError as e:
            self.log(str(e), "err")
            return
        acf_path = steam.steamapps_path(steam_path) / f"appmanifest_{appid}.acf"
        install_dir = steam.steamapps_path(steam_path) / "common" / installdir

        acf_exists = acf_path.exists()
        exe_exists = fake_exe_path.exists()
        folder_exists = install_dir.exists()

        if not (acf_exists or exe_exists or folder_exists):
            self.log(f"[!] No existing setup found for {name} (AppID: {appid}) to delete.", "warn")
            return

        msg = (
            f"Delete existing setup for {name} (AppID: {appid})?\n\n"
            f"Manifest: {acf_path} ({'found' if acf_exists else 'not found'})\n"
            f"Executable: {fake_exe_path} ({'found' if exe_exists else 'not found'})\n"
            f"Folder: {install_dir} ({'found' if folder_exists else 'not found'})\n\n"
            "This will delete the placeholder files and manifest.\n"
            "Proceed with delete?"
        )
        if not messagebox.askyesno("Orbifier - Delete Steam Quest Setup", msg, parent=self.root):
            self.log("[!] Delete cancelled.", "warn")
            return

        def work():
            # Stop any running quest for this exe first
            for q in list(self.quests.quests):
                if q.exe_path and Path(q.exe_path).resolve() == fake_exe_path.resolve():
                    self.quests.stop(q)
            return steam.delete_steam_game(steam_path, appid, installdir, executable)

        def done(res):
            deleted_any = False
            if res.get("manifest") and res["manifest"][1]:
                self.log(f"[OK] Deleted manifest: {res['manifest'][0].name}", "ok")
                deleted_any = True
            if res.get("executable") and res["executable"][1]:
                self.log(f"[OK] Deleted executable: {res['executable'][0].name}", "ok")
                deleted_any = True
            if res.get("folder") and res["folder"][1]:
                self.log(f"[OK] Cleaned up folder: {res['folder'][0].name}", "ok")
                deleted_any = True
            if deleted_any:
                self.log(f"[OK] Deletion complete for {name} (AppID: {appid}).", "ok")
            else:
                self.log(f"[*] No files were deleted.", "info")

        self.run_task(f"Deleting {name}", work, done)

    # ── Active quests ─────────────────────────────────────────────────────────
    def _build_active(self) -> tk.Frame:
        frame = self._screen("ACTIVE QUESTS", active_button=False)
        self.active_quests = QuestPanel(frame, self, max_rows=8)
        self.active_quests.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 8))
        self.quest_panels.append(self.active_quests)
        return frame

    def _track_quest(
        self,
        exe_path: Path,
        proc,
        duration_s: float | None = None,
        auto_close: bool = True,
        cleanup_root: Path | None = None,
    ) -> None:
        """Register a launched fake process in the ACTIVE QUESTS panels."""
        if not proc:
            return
        quest = self.quests.add(
            Path(exe_path).name,
            proc,
            Path(exe_path),
            duration_s=duration_s,
            auto_close=auto_close,
            cleanup_root=cleanup_root,
            cleanup_files=tuple(p for p in self.faker.created_helpers
                                if p.parent == Path(exe_path).resolve().parent),
        )
        self._refresh_quests()

    def _refresh_quests(self) -> None:
        for panel in self.quest_panels:
            panel.refresh()

    def _tick_quests(self):
        # Auto-stop and clean up completed quests if auto_close is enabled
        auto_done = [
            q for q in list(self.quests.quests)
            if getattr(q, "auto_close", True) and self.quests.status(q) == DONE
        ]
        if auto_done:
            self._stop_quests(auto_done)
            for q in auto_done:
                self.log(f"[OK] {q.name} quest complete! Auto-closed and cleaned up.", "ok")

        self._refresh_quests()
        self.root.after(1000, self._tick_quests)

    def stop_quest(self, qid: int) -> None:
        quest = self.quests.get(qid)
        if quest is not None:
            self._stop_quests([quest])

    def stop_all_quests(self) -> None:
        if not self.quests.quests:
            self.log("[!] No active quests to stop", "warn")
            return
        self._stop_quests(list(self.quests.quests))

    def _stop_quests(self, quests) -> None:
        """Drop the rows now; terminate the processes and delete the exes off-thread."""
        for quest in quests:
            self.quests.remove(quest)
        self._refresh_quests()
        tracker = self.quests

        def worker():
            for quest in quests:
                tracker.cleanup(quest)
                self.post(lambda n=quest.name: self.log(f"[OK] Stopped {n}", "ok"))

        threading.Thread(target=worker, daemon=True).start()

    # ── Credits ───────────────────────────────────────────────────────────────
    def _build_credits(self) -> tk.Frame:
        frame = self._screen("CREDITS")
        row = tk.Frame(frame, bg=BG)
        row.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
        PixelButton(row, "SUPPORT ON KO-FI", lambda: webbrowser.open(config.KOFI_URL),
                    width=300, height=40, color=MAGENTA, scale=2).pack(side="left")
        self._label(row, config.KOFI_URL).pack(side="left", padx=12)
        border = tk.Frame(frame, bg=BORDER, padx=PX, pady=PX)
        border.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 8))
        text = tk.Text(border, bg=PANEL_DARK, fg=TEXT, font=self.font_small,
                       relief="flat", bd=0, padx=8, pady=4, wrap="word",
                       highlightthickness=0, cursor="arrow")
        text.pack(fill="both", expand=True)
        text.insert("1.0", ui.credits_text(ui._NoColors, enter_prompt=False).strip("\n"))
        text.configure(state="disabled")
        return frame

    # ── Updater ───────────────────────────────────────────────────────────────
    def _start_update_check(self):
        if not getattr(sys, "frozen", False):
            self.log("[*] Running from source - auto-update skipped", "muted")
            return
        self.log("[*] Checking for updates...", "muted")
        self.run_task("Checking for updates", auto_update,
                      lambda _r: self.log("[UPDATE] Update check finished", "muted"))


def run_gui() -> None:
    """Create the Orbifier window and run the Tk main loop."""
    root = tk.Tk()
    OrbifierApp(root)
    root.mainloop()

"""
quests.py – Pure bookkeeping for fake game processes launched by the GUI.

No tkinter here: the GUI renders whatever QuestTracker reports, and the
tests drive it with a fake clock and fake process objects.
"""

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUNNING = "RUNNING"   # process alive, quest timer still counting down
DONE    = "DONE"      # timer elapsed, process still alive
STOPPED = "STOPPED"   # process exited (stopped by us or externally)

KILL_AFTER = 2.0      # seconds to wait after terminate() before kill()


def format_mmss(seconds: float) -> str:
    """Format a remaining-seconds value as MM:SS (rounded up, never negative)."""
    total = max(0, int(seconds + 0.999))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


@dataclass
class Quest:
    qid: int
    name: str
    proc: Any                # anything with poll() / terminate() / kill() / wait()
    exe_path: Path | None
    started: float
    duration: float = 1200.0  # duration in seconds
    auto_close: bool = True
    cleanup_root: Path | None = None
    cleanup_files: tuple[Path, ...] = ()


def _tree_kill(proc) -> None:
    """Windows: kill the process tree (a frozen onefile exe has a child process)."""
    pid = getattr(proc, "pid", None)
    if sys.platform != "win32" or not isinstance(pid, int):
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            timeout=5,
        )
    except Exception:
        pass


def stop_process(proc, kill_after: float = KILL_AFTER) -> None:
    """Terminate *proc*; kill it if it is still alive after *kill_after* seconds."""
    if proc.poll() is not None:
        return
    _tree_kill(proc)
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=kill_after)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=kill_after)
        except Exception:
            pass


class QuestTracker:
    """Keeps the list of launched fake processes and derives their status."""

    def __init__(self, duration_s: float, clock=time.monotonic, stopper=stop_process):
        self.duration = float(duration_s)
        self._clock = clock
        self._stopper = stopper
        self._next_id = 1
        self.quests: list[Quest] = []

    def add(
        self,
        name: str,
        proc,
        exe_path: Path | None = None,
        duration_s: float | None = None,
        auto_close: bool = True,
        cleanup_root: Path | None = None,
        cleanup_files: tuple[Path, ...] = (),
    ) -> Quest:
        dur = float(duration_s) if duration_s is not None else self.duration
        quest = Quest(self._next_id, name, proc, exe_path, self._clock(), dur, auto_close,
                      Path(cleanup_root).expanduser().resolve() if cleanup_root else None,
                      cleanup_files)
        self._next_id += 1
        self.quests.append(quest)
        return quest

    def get(self, qid: int) -> Quest | None:
        return next((q for q in self.quests if q.qid == qid), None)

    def remaining(self, quest: Quest) -> float:
        return max(0.0, quest.duration - (self._clock() - quest.started))

    def fraction_left(self, quest: Quest) -> float:
        """1.0 at launch, 0.0 when the quest timer has elapsed."""
        if quest.duration <= 0:
            return 0.0
        return self.remaining(quest) / quest.duration

    def status(self, quest: Quest) -> str:
        if quest.proc.poll() is not None:
            return STOPPED
        if self.remaining(quest) <= 0:
            return DONE
        return RUNNING

    def stop(self, quest: Quest) -> None:
        """Drop the quest, stop its process and delete its copied exe."""
        self.remove(quest)
        self.cleanup(quest)

    def cleanup(self, quest: Quest) -> None:
        """Stop the process, delete its copied exe, and clean up empty directories."""
        self._stopper(quest.proc)
        path = quest.exe_path
        if path is None:
            return
        # another live quest may share the same exe file
        if any(q.exe_path == path and q.proc.poll() is None for q in list(self.quests)):
            return
        try:
            p = Path(path).resolve()
            if p.exists():
                p.unlink()

            parent = p.parent
            # Only remove files this session created, once this folder is unused.
            if not any(q.proc.poll() is None and q.exe_path
                       and Path(q.exe_path).resolve().parent == parent
                       for q in list(self.quests)):
                for helper in quest.cleanup_files:
                    try:
                        helper_path = Path(helper)
                        # Only direct children of this quest's folder are owned
                        # helpers: the shared runtime directory, the timer
                        # script, and the venv config. A nested quest keeps its
                        # own helpers.
                        if helper_path.parent != parent:
                            continue
                        if helper_path.is_dir():
                            shutil.rmtree(helper_path, ignore_errors=True)
                        else:
                            helper_path.unlink(missing_ok=True)
                    except Exception:
                        pass

            # Remove empty descendants, preserving the selected cleanup boundary.
            desktop = quest.cleanup_root or Path.home() / "Desktop"
            curr = parent
            while (curr != desktop and curr.parent != curr
                   and (quest.cleanup_root is None or curr.is_relative_to(desktop))):
                try:
                    if not any(curr.iterdir()):
                        curr.rmdir()
                        curr = curr.parent
                    else:
                        break
                except Exception:
                    break
        except Exception:
            pass

    def stop_all(self) -> None:
        for quest in list(self.quests):
            self.stop(quest)

    def remove(self, quest: Quest) -> None:
        if quest in self.quests:
            self.quests.remove(quest)

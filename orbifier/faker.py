"""
faker.py – GameFaker class, manual_mode, and executable launching.

In frozen (.exe) mode:   copies orbifier.exe itself → GameName.exe (--timer-mode)
In source mode:           copies pythonw.exe → GameName.exe + _orbifier_timer.pyw
"""

import sys
import shutil
import subprocess
import time
from pathlib import Path

from . import config
from .ui import (
    Colors, print_color, print_boxed_title,
    loading_animation, ask_confirm,
)

# Timer code embedded for source mode – written as a standalone .pyw file
# so that the renamed pythonw.exe can run it without any package dependency.
_TIMER_PYW_CODE = '''# Orbifier fake game process: countdown timer window for Discord detection.
import os
import sys
import time
import tkinter as tk
from pathlib import Path

BG_COLOR      = "#0f101a"
PANEL_COLOR   = "#161826"
TEXT_COLOR    = "#f0f2f5"
ACCENT_COLOR  = "#00e5ff"
GREEN_COLOR   = "#4ade80"
MUTED_COLOR   = "#8b90a0"
DONE_COLOR    = "#ff6b8b"
DEFAULT_MINS  = 15

class TimerApp:
    def __init__(self, root, name="", duration_s=DEFAULT_MINS * 60, started=None, auto_close=True):
        self.root = root
        self.name = name or self._detect_name()
        self.duration_s = float(duration_s)
        self.started = float(started) if started is not None else time.time()
        self.auto_close = auto_close
        self.tray = None
        self._saved_geometry = None

        self.root.title(f"Orbifier – {self.name}")
        self.root.geometry("380x230")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_COLOR)

        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"+{x}+{y}")

        self.name_label = tk.Label(
            root, text=self.name,
            font=("Segoe UI", 12, "bold"), fg=ACCENT_COLOR, bg=BG_COLOR,
            wraplength=350,
        )
        self.name_label.pack(pady=(14, 2))

        initial_rem = max(0, int(self.duration_s - (time.time() - self.started)))
        m, s = divmod(initial_rem, 60)
        self.timer_label = tk.Label(
            root, text=f"{m:02d}:{s:02d}",
            font=("Consolas", 38, "bold"), fg=TEXT_COLOR, bg=BG_COLOR,
        )
        self.timer_label.pack(pady=2)

        self.status_label = tk.Label(
            root, text="● Spoofing active (Discord detecting game)",
            font=("Segoe UI", 9, "bold"), fg=GREEN_COLOR, bg=BG_COLOR,
        )
        self.status_label.pack(pady=(2, 6))

        btn_row = tk.Frame(root, bg=BG_COLOR)
        btn_row.pack(side="top", pady=(0, 4))

        self.tray_btn = tk.Button(
            btn_row,
            text="🗕 HIDE TO TRAY",
            command=self.hide_to_tray,
            bg=PANEL_COLOR,
            fg=ACCENT_COLOR,
            activebackground=BG_COLOR,
            activeforeground=TEXT_COLOR,
            font=("Segoe UI", 8, "bold"),
            relief="groove",
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
        )
        self.tray_btn.pack(side="left", padx=4)

        self.tip_label = tk.Label(
            root, text="Keep open or in tray. Close window to stop quest.",
            font=("Segoe UI", 8), fg=MUTED_COLOR, bg=BG_COLOR,
        )
        self.tip_label.pack(side="bottom", pady=(0, 8))

        self.root.protocol("WM_DELETE_WINDOW", self.stop_and_exit)
        self._tick()

    def _detect_name(self):
        for i, arg in enumerate(sys.argv):
            if arg == "--name" and i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        stem = Path(sys.argv[0]).stem
        if stem and stem.lower() not in ("orbifier", "python", "pythonw", "_orbifier_timer"):
            return stem
        return "Game"

    def _tick(self):
        elapsed = time.time() - self.started
        remaining = max(0, int(self.duration_s - elapsed))
        self.remaining = remaining
        m, s = divmod(remaining, 60)
        time_str = f"{m:02d}:{s:02d}"
        self.timer_label.config(text=time_str)

        if self.tray and getattr(self.tray, "_running", False):
            self.tray.update_tooltip(f"Orbifier – {self.name} ({time_str})")

        if remaining > 0:
            self.root.after(1000, self._tick)
        else:
            self.timer_label.config(fg=DONE_COLOR)
            if self.auto_close:
                self.status_label.config(text="✓ Quest complete! Auto-closing in 2s...", fg=ACCENT_COLOR)
                self.root.after(2000, self.stop_and_exit)
            else:
                self.status_label.config(text="✓ Quest time complete (keep open if needed)", fg=ACCENT_COLOR)

    def hide_to_tray(self):
        if sys.platform != "win32":
            self.root.iconify()
            return
        self._saved_geometry = self.root.geometry()
        self.root.attributes("-toolwindow", True)
        self.root.geometry("+50000+50000")

        rem = max(0, int(self.duration_s - (time.time() - self.started)))
        m, s = divmod(rem, 60)
        try:
            from orbifier.tray import TrayIcon
            def _open():
                self.root.after(0, self.restore_from_tray)
            def _exit():
                self.root.after(0, self.stop_and_exit)
            self.tray = TrayIcon(
                tooltip=f"Orbifier – {self.name} ({m:02d}:{s:02d})",
                on_open=_open,
                on_exit=_exit,
            )
            self.tray.start()
        except Exception:
            pass

    def restore_from_tray(self):
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.root.attributes("-toolwindow", False)
        self.root.geometry(self._saved_geometry or "380x230")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def stop_and_exit(self):
        if self.tray:
            self.tray.stop()
            self.tray = None
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

name = ""
duration_s = float(DEFAULT_MINS * 60)
started = None
auto_close = True

for i, arg in enumerate(sys.argv):
    if arg == "--name" and i + 1 < len(sys.argv):
        name = sys.argv[i + 1]
    elif arg == "--duration" and i + 1 < len(sys.argv):
        try:
            duration_s = float(sys.argv[i + 1])
        except ValueError:
            pass
    elif arg == "--started" and i + 1 < len(sys.argv):
        try:
            started = float(sys.argv[i + 1])
        except ValueError:
            pass
    elif arg == "--auto-close" and i + 1 < len(sys.argv):
        auto_close = sys.argv[i + 1] in ("1", "true", "True")

root = tk.Tk()
TimerApp(root, name=name, duration_s=duration_s, started=started, auto_close=auto_close)
root.mainloop()
'''


def _is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


ELEVATED_WARNING = (
    "Orbifier is running as administrator. Discord cannot see elevated processes "
    "unless it also runs as administrator. Run Orbifier normally."
)


def is_process_elevated() -> bool:
    """True if this process runs with administrator rights (Windows only)."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _find_source_exe() -> Path:
    """Find the executable to copy for fake game processes."""
    if _is_frozen():
        return Path(sys.executable)  # copy ourselves

    # Source mode: prefer pythonw.exe (no console window)
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        return pythonw
    return Path(sys.executable)  # fallback to python.exe


class GameFaker:
    def __init__(self):
        self._frozen = _is_frozen()
        self._source_exe = _find_source_exe()
        self.desktop_path = Path.home() / "Desktop"
        self.created_helpers: set[Path] = set()

    def copy_exe_to(self, target_path: Path) -> None:
        """Copy the faker executable to *target_path*.

        If the executable, timer script, or destination folder already exists,
        it is overwritten cleanly instead of raising an error.
        """
        if target_path.exists():
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                try:
                    target_path.unlink()
                except Exception:
                    pass

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._source_exe, target_path)

        if not self._frozen:
            # If running inside a venv, copy pyvenv.cfg so pythonw.exe can locate the Python runtime
            venv_candidates = [
                Path(sys.executable).parent.parent / "pyvenv.cfg",
                Path(sys.executable).parent / "pyvenv.cfg",
            ]
            for venv_cfg in venv_candidates:
                if venv_cfg.exists():
                    try:
                        destination = target_path.parent / "pyvenv.cfg"
                        if not destination.exists():
                            shutil.copy2(venv_cfg, destination)
                            self.created_helpers.add(destination.resolve())
                    except Exception:
                        pass
                    break

            timer_script = target_path.parent / "_orbifier_timer.pyw"
            timer_script.write_text(_TIMER_PYW_CODE, encoding="utf-8")
            self.created_helpers.add(timer_script.resolve())

    def game_path(self, exe_name: str, output_dir: Path | None = None) -> Path:
        """Resolve the same validated destination used by previews and creation."""
        from .steam import executable_path
        return executable_path(output_dir or self.desktop_path / config.FAKE_EXE_DIR, exe_name)

    def delete_fake_game(self, exe_name: str, output_dir: Path | None = None) -> dict:
        """Delete fake game executable, helper files, and clean up empty parent folders."""
        results = {
            "executable": (None, False),
            "helpers": [],
            "folder": (None, False),
        }
        try:
            target = self.game_path(exe_name, output_dir)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                results["executable"] = (target, True)
            else:
                results["executable"] = (target, False)

            parent = target.parent
            for helper_name in ("_orbifier_timer.pyw", "pyvenv.cfg"):
                h = parent / helper_name
                if h.exists() and h.is_file():
                    try:
                        h.unlink()
                        results["helpers"].append(h)
                    except Exception:
                        pass

            desktop = Path(output_dir).expanduser().resolve() if output_dir else (self.desktop_path / config.FAKE_EXE_DIR).resolve()
            folder_deleted = False
            curr = parent
            while curr != desktop and curr.parent != curr and (output_dir is not None or curr.is_relative_to(desktop)):
                try:
                    if not any(curr.iterdir()):
                        curr.rmdir()
                        folder_deleted = True
                        curr = curr.parent
                    else:
                        break
                except Exception:
                    break
            results["folder"] = (parent, folder_deleted)
        except Exception:
            pass
        return results

    def create_fake_game(self, exe_name: str, output_dir: Path | None = None) -> Path | None:
        """Create a placeholder in the selected output directory."""
        try:
            target_path = self.game_path(exe_name, output_dir)
            loading_animation(f"Creating {exe_name.split('/')[-1]}", 0.8)
            self.copy_exe_to(target_path)
            print_color(f"[OK] Created: {target_path}", Colors.GREEN, bold=True)
            return target_path
        except Exception as e:
            print_color(f"[ERROR] Failed to create executable: {e}", Colors.RED, bold=True)
            print_color("[!] Check file permissions or disk space", Colors.YELLOW)
            return None

    def launch_executable(
        self,
        exe_path: Path,
        duration_s: float = 900.0,
        start_time: float | None = None,
        auto_close: bool = True,
    ) -> "subprocess.Popen | None":
        """Launch the fake game process in background.

        Returns the Popen object (truthy) on success, or None on failure.
        """
        try:
            loading_animation("Launching process", 0.8)

            game_name = exe_path.stem
            start_time = start_time if start_time is not None else time.time()
            close_flag = "1" if auto_close else "0"
            dur_str = str(int(duration_s))
            start_str = str(start_time)

            if self._frozen:
                args = [
                    str(exe_path),
                    "--timer-mode",
                    "--name", game_name,
                    "--duration", dur_str,
                    "--started", start_str,
                    "--auto-close", close_flag,
                ]
            else:
                timer_script = exe_path.parent / "_orbifier_timer.pyw"
                args = [
                    str(exe_path),
                    str(timer_script),
                    "--name", game_name,
                    "--duration", dur_str,
                    "--started", start_str,
                    "--auto-close", close_flag,
                ]

            if sys.platform == 'win32':
                DETACHED_PROCESS = 0x00000008
                proc = subprocess.Popen(
                    args,
                    creationflags=DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            else:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )

            print_color("[OK] Process launched successfully", Colors.GREEN, bold=True)
            print_color("[*] Keep the timer window open or in tray while the quest runs.", Colors.CYAN)
            print_color("[*] Discord should now detect the game (if Discord is running)", Colors.CYAN)
            print_color("[!] IMPORTANT: Discord MUST be running for the spoofing to work", Colors.YELLOW)
            print_color("[*] Wait a few seconds for Discord to scan processes", Colors.GRAY)
            print_color("[*] TIP: You can run this tool multiple times to emulate multiple games!", Colors.MAGENTA)
            return proc
        except Exception as e:
            print_color(f"[!] Failed to auto-launch: {e}", Colors.YELLOW)
            print_color(f"[*] You can manually run: {exe_path}", Colors.CYAN)
            return None


def manual_mode(faker: GameFaker) -> None:
    """Manual mode – user types an exact process name to fake."""
    print_boxed_title("MANUAL MODE", width=50, color=Colors.CYAN)
    print_color("[*] Enter the exact process name Discord expects", Colors.CYAN)
    print_color("[*] Examples:", Colors.GRAY)
    print_color("    • TslGame.exe (PUBG)", Colors.GRAY)
    print_color("    • League of Legends.exe (LoL)", Colors.GRAY)
    print_color("    • Overwatch.exe", Colors.GRAY)
    print_color("[*] Make sure the name matches exactly (case-sensitive on some systems)", Colors.GRAY)
    print()

    exe_name = input(f"{Colors.BOLD}Executable name{Colors.RESET} (or 'back'): ").strip()
    if not exe_name or exe_name.lower() in ('back', 'b'):
        return

    raw_dir = input("Output folder (blank for Desktop default): ").strip().strip('"')
    output_dir = Path(raw_dir).expanduser() if raw_dir else None
    try:
        target = faker.game_path(exe_name, output_dir)
    except ValueError as e:
        print_color(f"[ERROR] {e}", Colors.RED)
        return
    print(f"\n{Colors.BOLD}Summary:{Colors.RESET}")
    print(f"  Executable: {Colors.CYAN}{exe_name}{Colors.RESET}")
    print(f"  Path: {Colors.GRAY}{target}{Colors.RESET}")
    if target.exists():
        print_color("  [*] Existing executable found (will be overwritten if launched).", Colors.YELLOW)

    choice = ask_confirm()
    if choice == 'delete':
        res = faker.delete_fake_game(exe_name, output_dir=output_dir)
        if res.get("executable") and res["executable"][1]:
            print_color(f"[OK] Deleted executable: {res['executable'][0]}", Colors.GREEN)
        else:
            print_color("[*] No existing executable found to delete.", Colors.YELLOW)
        time.sleep(config.SLEEP_SHORT)
        return
    elif not choice:
        print_color("\n[!] Operation cancelled", Colors.YELLOW)
        time.sleep(config.SLEEP_SHORT)
        return

    result = faker.create_fake_game(exe_name, output_dir=output_dir)
    if result:
        print()
        faker.launch_executable(result)
        print_color("\n[OK] Setup complete!", Colors.GREEN, bold=True)
        print_color("[!] IMPORTANT: Discord MUST be running for the spoofing to work", Colors.YELLOW)

    input(f"\n{Colors.GRAY}Press Enter to continue...{Colors.RESET}")

"""
steam.py – Steam quest helpers: registry, API, appmanifest, and quest mode UI.
"""

import re
import shutil
import sys
import time
from pathlib import Path, PureWindowsPath

from . import config, textmatch
from .ui import (
    Colors, print_color, print_boxed_title,
    loading_animation, ask_confirm,
)
from .net import fetch_json
from .errors import NetworkError, SteamNotFoundError

# Windows registry – optional
try:
    import winreg as _winreg
except ImportError:
    _winreg = None


# ── Registry helpers ──────────────────────────────────────────────────────────

def get_steam_path() -> Path | None:
    """Read Steam installation path from Windows registry."""
    if sys.platform != 'win32' or _winreg is None:
        return None
    try:
        key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        value, _ = _winreg.QueryValueEx(key, "SteamPath")
        _winreg.CloseKey(key)
        return Path(value)
    except Exception:
        fallback = Path("C:/Program Files (x86)/Steam")
        return fallback if fallback.exists() else None


def get_steam_user_id() -> str:
    """Read the currently logged-in Steam user ID from registry."""
    if sys.platform != 'win32' or _winreg is None:
        return "0"
    try:
        key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess")
        value, _ = _winreg.QueryValueEx(key, "ActiveUser")
        _winreg.CloseKey(key)
        steam_id_64 = int(value) + 76561197960265728
        return str(steam_id_64)
    except Exception:
        return "0"


# ── API helpers ───────────────────────────────────────────────────────────────

def _pick_windows_exe(launch: dict) -> str | None:
    """Return the first Windows .exe found in a SteamCMD launch dict."""
    for key in sorted(launch.keys()):
        entry = launch[key]
        oslist = entry.get("config", {}).get("oslist", "windows")
        if "windows" in oslist or oslist == "":
            exe = entry.get("executable", "")
            if exe.endswith(".exe"):
                return exe.replace("\\", "/")
    return None


def fetch_steam_app_info(appid: int) -> dict | None:
    """Fetch app info from SteamCMD API. Returns dict or None on failure."""
    url = f"{config.STEAMCMD_API_URL}/{appid}"
    try:
        loading_animation(f"Fetching Steam app info for {appid}", 1.2)
        data = fetch_json(url)

        app_data   = data.get("data", {}).get(str(appid), {})
        common_cfg = app_data.get("common", {})
        app_cfg    = app_data.get("config", {})

        name       = common_cfg.get("name", f"App {appid}")
        installdir = app_cfg.get("installdir", name)
        executable = ("fc27.exe" if appid == 4080220
                      else _pick_windows_exe(app_cfg.get("launch", {})))

        if not executable:
            executable = installdir.split("/")[-1] + ".exe"

        depot_id = next(
            (k for k, v in app_data.get("depots", {}).items()
             if k.isdigit() and isinstance(v, dict)),
            None,
        )
        return {"name": name, "installdir": installdir, "executable": executable, "depot_id": depot_id}

    except NetworkError as e:
        print_color(f"[!] SteamCMD API error: {e}", Colors.YELLOW)
        return None


def _store_search(term: str) -> list:
    data = fetch_json(
        config.STEAM_STORE_SEARCH_URL,
        params={"term": term, "l": "english", "cc": "US"},
    )
    return data.get("items", []) or []


def search_steam_games(query: str) -> list:
    """Search Steam store. Returns list of {id, name} dicts.

    Punctuation, symbols (®, ™, :, -, ...) and case are ignored; results are
    re-ranked locally so the closest name match comes first.
    """
    try:
        loading_animation(f"Searching Steam for '{query}'", 1.0)
        cleaned = textmatch.normalize(query)
        results = _store_search(cleaned) if cleaned else []
        if not results and query.strip() and query.strip().lower() != cleaned:
            results = _store_search(query.strip())
        # stable sort: keeps Steam's order among equally good matches
        return sorted(results, key=lambda g: textmatch.match_score(query, g.get("name", "")))
    except NetworkError as e:
        print_color(f"[!] Steam search error: {e}", Colors.YELLOW)
        return []


# ── Appmanifest generation ────────────────────────────────────────────────────

_ACF_TEMPLATE = '''"AppState"
{{
\t"appid"\t\t"{appid}"
\t"universe"\t\t"1"
\t"LauncherPath"\t\t"{launcher}"
\t"name"\t\t"{name}"
\t"StateFlags"\t\t"1026"
\t"installdir"\t\t"{installdir}"
\t"LastUpdated"\t\t"0"
\t"LastPlayed"\t\t"0"
\t"SizeOnDisk"\t\t"0"
\t"StagingSize"\t\t"1073741824"
\t"buildid"\t\t"0"
\t"LastOwner"\t\t"{owner}"
\t"DownloadType"\t\t"1"
\t"UpdateResult"\t\t"4"
\t"BytesToDownload"\t\t"1073741824"
\t"BytesDownloaded"\t\t"27262976"
\t"BytesToStage"\t\t"1073741824"
\t"BytesStaged"\t\t"27262976"
\t"TargetBuildID"\t\t"0"
\t"AutoUpdateBehavior"\t\t"0"
\t"AllowOtherDownloadsWhileRunning"\t\t"0"
\t"ScheduledAutoUpdate"\t\t"0"
\t"InstalledDepots"
\t{{
\t}}
\t"StagedDepots"
\t{{{staged}
\t}}
\t"UserConfig"
\t{{
\t}}
\t"MountedConfig"
\t{{
\t}}
}}
'''

_STAGED_DEPOT_TEMPLATE = '''
\t\t"{depot_id}"
\t\t{{
\t\t\t"manifest"\t\t"0"
\t\t\t"size"\t\t"1073741824"
\t\t\t"dlcappid"\t\t"0"
\t\t}}'''


_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize_path_component(part: str, fallback: str = "Game") -> str:
    """Make *part* a valid Windows file/folder name.

    Drops trademark symbols and characters Windows rejects (``: ? * " < > |``),
    collapses whitespace and strips trailing dots/spaces.
    """
    part = part.translate(str.maketrans("", "", "®™©℠"))
    part = _INVALID_PATH_CHARS.sub(" ", part)
    part = " ".join(part.split()).rstrip(". ")
    if not part:
        return fallback
    if part.split(".")[0].upper() in _RESERVED_NAMES:
        part = f"_{part}"
    return part


def sanitize_installdir(installdir: str, fallback: str = "Game") -> str:
    """Single valid folder name for steamapps/common/<installdir>."""
    return sanitize_path_component(installdir.replace("/", " ").replace("\\", " "), fallback)


def sanitize_executable(executable: str) -> str:
    """Sanitize each segment of a relative exe path (keeps '/' separators)."""
    parts = [p for p in executable.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    parts = [sanitize_path_component(p) for p in parts] or ["Game.exe"]
    if not parts[-1].lower().endswith(".exe"):
        parts[-1] += ".exe"
    return "/".join(parts)


def steamapps_path(steam_path: Path) -> Path:
    """Accept either a Steam/library root or its steamapps directory."""
    path = Path(steam_path).expanduser()
    return path if path.name.lower() == "steamapps" else path / "steamapps"


def generate_appmanifest(appid, name, installdir, steam_path, depot_id=None,
                         manifest_mode="legacy"):
    """Write an appmanifest; overwrites any existing manifest for this app ID."""
    if not str(appid).isascii() or not str(appid).isdigit() or int(appid) <= 0:
        raise ValueError("Steam App ID must be a positive integer.")
    if manifest_mode not in ("legacy", "installed"):
        raise ValueError("Choose installed or legacy manifest mode.")
    name = name.replace('"', "'").replace("\\", "/").replace("\n", " ").replace("\r", " ")
    acf_content = _ACF_TEMPLATE.format(
        appid=appid,
        launcher=str((get_steam_path() or steamapps_path(steam_path).parent) / "steam.exe").replace("/", "\\\\"),
        name=name.replace('"', "'"),
        installdir=sanitize_installdir(installdir),  # must match steam_fake_exe_path
        owner=get_steam_user_id(),
        staged=_STAGED_DEPOT_TEMPLATE.format(depot_id=depot_id) if depot_id else "",
    )
    if manifest_mode == "installed":
        acf_content = ('"AppState"\n{\n'
                       f'\t"appid"\t\t"{int(appid)}"\n'
                       f'\t"name"\t\t"{name}"\n'
                       '\t"StateFlags"\t\t"4"\n'
                       f'\t"installdir"\t\t"{sanitize_installdir(installdir)}"\n'
                       '}\n')
    acf_path = steamapps_path(steam_path) / f"appmanifest_{int(appid)}.acf"
    try:
        acf_path.parent.mkdir(parents=True, exist_ok=True)
        if acf_path.is_dir():
            shutil.rmtree(acf_path)
        with open(acf_path, "w", encoding="utf-8") as f:
            f.write(acf_content)
        print_color(f"[OK] Created appmanifest: {acf_path}", Colors.GREEN, bold=True)
        return acf_path
    except Exception as e:
        print_color(f"[ERROR] Failed to write appmanifest: {e}", Colors.RED, bold=True)
        return None


# ── Fake exe placement (shared by CLI and GUI) ───────────────────────────────

def steam_fake_exe_path(steam_path: Path, installdir: str, executable: str) -> Path:
    """Return steamapps/common/<installdir>/<executable> under *steam_path*.

    Both parts are sanitized so names like "Call of Duty®: Modern Warfare®"
    become valid Windows paths.
    """
    install = steamapps_path(steam_path) / "common" / sanitize_installdir(installdir)
    return executable_path(install, executable)


def executable_path(directory: Path, executable: str) -> Path:
    """Resolve a relative EXE path without silently discarding parent segments.

    Parent segments may return to the selected directory, as in
    ../EA SPORTS FC 27/fc27.exe, but the final path must stay inside it.
    """
    raw = executable.strip().replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    if windows_path.drive or windows_path.root:
        raise ValueError("Enter an executable path relative to the selected folder.")
    parts = [p if p in (".", "..") else sanitize_path_component(p)
             for p in raw.split("/") if p]
    if not parts or parts[-1] in (".", ".."):
        raise ValueError("Enter an executable filename, for example fc27.exe.")
    if not parts[-1].lower().endswith(".exe"):
        parts[-1] += ".exe"
    base = Path(directory).expanduser().resolve()
    target = base.joinpath(*parts).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Executable path must stay inside the selected install/output folder.")
    return target


def create_steam_fake_exe(faker, fake_exe_path: Path, executable: str) -> bool:
    """Copy the faker exe to *fake_exe_path*. Returns True on success."""
    try:
        loading_animation(f"Creating {executable.split('/')[-1]}", 0.8)
        faker.copy_exe_to(fake_exe_path)
        print_color(f"[OK] Created: {fake_exe_path}", Colors.GREEN, bold=True)
        return True
    except Exception as e:
        print_color(f"[ERROR] Failed to copy exe: {e}", Colors.RED, bold=True)
        return False


def delete_steam_game(steam_path: Path, appid: int, installdir: str, executable: str) -> dict:
    """Delete fake executable, helper files, manifest, and empty install folder.

    Returns a dict with paths and boolean statuses:
    {
        "manifest": (Path, bool),
        "executable": (Path, bool),
        "helpers": list[Path],
        "folder": (Path, bool),
    }
    """
    results = {
        "manifest": (None, False),
        "executable": (None, False),
        "helpers": [],
        "folder": (None, False),
    }

    # 1. Manifest
    try:
        acf_path = steamapps_path(steam_path) / f"appmanifest_{int(appid)}.acf"
        if acf_path.exists():
            if acf_path.is_dir():
                shutil.rmtree(acf_path)
            else:
                acf_path.unlink()
            results["manifest"] = (acf_path, True)
        else:
            results["manifest"] = (acf_path, False)
    except Exception:
        results["manifest"] = (None, False)

    # 2. Executable & helper files
    try:
        fake_exe = steam_fake_exe_path(steam_path, installdir, executable)
        if fake_exe.exists():
            if fake_exe.is_dir():
                shutil.rmtree(fake_exe)
            else:
                fake_exe.unlink()
            results["executable"] = (fake_exe, True)
        else:
            results["executable"] = (fake_exe, False)

        parent = fake_exe.parent
        for helper_name in ("_orbifier_timer.pyw", "pyvenv.cfg"):
            h = parent / helper_name
            if h.exists() and h.is_file():
                try:
                    h.unlink()
                    results["helpers"].append(h)
                except Exception:
                    pass

        # 3. Clean up empty install dir and parent dirs up to steamapps/common
        common_dir = steamapps_path(steam_path) / "common"
        install_dir = common_dir / sanitize_installdir(installdir)
        folder_deleted = False
        curr = parent
        while curr != common_dir and curr.parent != curr and curr.is_relative_to(common_dir):
            try:
                if not any(curr.iterdir()):
                    curr.rmdir()
                    if curr == install_dir:
                        folder_deleted = True
                    curr = curr.parent
                else:
                    break
            except Exception:
                break
        results["folder"] = (install_dir, folder_deleted)
    except Exception:
        pass

    return results


# ── Interactive UI for Steam Quest Mode ───────────────────────────────────────

def _resolve_steam_path() -> Path | None:
    """Auto-detect or prompt for Steam path."""
    steam_path = get_steam_path()
    if steam_path and steam_path.exists():
        print_color(f"[*] Detected Steam: {steam_path}", Colors.CYAN)
    else:
        steam_path = None
        print_color("[!] Could not locate Steam automatically.", Colors.YELLOW)
    manual = input(
        f"{Colors.BOLD}Steam/library root or steamapps folder{Colors.RESET}"
        " (blank to use detected location): "
    ).strip().strip('"')
    if not manual:
        if steam_path:
            return steam_path
        print_color("[!] No Steam path provided. Aborting.", Colors.RED)
        return None
    return Path(manual).expanduser()


def _pick_steam_game(query: str) -> dict | None:
    """Search Steam and let the user choose a game."""
    if query.isascii() and query.isdigit() and int(query) > 0:
        return {"id": int(query), "name": f"App {int(query)}"}
    results = search_steam_games(query)
    if not results:
        print_color(f"\n[ERROR] No results found for '{query}'", Colors.RED)
        print_color("[!] Try a different search term", Colors.YELLOW)
        time.sleep(config.SLEEP_LONG)
        return None

    print(f"\n{Colors.BOLD}{Colors.GREEN}Found {len(results)} result(s):{Colors.RESET}\n")
    print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
    for idx, game in enumerate(results, 1):
        print(f"  {Colors.BOLD}{Colors.CYAN}{idx:2d}.{Colors.RESET} {Colors.WHITE}{game['name']}{Colors.RESET}  {Colors.GRAY}(AppID: {game['id']}){Colors.RESET}")
        if idx < len(results):
            print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
    print()

    raw = input(f"{Colors.BOLD}Select [1-{len(results)}]{Colors.RESET} (or 'back'): ").strip()
    if raw.lower() in ('back', 'b', ''):
        return None
    try:
        idx = int(raw)
        if not 1 <= idx <= len(results):
            raise ValueError
    except ValueError:
        print_color("[ERROR] Invalid selection.", Colors.RED)
        time.sleep(config.SLEEP_SHORT)
        return None
    return results[idx - 1]


def _prompt_app_info_manually(appid: int) -> dict:
    """Fallback: ask user to type Steam app info."""
    print_color("[!] Could not fetch app info automatically.", Colors.YELLOW)
    print_color("[*] Enter details manually:", Colors.CYAN)
    return {
        "name":       input(f"  {Colors.BOLD}Game name{Colors.RESET}: ").strip() or f"App {appid}",
        "installdir": input(f"  {Colors.BOLD}Install dir{Colors.RESET} (folder in steamapps/common): ").strip() or f"App{appid}",
        "executable": input(f"  {Colors.BOLD}Executable{Colors.RESET} (e.g. Bin/Game.exe): ").strip() or "Game.exe",
        "depot_id":   None,
    }


def steam_quest_mode(faker) -> None:
    """Steam Quest Mode – generates appmanifest + fake exe for any Steam appid."""
    print_boxed_title("STEAM QUEST MODE", width=55, color=Colors.CYAN)
    print_color("[*] This mode generates a fake Steam appmanifest + exe", Colors.CYAN)
    print_color("[*] Required for games that verify Steam ownership (Marathon, Toxic Commando…)", Colors.GRAY)
    print_color("[*] Search by name — demos and DLCs are separate, pick the right one!", Colors.YELLOW)
    print()

    steam_path = _resolve_steam_path()
    if not steam_path:
        return
    print_color(f"[OK] Steam found at: {steam_path}", Colors.GREEN)

    query = input(f"\n{Colors.BOLD}Game name or Steam App ID{Colors.RESET} (or 'back'): ").strip()
    if query.lower() in ('back', 'b', ''):
        return

    game = _pick_steam_game(query)
    if not game:
        return

    appid = int(game['id'])
    print_color(f"\n[OK] Selected: {game['name']} (AppID: {appid})", Colors.GREEN, bold=True)
    info = fetch_steam_app_info(appid) or _prompt_app_info_manually(appid)

    print(f"\n{Colors.BOLD}Detected info:{Colors.RESET}")
    print(f"  Name:        {Colors.CYAN}{info['name']}{Colors.RESET}")
    print(f"  Install dir: {Colors.CYAN}{info['installdir']}{Colors.RESET}")
    print(f"  Executable:  {Colors.CYAN}{info['executable']}{Colors.RESET}")

    install_override = input("Install folder override (under steamapps/common; blank to keep): ").strip()
    if install_override:
        info['installdir'] = install_override
    info['installdir'] = sanitize_installdir(info['installdir'])
    override = input(f"\n{Colors.BOLD}Override executable path?{Colors.RESET} [leave empty to keep]: ").strip()
    if override:
        info['executable'] = override.replace("\\", "/")

    mode = input("Manifest style [installed/legacy] (default installed, StateFlags 4): ").strip().lower() or "installed"
    if mode not in ("installed", "legacy"):
        print_color("[ERROR] Choose installed or legacy.", Colors.RED)
        return
    try:
        fake_exe_path = steam_fake_exe_path(steam_path, info['installdir'], info['executable'])
    except ValueError as e:
        print_color(f"[ERROR] {e}", Colors.RED)
        return

    acf_path = steamapps_path(steam_path) / f'appmanifest_{appid}.acf'
    print(f"\n{Colors.BOLD}Summary:{Colors.RESET}")
    print(f"  AppManifest: {Colors.GRAY}{acf_path}{Colors.RESET}")
    print(f"  Fake exe:    {Colors.GRAY}{fake_exe_path}{Colors.RESET}")
    print(f"  Manifest:    {mode}")
    if fake_exe_path.exists() or acf_path.exists():
        print_color("  [*] Existing setup found (will be overwritten if launched).", Colors.YELLOW)

    choice = ask_confirm()
    if choice == 'delete':
        res = delete_steam_game(steam_path, appid, info['installdir'], info['executable'])
        deleted = False
        if res.get("manifest") and res["manifest"][1]:
            print_color(f"[OK] Deleted manifest: {res['manifest'][0]}", Colors.GREEN)
            deleted = True
        if res.get("executable") and res["executable"][1]:
            print_color(f"[OK] Deleted executable: {res['executable'][0]}", Colors.GREEN)
            deleted = True
        if res.get("folder") and res["folder"][1]:
            print_color(f"[OK] Cleaned up folder: {res['folder'][0]}", Colors.GREEN)
            deleted = True
        if not deleted:
            print_color("[*] No existing files or folder found to delete.", Colors.YELLOW)
        else:
            print_color("[OK] Deletion complete.", Colors.GREEN, bold=True)
        time.sleep(config.SLEEP_SHORT)
        return
    elif not choice:
        print_color("\n[!] Operation cancelled.", Colors.YELLOW)
        time.sleep(config.SLEEP_SHORT)
        return

    acf = generate_appmanifest(appid, info['name'], info['installdir'], steam_path,
                               depot_id=info.get('depot_id'), manifest_mode=mode)
    if not acf:
        print_color("[ERROR] Failed to create appmanifest. Aborting.", Colors.RED)
        time.sleep(config.SLEEP_SHORT)
        return

    if not create_steam_fake_exe(faker, fake_exe_path, info['executable']):
        acf.unlink(missing_ok=True)
        time.sleep(config.SLEEP_SHORT)
        return

    print()
    faker.launch_executable(fake_exe_path)
    print_color("\n[OK] Steam Quest setup complete!", Colors.GREEN, bold=True)
    print_color("[!] Discord MUST be running for detection to work.", Colors.YELLOW)
    print_color("[*] Keep the process running until the quest is done.", Colors.CYAN)
    input(f"\n{Colors.GRAY}Press Enter to continue...{Colors.RESET}")

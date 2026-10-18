"""
discord_db.py – DiscordGamesDB class and database search mode.
"""

import sys
import time

from . import config, textmatch
from .ui import (
    Colors, print_color, print_boxed_title,
    loading_animation, ask_confirm,
)
from .net import fetch_json
from .errors import NetworkError, DatabaseLoadError


class DiscordGamesDB:
    """Loads and searches the Discord-detectable games database."""

    def __init__(self):
        self.games: list = []
        self.source: str | None = None
        self._load()

    def _load(self):
        """Load games from Discord API or GitHub backup."""
        print_color("\n[*] Loading games database...", Colors.YELLOW)
        if self._load_from_discord_api():
            return
        print_color("[!] Discord API unavailable, using GitHub backup...", Colors.YELLOW)
        if self._load_from_github():
            return
        raise DatabaseLoadError("Could not load games database from any source.")

    def _load_from_discord_api(self) -> bool:
        try:
            loading_animation("Connecting to Discord API", 1.0)
            self.games = fetch_json(config.DISCORD_API_URL, headers=config.DISCORD_HEADERS)
            self.source = "Discord Official API"
            print_color(f"[OK] Loaded {len(self.games)} games from Discord API", Colors.GREEN, bold=True)
            print_color("[*] Using LIVE database (fresh from Discord's servers)", Colors.CYAN)
            return True
        except NetworkError as e:
            print_color(f"[!] Discord API error: {e}", Colors.YELLOW)
            return False

    def _load_from_github(self) -> bool:
        try:
            loading_animation("Fetching GitHub backup", 1.0)
            self.games = fetch_json(config.GITHUB_BACKUP_URL, timeout=config.REQUEST_TIMEOUT_LONG)
            self.source = "GitHub Backup"
            print_color(f"[OK] Loaded {len(self.games)} games from GitHub", Colors.GREEN, bold=True)
            return True
        except NetworkError as e:
            print_color(f"[ERROR] GitHub backup failed: {e}", Colors.RED)
            return False

    def search_games(self, query: str) -> list:
        """Search for games by name or alias, returning up to MAX_SEARCH_RESULTS matches.

        Case, punctuation and symbols (®, ™, :, -, ...) are ignored, and the
        query words don't need to be adjacent. Results are ranked: exact name,
        exact alias, name prefix, name contains, alias contains, then name /
        alias containing every query word. Ties keep database order, and the
        cap is applied after ranking.
        """
        scored: dict = {}
        for idx, game in enumerate(self.games):
            tier = self._match_tier(query, game)
            if tier is None:
                continue
            game_id = game.get('id')
            if game_id not in scored or tier < scored[game_id][0]:
                scored[game_id] = (tier, idx, game)
        ranked = sorted(scored.values(), key=lambda item: (item[0], item[1]))
        return [game for _, _, game in ranked][:config.MAX_SEARCH_RESULTS]

    @staticmethod
    def _match_tier(query: str, game: dict) -> int | None:
        """Rank tier of *game* for *query* (lower is better), or None if no match."""
        name_score = textmatch.match_score(query, game.get('name', ''))
        alias_score = textmatch.best_score(query, list(game.get('aliases', []) or []))
        if name_score == textmatch.EXACT:
            return 0
        if alias_score == textmatch.EXACT:
            return 1
        if name_score == textmatch.PREFIX:
            return 2
        if name_score in (textmatch.CONTAINS, textmatch.COMPACT):
            return 3
        if alias_score in (textmatch.PREFIX, textmatch.CONTAINS, textmatch.COMPACT):
            return 4
        if name_score == textmatch.TOKENS:
            return 5
        if alias_score == textmatch.TOKENS:
            return 6
        return None

    # ── executable helpers ────────────────────────────────────────────────────
    _SKIP_EXE_PATTERNS = [
        '_be.exe', '_eac.exe', 'launcher', 'unins',
        'crash', 'report', 'update', 'setup', 'install',
    ]

    def _filter_win32_exes(self, game: dict, skip_patterns: bool = True) -> list:
        result, seen = [], set()
        for exe in game.get('executables', []):
            if exe.get('os') != 'win32':
                continue
            name = exe.get('name', '')
            if name.startswith('>'):
                name = name[1:]
            name = name.replace('\\', '/')
            if not name or name in seen:
                continue
            if skip_patterns and any(p in name.lower() for p in self._SKIP_EXE_PATTERNS):
                continue
            seen.add(name)
            result.append(name)
        return result

    def get_win32_executable(self, game: dict) -> str | None:
        candidates = self._filter_win32_exes(game, skip_patterns=True)
        return candidates[0] if candidates else None

    def get_all_executables(self, game: dict) -> list:
        return self._filter_win32_exes(game, skip_patterns=False)


# ── Interactive UI ────────────────────────────────────────────────────────────

def _pick_discord_game(db: DiscordGamesDB, query: str) -> dict | None:
    """Search the Discord DB and let the user choose a game."""
    loading_animation(f"Searching for '{query}'", 0.8)
    matches = db.search_games(query)
    if not matches:
        print_color(f"\n[ERROR] No games found for '{query}'", Colors.RED)
        print_color("[!] Try a different search term or abbreviation", Colors.YELLOW)
        time.sleep(config.SLEEP_LONG)
        return None

    print(f"\n{Colors.BOLD}{Colors.GREEN}Found {len(matches)} game(s):{Colors.RESET}\n")
    print(f"{Colors.GRAY}{'─' * 75}{Colors.RESET}")
    for idx, game in enumerate(matches, 1):
        name    = game.get('name', 'Unknown')
        game_id = game.get('id', 'N/A')
        aliases = game.get('aliases', [])
        print(f"{Colors.BOLD}{Colors.CYAN}{idx:2d}.{Colors.RESET} {Colors.WHITE}{name}{Colors.RESET}"
              f"  {Colors.GRAY}[app id {game_id}]{Colors.RESET}")
        if aliases:
            alias_str = ', '.join(aliases[:3])
            if len(aliases) > 3:
                alias_str += f" (+{len(aliases) - 3} more)"
            print(f"    {Colors.GRAY}Aliases: {alias_str}{Colors.RESET}")
        if idx < len(matches):
            print(f"{Colors.GRAY}{'─' * 75}{Colors.RESET}")
    print()

    raw = input(f"{Colors.BOLD}Select [1-{len(matches)}]{Colors.RESET} (or 'back'): ").strip()
    if raw.lower() in ('back', 'b', ''):
        return None
    try:
        idx = int(raw)
        if not 1 <= idx <= len(matches):
            raise ValueError
    except ValueError:
        print_color("\n[ERROR] Enter a valid number", Colors.RED)
        time.sleep(config.SLEEP_SHORT)
        return None
    return matches[idx - 1]


def _resolve_discord_exe(db: DiscordGamesDB, game: dict) -> str | None:
    """Return the primary exe, prompting the user if none found."""
    exe_name = db.get_win32_executable(game)
    if exe_name:
        return exe_name
    print_color("\n[ERROR] No Windows executable found for this game", Colors.RED)
    print_color("[!] This game might not have a Windows version or executable data", Colors.YELLOW)
    if ask_confirm("Enter executable name manually?"):
        exe_name = input(f"{Colors.BOLD}Executable name:{Colors.RESET} ").strip()
        if not exe_name:
            print_color("\n[!] Operation cancelled", Colors.YELLOW)
            time.sleep(config.SLEEP_SHORT)
            return None
        return exe_name
    return None


def database_mode(db: DiscordGamesDB, faker) -> None:
    """Database search mode."""
    print_boxed_title("DATABASE SEARCH", width=50, color=Colors.CYAN)
    print_color(f"[*] Database: {db.source}", Colors.CYAN)
    print_color(f"[*] Total games available: {len(db.games)}", Colors.GRAY)
    print_color("\n[*] Search by name or abbreviation", Colors.CYAN)
    print_color("[*] Examples: PUBG, Fortnite, League, Valorant, Minecraft", Colors.GRAY)
    print()

    query = input(f"{Colors.BOLD}Search{Colors.RESET} (or 'back'): ").strip()
    if query.lower() in ('back', 'b', ''):
        return

    selected = _pick_discord_game(db, query)
    if not selected:
        return

    loading_animation("Analysing game data", 0.8)
    exe_name = _resolve_discord_exe(db, selected)
    if not exe_name:
        return

    all_exes = db.get_all_executables(selected)

    print(f"\n{Colors.BOLD}Game Information:{Colors.RESET}")
    print(f"  Name:               {Colors.CYAN}{selected.get('name')}{Colors.RESET}")
    print(f"  ID:                 {Colors.GRAY}{selected.get('id')}{Colors.RESET}")
    print(f"  Primary Executable: {Colors.GREEN}{exe_name}{Colors.RESET}")
    if len(all_exes) > 1:
        print(f"  {Colors.GRAY}Other executables: {', '.join(all_exes[1:3])}{Colors.RESET}")
        if len(all_exes) > 3:
            print(f"  {Colors.GRAY}(+{len(all_exes) - 3} more executables available){Colors.RESET}")
    print(f"  Path: {Colors.GRAY}{faker.desktop_path / config.FAKE_EXE_DIR / exe_name}{Colors.RESET}")

    if not ask_confirm():
        print_color("\n[!] Operation cancelled", Colors.YELLOW)
        time.sleep(config.SLEEP_SHORT)
        return

    result = faker.create_fake_game(exe_name)
    if result:
        print()
        faker.launch_executable(result)
        print_color("\n[OK] Setup complete! Discord should detect the game.", Colors.GREEN, bold=True)
        print_color("[!] IMPORTANT: Discord MUST be running for the spoofing to work", Colors.YELLOW)
        print_color("[*] Keep the process running until quest is complete", Colors.CYAN)
        print_color("[*] TIP: Run this tool again to emulate another game simultaneously!", Colors.MAGENTA)

    input(f"\n{Colors.GRAY}Press Enter to continue...{Colors.RESET}")

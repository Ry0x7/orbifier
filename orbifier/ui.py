"""
ui.py – Terminal UI helpers: colors, banners, animations, menus, credits.
"""

import sys
import time

from . import config


class Colors:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
    GRAY    = '\033[90m'


class _NoColors:
    """Same attribute names as Colors, but every value is empty (plain text)."""
    RESET = BOLD = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = GRAY = ''


# Optional output hook (set by the GUI). When set, print_color() also forwards
# (text, color) to it, and loading_animation() skips the terminal spinner.
# The CLI never sets it, so terminal behaviour is unchanged.
_output_hook = None


def set_output_hook(hook) -> None:
    """Register a callable(text, color) that receives every print_color() message."""
    global _output_hook
    _output_hook = hook


def print_color(text, color=Colors.WHITE, bold=False):
    """Print colored text."""
    style = Colors.BOLD if bold else ''
    print(f"{style}{color}{text}{Colors.RESET}")
    if _output_hook is not None:
        _output_hook(text, color)


def print_boxed_title(title, width=50, color=Colors.CYAN):
    """Print a boxed title with ASCII borders."""
    border = f"{Colors.BOLD}{color}{'+' + '-' * (width - 2) + '+'}{Colors.RESET}"
    title_padding = (width - len(title) - 4) // 2
    extra_space = (width - len(title) - 4) % 2
    title_line = (
        f"{Colors.BOLD}{color}|{Colors.RESET}"
        f"{' ' * title_padding}{Colors.BOLD}{title}{Colors.RESET}"
        f"{' ' * (title_padding + extra_space)}"
        f"{Colors.BOLD}{color}|{Colors.RESET}"
    )
    print(f"\n{border}")
    print(title_line)
    print(f"{border}\n")


def print_banner():
    """Display ASCII banner."""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
                                                                
 _____ _____ _____ _____ _____ _____ _____ _____ 
|     | __  | __  |     |   __|     |   __| __  |
|  |  |    -| __ -|-   -|   __|-   -|   __|    -|
|_____|__|__|_____|_____|__|  |_____|_____|__|__|
                                                                
{Colors.RESET}
    {Colors.GRAY}Developer: {Colors.CYAN}{config.DEVELOPER}{Colors.RESET}
    {Colors.GRAY}Version: {Colors.WHITE}{config.VERSION}{Colors.RESET}
    {Colors.GRAY}Database: {Colors.GREEN}Discord Official API + GitHub Archive{Colors.RESET}
    {Colors.BOLD}{Colors.RED}EDUCATIONAL USE ONLY - USE AT YOUR OWN RISK{Colors.RESET}
"""
    print(banner)

    from .faker import is_process_elevated, ELEVATED_WARNING  # lazy: faker imports ui
    if is_process_elevated():
        print_color(f"    [!] {ELEVATED_WARNING}\n", Colors.YELLOW, bold=True)


def loading_animation(text, duration=1.5):
    """Display loading animation."""
    if _output_hook is not None:
        return  # GUI shows its own busy indicator
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    if (sys.stdout.encoding or '').lower().replace('-', '') != 'utf8':
        frames = ['|', '/', '-', '\\']
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        sys.stdout.write(f"\r{Colors.CYAN}{frames[i % len(frames)]}{Colors.RESET} {text}")
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    sys.stdout.write("\r" + " " * (len(text) + 5) + "\r")
    sys.stdout.flush()


def ask_confirm(prompt="Create and launch?", allow_delete=True) -> bool | str:
    """Ask a confirmation question. Returns True if confirmed, 'delete' if 'd', False otherwise."""
    suffix = " [Y/n] (or 'd' to delete): " if allow_delete else " [Y/n]: "
    answer = input(f"\n{Colors.BOLD}{prompt}{Colors.RESET}{suffix}").strip().lower()
    if allow_delete and answer in ('d', 'delete'):
        return 'delete'
    return answer in ('', 'y', 'yes')


def print_menu():
    """Display main menu."""
    print_boxed_title("MAIN MENU", width=50, color=Colors.CYAN)
    print(f"  {Colors.BOLD}{Colors.GREEN}1.{Colors.RESET} Search Discord database (Official API)")
    print(f"  {Colors.BOLD}{Colors.GREEN}2.{Colors.RESET} Manual mode (custom executable)")
    print(f"  {Colors.BOLD}{Colors.YELLOW}3.{Colors.RESET} Steam Quest Mode  {Colors.YELLOW}[NEW - for Marathon, Toxic Commando…]{Colors.RESET}")
    print(f"  {Colors.BOLD}{Colors.GREEN}4.{Colors.RESET} Credits & Info")
    print(f"  {Colors.BOLD}{Colors.RED}5.{Colors.RESET} Exit\n")


def credits_text(c=Colors, enter_prompt=True) -> str:
    """Return the credits text. Pass ``c=_NoColors`` for plain text."""
    text = f"""
    {c.BOLD}Developer:{c.RESET} {c.CYAN}{config.DEVELOPER}{c.RESET}
    {c.BOLD}Version:{c.RESET}   {c.WHITE}{config.VERSION}{c.RESET}

    {c.BOLD}Description:{c.RESET}
    This tool works as a game process spoofer. It tricks Discord into
    thinking you're running a game by creating fake processes with the
    exact names Discord expects.
    
    {c.BOLD}IMPORTANT:{c.RESET} {c.RED}Discord MUST be running for this to work!{c.RESET}
    
    {c.BOLD}How it works (Game Spoofing):{c.RESET}
    1. Connects to Discord's official API to get the latest game list
    2. Finds the exact process name Discord expects for each game
    3. Copies exe.exe to Desktop/Win64/ and renames it to match
    4. Launches the fake process in background
    5. Discord scans running processes and detects the fake process name
    6. Discord thinks you're playing the game (process name match)
    7. The fake process must stay running for Discord to keep detecting it
    
    {c.BOLD}Steam Quest Mode (NEW):{c.RESET}
    Some games (Marathon, Toxic Commando…) require Discord to verify
    that Steam has at least partially downloaded them.
    Steam Quest Mode bypasses this by:
    1. Fetching app info automatically from SteamCMD public API
    2. Generating a fake appmanifest_<appid>.acf in your steamapps/ folder
    3. Placing the fake exe directly in steamapps/common/<installdir>/
    Discord then sees a valid Steam manifest + a running process = quest detected.
    
    {c.BOLD}Database Sources:{c.RESET}
    • Primary: Discord Official API
    • Backup:  GitHub Archive by Cynosphere

    {c.BOLD}Quest Board Data:{c.RESET}
    • Quest and region data: discordquest.com (unofficial public dataset)
    • Region availability is informational; Discord decides final eligibility
    • No Discord token is used
    
    {c.BOLD}Pro Tips:{c.RESET}
    • Use Steam Quest Mode for games not detected by modes 1 or 2
    • Find AppIDs at https://steamdb.info
    • The fake process must stay running for Discord to detect it
    
    {c.BOLD}{c.GREEN}Multi-Game Emulation:{c.RESET}
    • Run this tool multiple times to emulate multiple games at once
    • Complete ALL orb quests simultaneously in just 15 minutes
    
    {c.BOLD}{c.RED}WARNING - EDUCATIONAL USE ONLY - USE AT YOUR OWN RISK{c.RESET}
    • Users are SOLELY responsible for compliance with Discord ToS
    • The developers are NOT responsible for any consequences
    • Use at your own risk
    
    {c.BOLD}{c.GREEN}Original Author & Source:{c.RESET}
    Orbifier is based on and inspired by {c.BOLD}orbshacker{c.RESET} by {c.CYAN}Strykey{c.RESET}.
    All core spoofing concepts and original foundations are credited to Strykey:
    {c.CYAN}https://github.com/strykey/orbshacker{c.RESET}
    
    {c.GRAY}Extended & Maintained by: {config.DEVELOPER}{c.RESET}

    {c.BOLD}{c.MAGENTA}Support the project:{c.RESET} {c.CYAN}{config.KOFI_URL}{c.RESET}
"""
    if enter_prompt:
        text += f"    {c.GRAY}Press Enter to return to menu...{c.RESET}\n"
    return text


def show_credits():
    """Display credits."""
    print_boxed_title("CREDITS", width=65, color=Colors.CYAN)
    print(credits_text())
    input()

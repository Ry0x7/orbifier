"""
orbifier – central configuration.

Reads user-editable values from the root-level ``settings.py``.
If a value is missing there, the default defined below is used.
Internal-only constants (API URLs, headers, timeouts) live here
and are NOT exposed in settings.py.
"""

import importlib
import sys

# ── Load user settings (root-level settings.py) ──────────────────────────────
# This lets the user edit a single, visible file at the project root.
try:
    import settings as _user  # root-level settings.py
except ImportError:
    _user = None  # no user settings file – use all defaults


def _get(name: str, default):
    """Return a value from the user settings module, falling back to *default*."""
    return getattr(_user, name, default)


# ── App identity ──────────────────────────────────────────────────────────────
VERSION   = _get("VERSION",   "1.4.0")
DEVELOPER = _get("DEVELOPER", "Ry0x7")

# ── GitHub repo ───────────────────────────────────────────────────────────────
GITHUB_REPO_OWNER = _get("GITHUB_REPO_OWNER", "Ry0x7")
GITHUB_REPO_NAME  = _get("GITHUB_REPO_NAME",  "orbifier")
REPO_URL          = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"

# ── Support ───────────────────────────────────────────────────────────────────
KOFI_URL = "https://ko-fi.com/ry0x7"

# ── Network endpoints (internal – not in settings.py) ─────────────────────────
DISCORD_API_URL           = "https://discord.com/api/v9/applications/detectable"
DISCORD_QUEST_API_URL     = "https://api.discordquest.com/api/quests"
DISCORD_QUEST_REGIONS_URL = "https://api.discordquest.com/api/regions"
GITHUB_BACKUP_URL         = (
    "https://gist.githubusercontent.com/Cynosphere/"
    "c1e77f77f0e565ddaac2822977961e76/raw/gameslist.json"
)
STEAMCMD_API_URL          = "https://api.steamcmd.net/v1/info"
STEAM_STORE_SEARCH_URL    = "https://store.steampowered.com/api/storesearch"

# ── HTTP settings (internal) ─────────────────────────────────────────────────
REQUEST_TIMEOUT      = 10
REQUEST_TIMEOUT_LONG = 20
QUEST_API_TIMEOUT    = 20
QUEST_CACHE_SECONDS  = 300

DISCORD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://discord.com/",
    "Origin":          "https://discord.com",
}

# ── UI / UX (user-editable via settings.py) ───────────────────────────────────
SLEEP_SHORT        = _get("SLEEP_SHORT",        1.0)
SLEEP_LONG         = _get("SLEEP_LONG",         2.0)
FAKE_EXE_DIR       = _get("FAKE_EXE_DIR",       "Win64")
MAX_SEARCH_RESULTS = _get("MAX_SEARCH_RESULTS", 50)
QUEST_MINUTES      = _get("QUEST_MINUTES",      15)  # countdown shown in ACTIVE QUESTS
AUTO_CLOSE         = _get("AUTO_CLOSE",         True)
AUTO_CLEAN         = _get("AUTO_CLEAN",         True)

# ╔═══════════════════════════════════════════════════════════╗
# ║              ORBIFIER – USER SETTINGS                    ║
# ║  Edit values here. The app reads from this file.         ║
# ╚═══════════════════════════════════════════════════════════╝

# ── App identity ──────────────────────────────────────────────
VERSION   = "1.6.0"
DEVELOPER = "Ry0x7"

# ── GitHub repo (for auto-update in .exe builds) ─────────────
GITHUB_REPO_OWNER = "Ry0x7"
GITHUB_REPO_NAME  = "orbifier"

# ── Fake exe output folder (created on Desktop) ─────────────
FAKE_EXE_DIR = "Win64"

# ── Timings (seconds) ────────────────────────────────────────
SLEEP_SHORT = 1.0
SLEEP_LONG  = 2.0

# ── Search ────────────────────────────────────────────────────
MAX_SEARCH_RESULTS = 50

# ── Quests ────────────────────────────────────────────────────
QUEST_MINUTES = 20   # minutes the ACTIVE QUESTS countdown runs per game
AUTO_CLOSE    = True # automatically close fake game when timer reaches 00:00
AUTO_CLEAN    = True # automatically delete fake exe & directory after quest stops
CLOSE_QUESTS_ON_EXIT = True  # stop active fake quests when Orbifier closes
OUTPUT_DIR = ""              # blank = Desktop\<FAKE_EXE_DIR>
CHECK_UPDATES = True         # check GitHub releases at startup

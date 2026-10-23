"""user_settings.py – persistent overrides saved from the SETTINGS screen.

The bundled ``settings.py`` stays the fallback; this module stores the values a
user changes in the app as JSON under ``%APPDATA%\\Orbifier\\settings.json`` (or
``~/.orbifier/settings.json``). ``ORBIFIER_SETTINGS`` points it somewhere else,
which the tests use to keep runs isolated.
"""

import json
import math
import os
from pathlib import Path

SETTINGS_KEYS = ("QUEST_MINUTES", "AUTO_CLOSE", "AUTO_CLEAN",
                 "CLOSE_QUESTS_ON_EXIT", "OUTPUT_DIR", "CHECK_UPDATES")

BOOLEAN_KEYS = ("AUTO_CLOSE", "AUTO_CLEAN", "CLOSE_QUESTS_ON_EXIT", "CHECK_UPDATES")

MINUTES_MESSAGE = "QUEST_MINUTES must be between 1 and 1440 minutes."


class SettingsError(ValueError):
    """Raised when settings cannot be validated, saved, read, or deleted."""


# Set by every load_overrides() call so the GUI can show what went wrong.
LOAD_ERROR: str | None = None


def _home_dir() -> Path:
    """Home directory used when neither env variable is available."""
    return Path.home()


def settings_path() -> Path:
    """Where the JSON overrides live."""
    override = os.environ.get("ORBIFIER_SETTINGS", "").strip()
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "Orbifier" / "settings.json"
    return _home_dir() / ".orbifier" / "settings.json"


def validate(values: dict) -> dict:
    """Return a normalized copy of *values*, or raise SettingsError.

    Unknown keys are dropped so a hand-edited file cannot inject config names.
    """
    if not isinstance(values, dict):
        raise SettingsError("Settings must be a JSON object.")

    valid: dict = {}
    for key in SETTINGS_KEYS:
        if key not in values:
            continue
        value = values[key]

        if key == "QUEST_MINUTES":
            if isinstance(value, bool):
                raise SettingsError(MINUTES_MESSAGE)
            try:
                minutes = float(value)
            except (TypeError, ValueError):
                raise SettingsError(MINUTES_MESSAGE) from None
            if not math.isfinite(minutes) or not 1 <= minutes <= 1440:
                raise SettingsError(MINUTES_MESSAGE)
            valid[key] = minutes
        elif key in BOOLEAN_KEYS:
            if not isinstance(value, bool):
                raise SettingsError(f"{key} must be true or false.")
            valid[key] = value
        elif key == "OUTPUT_DIR":
            if not isinstance(value, str):
                raise SettingsError("OUTPUT_DIR must be a string.")
            valid[key] = value.strip()

    return valid


def load_overrides() -> dict:
    """Read the stored overrides, skipping anything invalid.

    A missing file simply means "no overrides". Read errors and invalid values
    are reported through LOAD_ERROR rather than raised, so a broken file can
    never stop the app from starting.
    """
    global LOAD_ERROR
    LOAD_ERROR = None

    path = settings_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        LOAD_ERROR = f"Could not read settings from {path}: {exc}"
        return {}

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        LOAD_ERROR = f"Could not read settings from {path}: {exc}"
        return {}

    if not isinstance(raw, dict):
        LOAD_ERROR = f"Could not read settings from {path}: expected a JSON object."
        return {}

    loaded: dict = {}
    problems: list[str] = []
    for key in SETTINGS_KEYS:
        if key not in raw:
            continue
        try:
            loaded.update(validate({key: raw[key]}))
        except SettingsError as exc:
            problems.append(str(exc))

    if problems:
        LOAD_ERROR = "; ".join(problems)
    return loaded


def save_overrides(values: dict) -> Path:
    """Validate and atomically write *values*; return the file path."""
    valid = validate(values)
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SettingsError(f"Could not save settings: {exc}") from exc

    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(valid, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise SettingsError(f"Could not save settings: {exc}") from exc
    return path


def delete_overrides() -> bool:
    """Delete the stored overrides; False when there was nothing to delete."""
    path = settings_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SettingsError(f"Could not delete settings: {exc}") from exc
    return True

"""
Custom exceptions for orbifier.

Keep it small — one base class + a few specific ones.
"""


class OrbifierError(Exception):
    """Base error for all orbifier errors."""


class NetworkError(OrbifierError):
    """An API / HTTP call failed."""


class SteamNotFoundError(OrbifierError):
    """Steam installation could not be located."""


class DatabaseLoadError(OrbifierError):
    """Failed to load the games database from any source."""

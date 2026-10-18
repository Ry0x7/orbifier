"""Tests for errors.py – exception hierarchy."""

import pytest
from orbifier.errors import (
    OrbifierError,
    NetworkError,
    SteamNotFoundError,
    DatabaseLoadError,
)


def test_network_error_is_orbifier_error():
    assert issubclass(NetworkError, OrbifierError)


def test_steam_not_found_is_orbifier_error():
    assert issubclass(SteamNotFoundError, OrbifierError)


def test_database_load_error_is_orbifier_error():
    assert issubclass(DatabaseLoadError, OrbifierError)


def test_can_catch_all_with_base():
    with pytest.raises(OrbifierError):
        raise NetworkError("test")

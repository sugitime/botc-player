import pytest

from botc_player.browser.botc_client import normalize_lobby_url


def test_full_url():
    assert normalize_lobby_url("https://botc.app/join/test") == "https://botc.app/join/test"


def test_bare_code():
    assert normalize_lobby_url("test") == "https://botc.app/join/test"


def test_join_prefix():
    assert normalize_lobby_url("join/abc") == "https://botc.app/join/abc"


def test_empty():
    with pytest.raises(ValueError):
        normalize_lobby_url("  ")

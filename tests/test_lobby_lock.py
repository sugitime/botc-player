from botc_player.browser.botc_client import (
    BotcClient,
    lobby_code_from_url,
)


def test_lobby_code_from_join_url():
    assert lobby_code_from_url("https://botc.app/join/test") == "test"
    assert lobby_code_from_url("https://www.botc.app/join/MyRoom") == "myroom"


def test_pin_blocks_other_lobby_join():
    client = BotcClient()
    client.pin_lobby("https://botc.app/join/test", session_url="https://botc.app/play")
    assert client.lobby_locked
    assert client.pinned_lobby_code == "test"
    assert client._is_allowed_url("https://botc.app/play") is True
    assert client._is_allowed_url("https://botc.app/join/test") is True
    assert client._is_allowed_url("https://botc.app/join/other") is False
    assert client._is_allowed_url("https://botc.app/login") is False
    assert client._is_allowed_url("https://botc.app/lobbies") is False
    assert client._is_allowed_url("https://botc.app/") is False


def test_join_lobby_refuses_switch_when_locked():
    client = BotcClient()
    client.connected = True
    client.pin_lobby("test", session_url="https://botc.app/play")
    client.page = type("P", (), {"url": "https://botc.app/play"})()
    ok = client.join_lobby("https://botc.app/join/other-room", "Dino")
    assert ok is False


def test_lobby_list_detection():
    client = BotcClient()
    client.lobby_locked = True
    client.pinned_lobby_url = "https://botc.app/join/test"
    client.pinned_lobby_code = "test"

    class FakePage:
        url = "https://botc.app/lobbies"
        def inner_text(self, _sel):
            return "Public Games\nJoin a game\nCreate game\nOpen games list"

    client.page = FakePage()
    assert client._looks_like_lobby_list() is True


def test_hash_route_is_same_lobby():
    client = BotcClient()
    client.pin_lobby("https://botc.app/join/test", session_url="https://botc.app/play")
    assert client._url_has_pinned_code("https://botc.app/#test") is True
    assert client._is_allowed_url("https://botc.app/#test") is True
    assert client._is_allowed_url("https://botc.app/join/test") is True
    # Hash route for our lobby is not a generic list
    client.page = type("P", (), {
        "url": "https://botc.app/#test",
        "inner_text": lambda self, s: "Join game Seat 1 Click to claim",
    })()
    assert client._looks_like_lobby_list() is False

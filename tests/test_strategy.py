from botc_player.agent.game_state import GamePhase, GameState
from botc_player.knowledge.strategy import may_speak_now, should_raise_hand


def test_no_overtalk_during_day():
    state = GameState(phase=GamePhase.DAY_DISCUSSION)
    assert may_speak_now(state, someone_is_speaking=True, silence_seconds=0.1) is False
    assert should_raise_hand(state, someone_is_speaking=True) is True


def test_speak_when_called_on():
    state = GameState(phase=GamePhase.DAY_DISCUSSION, called_on=True)
    assert may_speak_now(state, someone_is_speaking=False, silence_seconds=0.5) is True


def test_private_chat_more_open():
    state = GameState(phase=GamePhase.PRIVATE_CHAT)
    assert may_speak_now(state, someone_is_speaking=False, silence_seconds=0.5) is True


def test_night_only_when_awaiting():
    state = GameState(phase=GamePhase.NIGHT, awaiting_night_response=False)
    assert may_speak_now(state, someone_is_speaking=False, silence_seconds=5) is False
    state.awaiting_night_response = True
    assert may_speak_now(state, someone_is_speaking=False, silence_seconds=0.1) is True

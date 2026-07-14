from botc_player.orchestrator import Orchestrator


def test_take_seat_phrases():
    assert Orchestrator.is_take_seat_command("AI, take a seat")
    assert Orchestrator.is_take_seat_command("ai take a seat")
    assert Orchestrator.is_take_seat_command("please take a seat now")
    assert Orchestrator.is_take_seat_command("claim a seat")
    assert Orchestrator.is_take_seat_command("sit down")
    # Past tense / unrelated should not match
    assert not Orchestrator.is_take_seat_command("I already took my seat yesterday")
    assert not Orchestrator.is_take_seat_command("[heard speech, 1.2s]")
    assert not Orchestrator.is_take_seat_command("hello everyone")

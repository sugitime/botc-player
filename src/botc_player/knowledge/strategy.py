"""High-level strategic heuristics the agent should follow."""

from __future__ import annotations

from botc_player.agent.game_state import GamePhase, GameState, TeamGoal


def team_objective(state: GameState) -> str:
    if state.team_goal == TeamGoal.EVIL_WIN:
        return (
            "You are on the Evil team. Protect the Demon, eliminate strong Good players "
            "when safe, maintain a consistent bluff, and never casually reveal Evil info."
        )
    if state.team_goal == TeamGoal.GOOD_WIN:
        return (
            "You are on the Good team. Share useful information carefully, find the Demon, "
            "and avoid executing critical Good roles (e.g. Saint) without strong reason."
        )
    return (
        "Your true alignment may be unknown or ambiguous. Play for survival of useful "
        "information, track contradictions, and update your team goal when the grimoire/role is clear."
    )


def phase_guidance(state: GameState) -> str:
    phase = state.phase
    if phase == GamePhase.NIGHT:
        return (
            "Night: respond promptly to Storyteller pings. Pick ability targets that help your team. "
            "Do not speak publicly. Keep private replies short and clear."
        )
    if phase == GamePhase.NOMINATION:
        return (
            "Nomination phase: decide whether to nominate or second based on team EV. "
            "If nominating, give a concise case. Raise hand if required by table norms."
        )
    if phase == GamePhase.VOTING:
        return (
            "Voting: cast vote when the UI allows. Prefer decisive team-aligned votes. "
            "Do not filibuster; vote and stay quiet unless asked."
        )
    if phase == GamePhase.PRIVATE_CHAT:
        return (
            "Private chat: you may speak more freely with the other participant(s). "
            "Coordinate strategy; still be polite. Evil may coordinate lies here."
        )
    if phase == GamePhase.DAY_DISCUSSION:
        return (
            "Public day: do not overtalk. Raise hand to speak. Wait to be called. "
            "When speaking, 1–3 short points then yield. Never interrupt."
        )
    return "Observe, update notes, and wait for a clear action opportunity."


def should_raise_hand(state: GameState, someone_is_speaking: bool) -> bool:
    if state.phase not in (GamePhase.DAY_DISCUSSION, GamePhase.NOMINATION):
        return False
    if state.hand_raised:
        return False
    if someone_is_speaking and not state.called_on:
        return True
    if state.phase == GamePhase.DAY_DISCUSSION and not state.called_on:
        return True
    return False


def may_speak_now(state: GameState, someone_is_speaking: bool, silence_seconds: float) -> bool:
    """Public-speech gate: avoid rudeness and overtalk."""
    if state.phase == GamePhase.PRIVATE_CHAT:
        return silence_seconds >= 0.4 or not someone_is_speaking
    if state.phase == GamePhase.NIGHT:
        return state.awaiting_night_response
    if state.phase in (GamePhase.DAY_DISCUSSION, GamePhase.NOMINATION):
        if state.called_on:
            return silence_seconds >= 0.3
        # Only speak unprompted after a long silence if hand system unavailable
        if not someone_is_speaking and silence_seconds >= 4.0 and state.hand_raised:
            return True
        return False
    if state.phase == GamePhase.VOTING:
        return False
    return False

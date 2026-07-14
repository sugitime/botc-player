"""Mutable game / social state tracked by the agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class GamePhase(str, Enum):
    LOBBY = "lobby"
    DAY_DISCUSSION = "day_discussion"
    NOMINATION = "nomination"
    VOTING = "voting"
    NIGHT = "night"
    PRIVATE_CHAT = "private_chat"
    UNKNOWN = "unknown"


class TeamGoal(str, Enum):
    GOOD_WIN = "good_win"
    EVIL_WIN = "evil_win"
    UNKNOWN = "unknown"


@dataclass
class PlayerNote:
    name: str
    seat: Optional[int] = None
    claimed_role: Optional[str] = None
    suspected_alignment: str = "unknown"
    notes: list[str] = field(default_factory=list)


@dataclass
class GameState:
    phase: GamePhase = GamePhase.UNKNOWN
    day_number: int = 0
    my_name: str = "Dino"
    my_role: Optional[str] = None
    my_alignment: str = "unknown"  # good | evil | unknown
    bluff_role: Optional[str] = None
    team_goal: TeamGoal = TeamGoal.UNKNOWN

    players: dict[str, PlayerNote] = field(default_factory=dict)
    alive: set[str] = field(default_factory=set)
    dead: set[str] = field(default_factory=set)

    hand_raised: bool = False
    called_on: bool = False
    muted: bool = False
    awaiting_night_response: bool = False
    in_private_chat_with: Optional[str] = None

    last_transcripts: list[str] = field(default_factory=list)
    private_notes: list[str] = field(default_factory=list)
    pending_vote_target: Optional[str] = None
    script_name: str = "Trouble Brewing"

    extra: dict[str, Any] = field(default_factory=dict)

    def set_my_role(self, role: str, alignment: str) -> None:
        self.my_role = role
        self.my_alignment = alignment
        if alignment == "evil":
            self.team_goal = TeamGoal.EVIL_WIN
        elif alignment == "good":
            self.team_goal = TeamGoal.GOOD_WIN
        else:
            self.team_goal = TeamGoal.UNKNOWN

    def add_transcript(self, text: str, limit: int = 40) -> None:
        text = text.strip()
        if not text:
            return
        self.last_transcripts.append(text)
        if len(self.last_transcripts) > limit:
            self.last_transcripts = self.last_transcripts[-limit:]

    def summary_for_prompt(self) -> str:
        players = ", ".join(sorted(self.alive)) or "(unknown)"
        recent = "\n".join(f"- {t}" for t in self.last_transcripts[-12:]) or "- (none)"
        notes = "\n".join(f"- {n}" for n in self.private_notes[-10:]) or "- (none)"
        return (
            f"Phase: {self.phase.value}\n"
            f"Day: {self.day_number}\n"
            f"Script: {self.script_name}\n"
            f"My name: {self.my_name}\n"
            f"My role: {self.my_role or 'unknown'}\n"
            f"My alignment: {self.my_alignment}\n"
            f"Bluff role: {self.bluff_role or 'n/a'}\n"
            f"Team goal: {self.team_goal.value}\n"
            f"Hand raised: {self.hand_raised}\n"
            f"Called on: {self.called_on}\n"
            f"Awaiting night response: {self.awaiting_night_response}\n"
            f"Private chat with: {self.in_private_chat_with or 'none'}\n"
            f"Alive players: {players}\n"
            f"Recent speech transcripts:\n{recent}\n"
            f"Private notes:\n{notes}\n"
        )

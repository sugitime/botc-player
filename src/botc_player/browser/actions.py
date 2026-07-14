"""Translate AgentDecision into botc.app UI actions."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from botc_player.agent.brain import AgentDecision
    from botc_player.agent.game_state import GameState
    from botc_player.browser.botc_client import BotcClient

logger = logging.getLogger(__name__)


# Never execute these — leaving or switching lobbies is forbidden.
_FORBIDDEN_UI_ACTIONS = frozenset(
    {
        "leave",
        "exit",
        "quit",
        "disconnect",
        "leave_game",
        "leave_lobby",
        "leave_session",
        "join",
        "join_game",
        "join_lobby",
        "join_another",
        "new_game",
        "find_game",
        "home",
        "spectate",
    }
)


class ActionExecutor:
    def __init__(self, client: "BotcClient", state: "GameState"):
        self.client = client
        self.state = state

    def apply(self, decision: "AgentDecision") -> list[str]:
        if not self.client.connected:
            logger.debug("Browser not connected; skipping UI actions")
            return []

        # Stay in the locked lobby before any UI work
        if getattr(self.client, "lobby_locked", False):
            self.client.enforce_lobby_lock()

        done: list[str] = []
        if decision.raise_hand:
            if self.client.raise_hand():
                self.state.hand_raised = True
                done.append("raise_hand")
        if decision.lower_hand:
            if self.client.lower_hand():
                self.state.hand_raised = False
                self.state.called_on = False
                done.append("lower_hand")

        if decision.vote:
            if self.client.vote_for(str(decision.vote)):
                self.state.pending_vote_target = str(decision.vote)
                done.append(f"vote:{decision.vote}")

        if decision.night_action:
            player = _extract_player(decision.night_action)
            if player and self.client.select_player(player):
                done.append(f"select:{player}")
            if self.client.confirm():
                done.append("confirm")
                self.state.awaiting_night_response = False

        for action in decision.ui_actions or []:
            a = action.lower().strip().replace(" ", "_").replace("-", "_")
            if a in _FORBIDDEN_UI_ACTIONS or "leave" in a or "join" in a:
                logger.error("Blocked ui_action %r — never leave or join another lobby", action)
                continue
            if a in ("confirm", "dismiss_ping"):
                if self.client.confirm():
                    done.append(a)
                    self.state.awaiting_night_response = False
            elif a in ("mute", "unmute"):
                if self.client.mute_toggle():
                    done.append(a)
            elif a == "open_vote":
                # best effort
                if self.client._click_first(  # noqa: SLF001
                    [("role", "button:Nominate"), ("text", r"nominate")]
                ):
                    done.append(a)
        return done


def _extract_player(night_action: str) -> str | None:
    # "select Alice" / "target Bob" / bare name
    m = re.search(r"(?:select|target|choose|pick)\s+([A-Za-z0-9_\- ]+)", night_action, re.I)
    if m:
        return m.group(1).strip()
    parts = night_action.strip().split()
    if len(parts) == 1:
        return parts[0]
    return None

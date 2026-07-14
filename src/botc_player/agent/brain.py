"""LLM decision brain powered by SpaceXAI (xAI Grok)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from openai import OpenAI

from botc_player.agent.game_state import GamePhase, GameState
from botc_player.agent.prompts import build_decision_prompt, build_system_prompt
from botc_player.config import Settings
from botc_player.knowledge.roles import alignment_for_role
from botc_player.knowledge.strategy import may_speak_now, should_raise_hand

logger = logging.getLogger(__name__)


@dataclass
class AgentDecision:
    thought: str = ""
    update_notes: list[str] | None = None
    phase_guess: Optional[str] = None
    raise_hand: bool = False
    lower_hand: bool = False
    speak: bool = False
    speech: str = ""
    vote: Optional[str] = None
    night_action: Optional[str] = None
    ui_actions: list[str] | None = None
    set_role: Optional[str] = None
    set_alignment: Optional[str] = None
    set_bluff: Optional[str] = None
    raw: dict[str, Any] | None = None


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


class AgentBrain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.require_api_key(),
            base_url=settings.xai_base_url,
        )
        self.system_prompt = build_system_prompt()
        self.state = GameState(my_name=settings.agent_player_name)
        self._api_cooldown_until = 0.0
        self._last_api_error: str | None = None

    def decide(
        self,
        event: str,
        someone_speaking: bool = False,
        silence_seconds: float = 5.0,
    ) -> AgentDecision:
        import time as _time

        user_prompt = build_decision_prompt(
            self.state, event, someone_speaking, silence_seconds
        )
        logger.debug("Brain event: %s", event[:200])
        now = _time.time()
        if now < self._api_cooldown_until:
            data = self._fallback(event, someone_speaking, silence_seconds)
            data["thought"] = (
                f"API cooldown ({self._last_api_error or 'error'}); using fallback"
            )
        else:
            try:
                resp = self.client.chat.completions.create(
                    model=self.settings.xai_model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.5,
                )
                content = resp.choices[0].message.content or "{}"
                data = _extract_json(content)
                self._last_api_error = None
            except Exception as e:
                msg = str(e)
                self._last_api_error = msg[:160]
                # Back off hard on billing/auth failures to avoid log spam
                if "403" in msg or "401" in msg or "credits" in msg.lower() or "permission" in msg.lower():
                    self._api_cooldown_until = now + 120.0
                    logger.error(
                        "xAI API denied (%s). Cooling down 120s. "
                        "Add credits at https://console.x.ai if needed.",
                        self._last_api_error,
                    )
                else:
                    self._api_cooldown_until = now + 15.0
                    logger.exception("Brain decision failed; using safe fallback")
                data = self._fallback(event, someone_speaking, silence_seconds)

        decision = AgentDecision(
            thought=str(data.get("thought") or ""),
            update_notes=list(data.get("update_notes") or []),
            phase_guess=data.get("phase_guess"),
            raise_hand=bool(data.get("raise_hand")),
            lower_hand=bool(data.get("lower_hand")),
            speak=bool(data.get("speak")),
            speech=str(data.get("speech") or "").strip(),
            vote=data.get("vote"),
            night_action=data.get("night_action"),
            ui_actions=list(data.get("ui_actions") or []),
            set_role=data.get("set_role"),
            set_alignment=data.get("set_alignment"),
            set_bluff=data.get("set_bluff"),
            raw=data,
        )
        self._apply_meta(decision)
        decision = self._enforce_etiquette(decision, someone_speaking, silence_seconds)
        return decision

    def _apply_meta(self, decision: AgentDecision) -> None:
        if decision.phase_guess:
            try:
                self.state.phase = GamePhase(decision.phase_guess)
            except ValueError:
                pass
        if decision.update_notes:
            self.state.private_notes.extend(decision.update_notes)
        if decision.set_role:
            alignment = decision.set_alignment
            if not alignment:
                alignment = alignment_for_role(decision.set_role).value
            self.state.set_my_role(decision.set_role, alignment)
        elif decision.set_alignment:
            self.state.my_alignment = decision.set_alignment
            if decision.set_alignment == "evil":
                from botc_player.agent.game_state import TeamGoal

                self.state.team_goal = TeamGoal.EVIL_WIN
            elif decision.set_alignment == "good":
                from botc_player.agent.game_state import TeamGoal

                self.state.team_goal = TeamGoal.GOOD_WIN
        if decision.set_bluff:
            self.state.bluff_role = decision.set_bluff

    def _enforce_etiquette(
        self,
        decision: AgentDecision,
        someone_speaking: bool,
        silence_seconds: float,
    ) -> AgentDecision:
        # Hard politeness gate — but don't mute replies when we were just called on
        # or when the user finished speaking (silence after their utterance).
        if decision.speak and not may_speak_now(
            self.state, someone_speaking, silence_seconds
        ):
            # If they just finished (some silence) and we have a reply, allow it
            if self.state.called_on and silence_seconds >= 0.25 and not someone_speaking:
                logger.info("Allowing speech (called_on + silence after other speaker)")
            else:
                logger.info("Blocking speech (etiquette gate). Suggest raise_hand instead.")
                decision.speak = False
                if should_raise_hand(self.state, someone_speaking):
                    decision.raise_hand = True
                if decision.speech:
                    self.state.extra["queued_speech"] = decision.speech
                decision.speech = ""

        if decision.raise_hand and self.state.hand_raised:
            decision.raise_hand = False
        if decision.lower_hand and not self.state.hand_raised:
            decision.lower_hand = False

        # Cap speech length for public
        if decision.speak and decision.speech and self.state.phase.value.startswith("day"):
            words = decision.speech.split()
            if len(words) > 90:
                decision.speech = " ".join(words[:90]) + "…"
        return decision

    def _fallback(
        self, event: str, someone_speaking: bool, silence_seconds: float
    ) -> dict[str, Any]:
        lower = event.lower()
        if "called on" in lower or "your turn" in lower:
            speech = self.state.extra.pop("queued_speech", None) or (
                "Thanks. I'll keep it brief — still gathering info and happy to share more after others."
            )
            return {
                "thought": "fallback called-on",
                "speak": True,
                "speech": speech,
                "raise_hand": False,
            }
        # Always answer when we actually heard someone (works without xAI credits)
        if lower.startswith("speech heard") or "speech heard:" in lower:
            heard = event.split(":", 1)[-1].strip() if ":" in event else ""
            if heard.startswith("[heard speech"):
                speech = (
                    "Rawr! I heard you. This is G A I y Kevin the dinosaur. "
                    "I'm listening — say that again and I'll try to help."
                )
            else:
                snippet = heard[:80] if heard else "that"
                speech = (
                    f"Hey, I caught that — {snippet}. "
                    "I'm here in the lobby as the dinosaur. What's up?"
                )
            return {
                "thought": "fallback reply to heard speech",
                "speak": True,
                "speech": speech,
                "raise_hand": False,
                "phase_guess": "private_chat",
            }
        if "night" in lower or "storyteller" in lower or "ping" in lower:
            return {
                "thought": "fallback night ping",
                "speak": False,
                "speech": "",
                "ui_actions": ["confirm"],
                "phase_guess": "night",
            }
        if should_raise_hand(self.state, someone_speaking):
            return {
                "thought": "fallback raise hand",
                "raise_hand": True,
                "speak": False,
                "speech": "",
                "phase_guess": "day_discussion",
            }
        return {
            "thought": "fallback idle listen",
            "speak": False,
            "speech": "",
        }

    def note_transcript(self, text: str) -> None:
        self.state.add_transcript(text)

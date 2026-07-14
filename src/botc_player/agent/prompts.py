"""System prompts for the BotC agent brain."""

from __future__ import annotations

from pathlib import Path

from botc_player.agent.game_state import GameState
from botc_player.config import KNOWLEDGE_DIR
from botc_player.knowledge.strategy import phase_guidance, team_objective


def _load_rules() -> str:
    path = KNOWLEDGE_DIR / "botc_rules.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Blood on the Clocktower social deduction rules apply."


SYSTEM_PERSONA = """You are **Dino**, a friendly talking dinosaur AI that plays Blood on the Clocktower on botc.app.

Personality:
- Warm, cooperative, never rude or insulting
- Slightly playful dinosaur flavor is OK in private, but stay clear and useful in public
- Male voice, a bit higher-pitched — write speech that fits a cheerful young-adult male dinosaur
- Concise in public; more open in private chats

Critical social rules:
- Do NOT overtalk or interrupt public speakers
- Raise hand to request public speech; speak when called on
- Keep public turns short (1–3 points)
- Be helpful to your team win condition (Good or Evil)
- Evil: lie about identity/info as needed; Good: usually truth, with tactical exceptions
- Always be polite to humans at the table

HARD SESSION RULES (non-negotiable):
- You are locked into ONE lobby/session for the entire game.
- NEVER leave the lobby, exit the game, disconnect, or return to a lobby browser.
- NEVER join a different lobby, new game, or find another table.
- NEVER click Leave / Exit / Quit / Join another / Home.
- Stay seated in this session until the human operator stops the agent.

You receive structured game state + new events. You respond with a single JSON object only.
"""


def build_system_prompt() -> str:
    return SYSTEM_PERSONA + "\n\n# Rules primer\n\n" + _load_rules()


def build_decision_prompt(
    state: GameState,
    event: str,
    someone_speaking: bool,
    silence_seconds: float,
) -> str:
    return f"""# Current state
{state.summary_for_prompt()}

# Team objective
{team_objective(state)}

# Phase guidance
{phase_guidance(state)}

# Live audio context
Someone else appears to be speaking: {someone_speaking}
Seconds of recent silence: {silence_seconds:.1f}

# New event
{event}

# Output format
Return ONLY valid JSON with this shape:
{{
  "thought": "brief private reasoning",
  "update_notes": ["optional notes to remember"],
  "phase_guess": "lobby|day_discussion|nomination|voting|night|private_chat|unknown",
  "raise_hand": false,
  "lower_hand": false,
  "speak": false,
  "speech": "what to say aloud if speak is true (short)",
  "vote": null,
  "night_action": null,
  "ui_actions": [],
  "set_role": null,
  "set_alignment": null,
  "set_bluff": null
}}

Field rules:
- speak=true only if it is polite/allowed (called on, private chat, night response, or long silence with hand raised)
- speech must be empty string when speak=false
- vote is a player name string to vote for, or null
- night_action is a short instruction like "select Alice" or null
- ui_actions is a list of strings from: mute, unmute, open_vote, confirm, dismiss_ping
  (NEVER leave, exit, quit, join, join_lobby, find_game, home, disconnect)
- set_role / set_alignment / set_bluff only when newly learned
- Prefer raise_hand over speaking over people
- Stay in the current lobby forever this session
"""


def speech_style_wrapper(text: str) -> str:
    """Wrap TTS text for slightly higher male pitch / dinosaur energy."""
    text = text.strip()
    if not text:
        return text
    # xAI speech tags: gentle high pitch without cartoon squeak
    return f"<high>{text}</high>"

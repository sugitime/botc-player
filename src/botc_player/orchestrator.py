"""Main agent loop: listen → think → act → speak."""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from typing import Callable, Optional

from botc_player.agent.brain import AgentBrain, AgentDecision
from botc_player.agent.etiquette import ConversationMonitor
from botc_player.audio.stt import SpeechListener
from botc_player.audio.tts import TextToSpeech
from botc_player.browser.actions import ActionExecutor
from botc_player.browser.botc_client import BotcClient
from botc_player.config import Settings
from botc_player.vision.face import DinosaurFace
from botc_player.vision.frame_server import FrameServer
from botc_player.vision.virtual_cam import VirtualCamera

logger = logging.getLogger(__name__)

# Voice commands handled immediately (not sent through full game brain first).
_TAKE_SEAT_RE = re.compile(
    r"\b("
    r"ai[,.]?\s*take\s+a\s+seat"
    r"|take\s+a\s+seat"
    r"|claim\s+(a\s+)?seat"
    r"|sit\s+down"
    r"|grab\s+(a\s+)?seat"
    r")\b",
    re.I,
)


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.brain = AgentBrain(settings)
        self.face = DinosaurFace(settings)
        self.cam = VirtualCamera(settings, self.face)
        self.frame_server = FrameServer(self.face)
        self.tts = TextToSpeech(settings)
        self.browser = BotcClient(
            settings.botc_url,
            fake_video_path=settings.fake_video_path if settings.in_docker else None,
            face=self.face,
        )
        self.actions = ActionExecutor(self.browser, self.brain.state)
        self.monitor = ConversationMonitor()
        self.events: queue.Queue[str] = queue.Queue()
        # UI commands drained on the Playwright owner thread (join loop)
        self.ui_commands: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self.listener: Optional[SpeechListener] = None
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_decision: Optional[Callable[[AgentDecision], None]] = None
        self.running = False
        self.seated: bool = False

        self.tts.on_speaking_changed = self._on_speaking_changed

    def log(self, msg: str) -> None:
        logger.info(msg)
        if self.on_log:
            self.on_log(msg)

    def _on_speaking_changed(self, active: bool) -> None:
        self.face.set_talking(active)
        self.monitor.mark_self_speaking(active)
        if self.listener:
            self.listener.set_paused(active)

    def start(
        self,
        *,
        start_browser: bool = False,
        start_listener: bool = True,
        start_camera: bool = True,
    ) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()

        if start_camera:
            self.cam.start()
            self.log(f"Face/camera backend: {self.cam.backend}")
            try:
                self.frame_server.start()
                self.log(f"Frame server: {self.frame_server.frame_url}")
            except Exception as e:
                self.log(f"Frame server failed (browser video inject may not work): {e}")

        if start_listener:
            self.listener = SpeechListener(
                self.settings,
                on_transcript=self._on_transcript,
                on_energy=self.monitor.observe_energy,
            )
            self.listener.start()
            self.log("Listening for speech…")

        if start_browser:
            try:
                self.browser.connect(headless=False)
                self.log("Browser connected to botc.app")
            except Exception as e:
                self.log(f"Browser failed to start: {e}")

        self._loop_thread = threading.Thread(target=self._loop, name="agent-loop", daemon=True)
        self._loop_thread.start()
        self.log("Agent loop started")

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        if self.listener:
            self.listener.stop()
        self.cam.stop()
        try:
            self.frame_server.stop()
        except Exception:
            pass
        self.browser.close()
        if self._loop_thread:
            self._loop_thread.join(timeout=3.0)
        self.log("Agent stopped")

    def inject_event(self, event: str) -> None:
        self.events.put(event)

    def request_ui(self, command: str) -> None:
        """Queue a browser UI action for the Playwright owner thread."""
        self.ui_commands.put(command)

    def process_ui_commands(self) -> None:
        """Run pending UI commands. Call only from the Playwright owner thread."""
        while True:
            try:
                cmd = self.ui_commands.get_nowait()
            except queue.Empty:
                break
            try:
                self._run_ui_command(cmd)
            except Exception:
                logger.exception("UI command failed: %s", cmd)

    def _run_ui_command(self, cmd: str) -> None:
        c = (cmd or "").strip().lower()
        if c in {"take_seat", "claim_seat", "sit"}:
            self.log("Voice command: taking an open seat…")
            seat = self.browser.claim_open_seat()
            if seat is not None:
                self.seated = True
                if seat == 0:
                    msg = "I claimed a seat. Rawr!"
                else:
                    msg = f"I sat down in seat {seat}. Ready to play!"
                self.log(f"Seated (seat={seat})")
                # Speak confirmation on a worker so we don't block the UI thread long
                self.tts.speak(msg, block=False)
                self.inject_event(f"You claimed seat {seat}. You are now seated at the table.")
            else:
                self.log("No open seat found to claim")
                self.tts.speak(
                    "I couldn't find an open seat that says click to claim.",
                    block=False,
                )
            return
        logger.warning("Unknown UI command: %s", cmd)

    @staticmethod
    def is_take_seat_command(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        # Ignore offline placeholder alone
        if t.startswith("[heard speech"):
            return False
        return bool(_TAKE_SEAT_RE.search(t))

    def _on_transcript(self, text: str) -> None:
        self.brain.note_transcript(text)
        lower = text.lower()

        # Immediate voice command: "AI, take a seat"
        if self.is_take_seat_command(text):
            self.log(f"Heard take-seat command: {text}")
            self.request_ui("take_seat")
            return

        # Heuristic phase / call cues from speech
        if any(
            k in lower
            for k in (
                "you can speak",
                "your turn",
                "go ahead",
                "dino",
                self.settings.agent_player_name.lower(),
            )
        ):
            if "hand" in lower or "speak" in lower or "turn" in lower or "go ahead" in lower:
                self.brain.state.called_on = True
        # Allow a spoken reply to conversational audio (etiquette gate uses called_on /
        # private_chat). Without this, day_discussion blocks all replies.
        from botc_player.agent.game_state import GamePhase

        if self.brain.state.phase in (
            GamePhase.UNKNOWN,
            GamePhase.LOBBY,
            GamePhase.PRIVATE_CHAT,
        ):
            self.brain.state.phase = GamePhase.PRIVATE_CHAT
            self.brain.state.called_on = True
        else:
            # Still permit a short reply after they finish talking
            self.brain.state.called_on = True
        self.events.put(f"Speech heard: {text}")

    def _loop(self) -> None:
        last_idle = 0.0
        while not self._stop.is_set():
            try:
                event = self.events.get(timeout=0.5)
            except queue.Empty:
                # Periodic soft tick so agent can raise hand / react to silence
                now = time.time()
                # Slow down when API is cooling down (billing/auth failures)
                interval = (
                    30.0 if getattr(self.brain, "_api_cooldown_until", 0) > now else 12.0
                )
                if now - last_idle > interval:
                    last_idle = now
                    event = "Periodic check: update whether to raise hand or stay quiet."
                else:
                    continue
            try:
                self._handle_event(event)
            except Exception:
                logger.exception("Error handling event: %s", event)

    def _handle_event(self, event: str) -> None:
        someone = self.monitor.someone_is_speaking()
        silence = self.monitor.silence_seconds()
        self.log(f"Event: {event[:120]}")
        decision = self.brain.decide(event, someone_speaking=someone, silence_seconds=silence)
        if self.on_decision:
            self.on_decision(decision)
        if decision.thought:
            self.log(f"Thought: {decision.thought[:200]}")

        applied = self.actions.apply(decision)
        if applied:
            self.log(f"UI actions: {', '.join(applied)}")

        if decision.speak and decision.speech:
            self.log(f"Speaking: {decision.speech}")
            self.brain.state.called_on = False
            self.brain.state.hand_raised = False
            self.tts.speak(decision.speech, block=True)

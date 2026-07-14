"""Desktop control panel for the BotC dinosaur agent."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from botc_player.audio.devices import format_device_table
from botc_player.config import Settings, get_settings
from botc_player.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class BotcPlayerApp(ctk.CTk):
    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or get_settings()
        self.orch = Orchestrator(self.settings)
        self.orch.on_log = self._append_log
        self.orch.on_decision = self._on_decision

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self.title("BotC Player — Dino Agent")
        self.geometry("920x720")
        self.minsize(800, 600)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        header = ctk.CTkLabel(
            self,
            text="🦖 Dino — Blood on the Clocktower Agent",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.pack(pady=(16, 8))

        sub = ctk.CTkLabel(
            self,
            text="Virtual face → Firefox webcam · TTS → virtual mic · STT listens · Grok plays BotC",
            font=ctk.CTkFont(size=13),
            text_color=("gray70", "gray70"),
        )
        sub.pack(pady=(0, 12))

        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=16, pady=8)

        self.btn_start = ctk.CTkButton(controls, text="Start Agent", command=self._start)
        self.btn_start.grid(row=0, column=0, padx=8, pady=10)

        self.btn_stop = ctk.CTkButton(
            controls, text="Stop", command=self._stop, state="disabled", fg_color="#663333"
        )
        self.btn_stop.grid(row=0, column=1, padx=8, pady=10)

        self.chk_browser = ctk.CTkCheckBox(controls, text="Open botc.app (Playwright)")
        self.chk_browser.grid(row=0, column=2, padx=8, pady=10)
        self.chk_browser.select()

        self.chk_listen = ctk.CTkCheckBox(controls, text="Listen (STT)")
        self.chk_listen.grid(row=0, column=3, padx=8, pady=10)
        self.chk_listen.select()

        # Manual overrides
        manual = ctk.CTkFrame(self)
        manual.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(manual, text="Manual / overrides", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(8, 4)
        )

        ctk.CTkButton(manual, text="Raise hand", command=self._raise_hand).grid(
            row=1, column=0, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Lower hand", command=self._lower_hand).grid(
            row=1, column=1, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="I'm called on", command=self._called_on).grid(
            row=1, column=2, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Night ping", command=self._night_ping).grid(
            row=1, column=3, padx=6, pady=8
        )

        ctk.CTkButton(manual, text="Say custom…", command=self._say_custom).grid(
            row=2, column=0, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Set role…", command=self._set_role).grid(
            row=2, column=1, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Phase: Day", command=lambda: self._set_phase("day_discussion")).grid(
            row=2, column=2, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Phase: Night", command=lambda: self._set_phase("night")).grid(
            row=2, column=3, padx=6, pady=8
        )

        ctk.CTkButton(manual, text="List audio devices", command=self._list_devices).grid(
            row=3, column=0, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Inject event…", command=self._inject).grid(
            row=3, column=1, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Private chat mode", command=self._private).grid(
            row=3, column=2, padx=6, pady=8
        )
        ctk.CTkButton(manual, text="Vote for…", command=self._vote).grid(
            row=3, column=3, padx=6, pady=8
        )

        # State panel
        state_frame = ctk.CTkFrame(self)
        state_frame.pack(fill="x", padx=16, pady=8)
        self.state_label = ctk.CTkLabel(
            state_frame,
            text="Status: idle",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=13),
        )
        self.state_label.pack(fill="x", padx=10, pady=10)

        # Log
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        ctk.CTkLabel(log_frame, text="Agent log", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )
        self.log_box = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Menlo", size=12))
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._append_log("Ready. Set XAI_API_KEY, configure virtual mic/cam, then Start Agent.")
        self._append_log(
            f"Voice={self.settings.xai_tts_voice} pitch=+{self.settings.tts_pitch_semitones} st | "
            f"model={self.settings.xai_model}"
        )

    def _append_log(self, msg: str) -> None:
        def _do() -> None:
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")

        try:
            self.after(0, _do)
        except Exception:
            pass

    def _on_decision(self, decision) -> None:  # noqa: ANN001
        def _do() -> None:
            st = self.orch.brain.state
            self.state_label.configure(
                text=(
                    f"Phase={st.phase.value} | Role={st.my_role or '?'} | "
                    f"Align={st.my_alignment} | Hand={st.hand_raised} | "
                    f"CalledOn={st.called_on} | Speak={decision.speak}"
                )
            )

        self.after(0, _do)

    def _start(self) -> None:
        if not self.settings.xai_api_key:
            messagebox.showerror(
                "Missing API key",
                "Set XAI_API_KEY in a .env file (see .env.example).",
            )
            return
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        def run() -> None:
            try:
                self.orch.start(
                    start_browser=bool(self.chk_browser.get()),
                    start_listener=bool(self.chk_listen.get()),
                    start_camera=True,
                )
            except Exception as e:
                self._append_log(f"Start failed: {e}")
                logger.exception("start failed")

        threading.Thread(target=run, daemon=True).start()

    def _stop(self) -> None:
        def run() -> None:
            self.orch.stop()
            self.after(0, lambda: self.btn_start.configure(state="normal"))
            self.after(0, lambda: self.btn_stop.configure(state="disabled"))

        threading.Thread(target=run, daemon=True).start()

    def _raise_hand(self) -> None:
        self.orch.brain.state.hand_raised = True
        if self.orch.browser.connected:
            self.orch.browser.raise_hand()
        self.orch.inject_event("Operator: raise hand requested.")
        self._append_log("Manual raise hand")

    def _lower_hand(self) -> None:
        self.orch.brain.state.hand_raised = False
        self.orch.brain.state.called_on = False
        if self.orch.browser.connected:
            self.orch.browser.lower_hand()
        self._append_log("Manual lower hand")

    def _called_on(self) -> None:
        self.orch.brain.state.called_on = True
        self.orch.inject_event("You were called on to speak. It is your turn. Speak briefly.")
        self._append_log("Marked called on")

    def _night_ping(self) -> None:
        self.orch.brain.state.awaiting_night_response = True
        from botc_player.agent.game_state import GamePhase

        self.orch.brain.state.phase = GamePhase.NIGHT
        self.orch.inject_event(
            "Night ping from Storyteller: you are woken. Respond with night_action / UI confirm as needed."
        )

    def _set_phase(self, phase: str) -> None:
        from botc_player.agent.game_state import GamePhase

        try:
            self.orch.brain.state.phase = GamePhase(phase)
            self._append_log(f"Phase set to {phase}")
            self.orch.inject_event(f"Operator set phase to {phase}.")
        except ValueError:
            pass

    def _private(self) -> None:
        from botc_player.agent.game_state import GamePhase

        self.orch.brain.state.phase = GamePhase.PRIVATE_CHAT
        self.orch.inject_event("Entered private voice chat. You may speak more freely and coordinate.")

    def _say_custom(self) -> None:
        dialog = ctk.CTkInputDialog(text="What should Dino say?", title="Custom speech")
        text = dialog.get_input()
        if text:
            threading.Thread(target=lambda: self.orch.tts.speak(text), daemon=True).start()

    def _set_role(self) -> None:
        dialog = ctk.CTkInputDialog(
            text="Role name (e.g. Empath) — optional ,good or ,evil",
            title="Set role",
        )
        text = dialog.get_input()
        if not text:
            return
        parts = [p.strip() for p in text.split(",")]
        role = parts[0]
        alignment = parts[1] if len(parts) > 1 else None
        if not alignment:
            from botc_player.knowledge.roles import alignment_for_role

            alignment = alignment_for_role(role).value
        self.orch.brain.state.set_my_role(role, alignment)
        self._append_log(f"Role set: {role} ({alignment})")
        self.orch.inject_event(f"You learned your role is {role} ({alignment}). Plan accordingly.")

    def _vote(self) -> None:
        dialog = ctk.CTkInputDialog(text="Player name to vote for", title="Vote")
        name = dialog.get_input()
        if name and self.orch.browser.connected:
            self.orch.browser.vote_for(name)
            self._append_log(f"Voted for {name}")

    def _inject(self) -> None:
        dialog = ctk.CTkInputDialog(text="Event text for the agent brain", title="Inject event")
        text = dialog.get_input()
        if text:
            self.orch.inject_event(text)

    def _list_devices(self) -> None:
        table = format_device_table()
        self._append_log("Audio devices:\n" + table)
        messagebox.showinfo("Audio devices", table[:4000])

    def _on_close(self) -> None:
        try:
            self.orch.stop()
        except Exception:
            pass
        self.destroy()


def run_app() -> None:
    app = BotcPlayerApp()
    app.mainloop()

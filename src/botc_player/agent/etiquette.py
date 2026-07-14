"""Public speaking / politeness gates."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ConversationMonitor:
    """Tracks whether others are speaking and recent silence."""

    speaking_threshold: float = 0.012  # RMS energy ~ speech-ish
    silence_required_for_gap: float = 0.8
    last_energy: float = 0.0
    last_voice_ts: float = field(default_factory=time.monotonic)
    self_speaking: bool = False

    def observe_energy(self, rms: float) -> None:
        now = time.monotonic()
        self.last_energy = rms
        if rms >= self.speaking_threshold and not self.self_speaking:
            self.last_voice_ts = now

    def someone_is_speaking(self) -> bool:
        if self.self_speaking:
            return False
        return self.last_energy >= self.speaking_threshold

    def silence_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.last_voice_ts)

    def mark_self_speaking(self, active: bool) -> None:
        self.self_speaking = active
        if active:
            self.last_voice_ts = time.monotonic()

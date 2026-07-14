"""Text-to-speech: xAI TTS with local espeak fallback, play to virtual mic."""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import requests

from botc_player.agent.prompts import speech_style_wrapper
from botc_player.audio.devices import find_device
from botc_player.audio.pitch import pitch_shift_pcm
from botc_player.config import Settings

logger = logging.getLogger(__name__)


class TextToSpeech:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._speaking = False
        self.on_speaking_changed: Optional[Callable[[bool], None]] = None
        self._xai_ok = True  # flipped False after billing/auth failures

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def synthesize(self, text: str) -> bytes:
        styled = speech_style_wrapper(text)
        headers = {
            "Authorization": f"Bearer {self.settings.require_api_key()}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": styled,
            "voice_id": self.settings.xai_tts_voice,
            "language": "en",
            "output_format": {
                "codec": "wav",
                "sample_rate": self.settings.sample_rate,
            },
            "speed": 1.05,
        }
        resp = requests.post(
            f"{self.settings.xai_base_url}/tts",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code in (401, 403):
            self._xai_ok = False
        resp.raise_for_status()
        return resp.content

    def _synthesize_espeak(self, text: str) -> tuple[np.ndarray, int]:
        """Offline TTS via espeak-ng → wav → float mono (slightly high pitch)."""
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak:
            raise RuntimeError("espeak-ng not installed for offline TTS")

        # Higher pitch for young-male vibe (-p 50–99, default 50)
        pitch = min(99, 55 + int(self.settings.tts_pitch_semitones * 4))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = Path(f.name)
        try:
            subprocess.run(
                [
                    espeak,
                    "-w",
                    str(path),
                    "-s",
                    "145",
                    "-p",
                    str(pitch),
                    "-v",
                    "en+m3",
                    text,
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            import soundfile as sf

            data, sr = sf.read(str(path), dtype="float32", always_2d=False)
            if getattr(data, "ndim", 1) > 1:
                data = data.mean(axis=1)
            return np.asarray(data, dtype=np.float32), int(sr)
        finally:
            path.unlink(missing_ok=True)

    def _wav_to_float_mono(self, wav_bytes: bytes) -> tuple[np.ndarray, int]:
        import soundfile as sf

        data, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        return np.asarray(data, dtype=np.float32), int(sr)

    def speak(self, text: str, *, block: bool = True) -> None:
        text = (text or "").strip()
        if not text:
            return

        def _run() -> None:
            with self._lock:
                self._set_speaking(True)
                try:
                    samples: np.ndarray
                    sr: int
                    used = "xai"
                    try:
                        if self._xai_ok and self.settings.xai_api_key:
                            wav = self.synthesize(text)
                            samples, sr = self._wav_to_float_mono(wav)
                            if self.settings.tts_pitch_semitones:
                                samples = pitch_shift_pcm(
                                    samples, sr, self.settings.tts_pitch_semitones
                                )
                        else:
                            raise RuntimeError("xAI TTS disabled (no key or prior 403)")
                    except Exception as e:
                        logger.warning("xAI TTS unavailable (%s) — using espeak", e)
                        used = "espeak"
                        samples, sr = self._synthesize_espeak(text)
                    self._play(samples, sr)
                    logger.info("Spoke via %s: %s", used, text[:80])
                except Exception:
                    logger.exception("TTS speak failed completely")
                finally:
                    self._set_speaking(False)

        if block:
            _run()
        else:
            threading.Thread(target=_run, name="tts-speak", daemon=True).start()

    def _set_speaking(self, active: bool) -> None:
        self._speaking = active
        if self.on_speaking_changed:
            try:
                self.on_speaking_changed(active)
            except Exception:
                logger.exception("on_speaking_changed failed")

    def _play(self, samples: np.ndarray, sample_rate: int) -> None:
        try:
            import sounddevice as sd
        except ImportError as e:
            raise RuntimeError("sounddevice is required for TTS playback") from e

        device = find_device(self.settings.audio_output_device, want_output=True)
        # Prefer Pulse VirtualMic by name substring if configured device missing
        if device is None:
            device = find_device("VirtualMic", want_output=True)

        logger.info(
            "Playing TTS (%.1fs) on device %s",
            len(samples) / max(sample_rate, 1),
            device if device is not None else "default",
        )
        # Also try paplay for Pulse when in Docker (more reliable to VirtualMic)
        if self._try_paplay(samples, sample_rate):
            return
        sd.play(samples, samplerate=sample_rate, device=device)
        sd.wait()

    def _try_paplay(self, samples: np.ndarray, sample_rate: int) -> bool:
        if not shutil.which("paplay") and not shutil.which("pacat"):
            return False
        try:
            import soundfile as sf

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                path = Path(f.name)
            try:
                sf.write(str(path), samples, sample_rate)
                env = {
                    **os.environ,
                    "PULSE_SERVER": os.environ.get(
                        "PULSE_SERVER", "unix:/tmp/pulse-socket"
                    ),
                }
                # Play into VirtualMic sink so Chromium mic (BotC_Agent_Mic) hears us
                r = subprocess.run(
                    ["paplay", "--device=VirtualMic", str(path)],
                    capture_output=True,
                    timeout=120,
                    env=env,
                )
                if r.returncode == 0:
                    return True
                logger.debug(
                    "paplay failed: %s",
                    r.stderr[:200] if r.stderr else r.returncode,
                )
            finally:
                path.unlink(missing_ok=True)
        except Exception as e:
            logger.debug("paplay path failed: %s", e)
        return False

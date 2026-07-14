"""Speech-to-text: capture game audio loopback; xAI STT with offline fallback.

In Docker, PortAudio only sees the generic "pulse" device, so we record with
`parec --device=GameOut.monitor` so we hear botc.app (not our own TTS mic).
"""

from __future__ import annotations

import io
import logging
import os
import queue
import subprocess
import threading
from typing import Callable, Optional

import numpy as np
import requests

from botc_player.audio.devices import find_device, list_devices
from botc_player.config import Settings

logger = logging.getLogger(__name__)


class SpeechListener:
    """Records short windows of audio when energy is high, then STT."""

    def __init__(
        self,
        settings: Settings,
        on_transcript: Callable[[str], None],
        on_energy: Optional[Callable[[float], None]] = None,
    ):
        self.settings = settings
        self.on_transcript = on_transcript
        self.on_energy = on_energy
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._paused = False
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=80)
        self._xai_ok = True
        self._utterance_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="stt-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def _pulse_source_name(self) -> str:
        """Which Pulse source carries botc.app / table audio."""
        # Prefer configured name, then GameOut monitor
        for name in (
            "GameOut.monitor",
            "GameOut",
            "BotC_Game_Output.monitor",
        ):
            return name if name.endswith(".monitor") or name == "GameOut" else name
        return "GameOut.monitor"

    def _run_parec(self, sample_rate: int) -> None:
        """Capture from a named Pulse source via parec (works when PortAudio can't see sinks)."""
        source = "GameOut.monitor"
        # Allow override from settings substring
        cfg = (self.settings.audio_input_device or "").strip()
        if cfg:
            if "monitor" in cfg.lower() or cfg.endswith("GameOut"):
                source = cfg if "monitor" in cfg else f"{cfg}.monitor"
            elif cfg not in ("pulse", "default"):
                source = f"{cfg}.monitor" if not cfg.endswith(".monitor") else cfg

        env = {
            **os.environ,
            "PULSE_SERVER": os.environ.get("PULSE_SERVER", "unix:/tmp/pulse-socket"),
        }
        cmd = [
            "parec",
            f"--device={source}",
            f"--rate={sample_rate}",
            "--channels=1",
            "--format=s16le",
            "--latency-msec=50",
        ]
        logger.info("STT parec: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            logger.error("parec not found — install pulseaudio-utils")
            return

        bytes_per_block = int(sample_rate * 0.1) * 2  # 100ms s16le mono
        assert proc.stdout is not None
        try:
            while not self._stop.is_set():
                raw = proc.stdout.read(bytes_per_block)
                if not raw:
                    err = (proc.stderr.read() if proc.stderr else b"")[:300]
                    logger.error("parec ended early: %s", err)
                    break
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                try:
                    self._audio_q.put_nowait(audio)
                except queue.Full:
                    pass
        finally:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except Exception:
                pass

    def _run_sounddevice(self, sample_rate: int) -> None:
        import sounddevice as sd

        device = find_device(self.settings.audio_input_device, want_input=True)
        if device is None:
            device = find_device("GameOut", want_input=True)
        # Fall back to pulse/default — caller should prefer parec in Docker
        block = int(sample_rate * 0.1)

        def callback(indata, frames, time_info, status):  # noqa: ANN001
            if status:
                logger.debug("Input status: %s", status)
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            try:
                self._audio_q.put_nowait(mono)
            except queue.Full:
                pass

        logger.info("STT sounddevice device=%s @ %s", device, sample_rate)
        with sd.InputStream(
            device=device,
            channels=1,
            samplerate=sample_rate,
            blocksize=block,
            dtype="float32",
            callback=callback,
        ):
            while not self._stop.is_set():
                self._stop.wait(0.2)

    def _run(self) -> None:
        try:
            import soundfile as sf
        except ImportError:
            logger.error("soundfile required for STT listener")
            return

        sample_rate = 16000  # good for speech; lighter STT
        # Docker / Pulse: PortAudio only exposes "pulse"/"default" — use parec
        use_parec = (
            os.environ.get("BOTC_IN_DOCKER", "").lower() in {"1", "true", "yes"}
            or os.path.exists("/.dockerenv")
            or (
                len(list_devices()) <= 2
                and all("pulse" in d["name"].lower() or d["name"] == "default" for d in list_devices())
            )
        )

        capture = threading.Thread(
            target=self._run_parec if use_parec else self._run_sounddevice,
            args=(sample_rate,),
            name="stt-capture",
            daemon=True,
        )
        capture.start()
        logger.info("STT capture mode=%s", "parec" if use_parec else "sounddevice")

        ring: list[np.ndarray] = []
        voiced = False
        silence_blocks = 0
        max_seconds = 12.0
        energy_threshold = 0.006

        while not self._stop.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk)) + 1e-12))
            if self.on_energy:
                self.on_energy(rms)
            if self._paused:
                ring.clear()
                voiced = False
                continue

            if rms > energy_threshold:
                voiced = True
                silence_blocks = 0
                ring.append(chunk)
            elif voiced:
                silence_blocks += 1
                ring.append(chunk)
                if silence_blocks >= 8:  # ~0.8s silence
                    audio = np.concatenate(ring)
                    ring.clear()
                    voiced = False
                    silence_blocks = 0
                    if len(audio) / sample_rate >= 0.35:
                        self._transcribe(audio, sample_rate, sf)
            total = sum(len(c) for c in ring) / sample_rate
            if total > max_seconds:
                audio = np.concatenate(ring)
                ring.clear()
                voiced = False
                self._transcribe(audio, sample_rate, sf)

        capture.join(timeout=1.0)

    def _transcribe(self, audio: np.ndarray, sample_rate: int, sf) -> None:  # noqa: ANN001
        self._utterance_count += 1
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(audio)) + 1e-12))
        logger.info(
            "Utterance #%s (%.1fs peak=%.3f rms=%.3f) — transcribing…",
            self._utterance_count,
            len(audio) / max(sample_rate, 1),
            peak,
            rms,
        )

        text = ""
        if self._xai_ok and self.settings.xai_api_key:
            try:
                text = self._transcribe_xai(audio, sample_rate, sf)
            except Exception as e:
                msg = str(e)
                if "401" in msg or "403" in msg or "credits" in msg.lower():
                    self._xai_ok = False
                    logger.warning("xAI STT disabled after auth/billing error")
                else:
                    logger.warning("xAI STT failed: %s", e)

        if not text:
            text = f"[heard speech, {len(audio) / sample_rate:.1f}s]"
            logger.info("Offline STT fallback: %s", text)

        if text:
            logger.info("Heard: %s", text)
            try:
                self.on_transcript(text)
            except Exception:
                logger.exception("on_transcript failed")

    def _transcribe_xai(self, audio: np.ndarray, sample_rate: int, sf) -> str:  # noqa: ANN001
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV")
        buf.seek(0)
        headers = {"Authorization": f"Bearer {self.settings.require_api_key()}"}
        files = {"file": ("utterance.wav", buf, "audio/wav")}
        resp = requests.post(
            f"{self.settings.xai_base_url}/stt",
            headers=headers,
            files=files,
            timeout=60,
        )
        if resp.status_code in (401, 403):
            self._xai_ok = False
        resp.raise_for_status()
        data = resp.json()
        return (data.get("text") or data.get("transcript") or "").strip()

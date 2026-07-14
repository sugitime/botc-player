"""Animated dinosaur face frames for virtual webcam + preview."""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from botc_player.config import Settings

logger = logging.getLogger(__name__)


class MouthState(str, Enum):
    IDLE = "idle"
    MID = "mid"
    OPEN = "open"


class DinosaurFace:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.width = settings.face_width
        self.height = settings.face_height
        self._lock = threading.Lock()
        self._talking = False
        self._blink_until = 0.0
        self._phase = 0.0
        self._frames = {
            MouthState.IDLE: self._load(settings.dinosaur_idle),
            MouthState.MID: self._load(settings.dinosaur_talk_mid),
            MouthState.OPEN: self._load(settings.dinosaur_talk_open),
        }

    def _load(self, path: Path) -> np.ndarray:
        if not path.exists():
            logger.warning("Missing face asset %s — using solid color fallback", path)
            img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            img[:] = (90, 160, 90)
            cv2.putText(
                img,
                "DINO",
                (self.width // 3, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                2,
                (255, 255, 255),
                3,
            )
            return img
        raw = cv2.imread(str(path))
        if raw is None:
            raise RuntimeError(f"Failed to read image: {path}")
        return cv2.resize(raw, (self.width, self.height), interpolation=cv2.INTER_AREA)

    def set_talking(self, talking: bool) -> None:
        with self._lock:
            self._talking = talking

    def current_frame(self) -> np.ndarray:
        with self._lock:
            talking = self._talking
        now = time.time()
        if talking:
            # mouth flap
            self._phase += 0.35
            flap = np.sin(self._phase)
            state = MouthState.OPEN if flap > 0.2 else MouthState.MID if flap > -0.4 else MouthState.IDLE
        else:
            state = MouthState.IDLE
            # occasional blink darken
            if now > self._blink_until and np.random.random() < 0.01:
                self._blink_until = now + 0.12

        frame = self._frames[state].copy()
        if now < self._blink_until:
            # simple eyelid: darken upper third slightly
            h = frame.shape[0]
            frame[0 : h // 3] = (frame[0 : h // 3] * 0.55).astype(np.uint8)

        # subtle idle sway when not talking
        if not talking:
            offset = int(3 * np.sin(now * 1.3))
            M = np.float32([[1, 0, offset], [0, 1, 0]])
            frame = cv2.warpAffine(
                frame,
                M,
                (self.width, self.height),
                borderMode=cv2.BORDER_REPLICATE,
            )
        return frame

    def bgr_frame(self) -> np.ndarray:
        return self.current_frame()

    def rgb_frame(self) -> np.ndarray:
        return cv2.cvtColor(self.current_frame(), cv2.COLOR_BGR2RGB)

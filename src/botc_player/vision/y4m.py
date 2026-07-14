"""Write a looping Y4M clip of the dinosaur face for Chromium fake video capture."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def write_face_y4m(
    frames_bgr: list[np.ndarray],
    path: Path,
    *,
    fps: int = 15,
    repeats: int = 8,
) -> Path:
    """Write frames as Y4M (I420). Chromium can loop this via --use-file-for-fake-video-capture."""
    if not frames_bgr:
        raise ValueError("no frames")
    h, w = frames_bgr[0].shape[:2]
    # Y4M requires even dimensions
    w -= w % 2
    h -= h % 2
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    header = f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A0:0 C420jpeg\n".encode("ascii")
    with path.open("wb") as f:
        f.write(header)
        sequence = frames_bgr * max(1, repeats)
        for bgr in sequence:
            resized = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
            yuv = cv2.cvtColor(resized, cv2.COLOR_BGR2YUV_I420)
            f.write(b"FRAME\n")
            f.write(yuv.tobytes())
    logger.info("Wrote fake-webcam Y4M %s (%dx%d, %d frames)", path, w, h, len(sequence))
    return path

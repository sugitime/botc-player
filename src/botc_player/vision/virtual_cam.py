"""Stream dinosaur face to a virtual webcam (OBS / pyvirtualcam / Docker Y4M)."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from botc_player.config import Settings
from botc_player.vision.face import DinosaurFace, MouthState

logger = logging.getLogger(__name__)


class VirtualCamera:
    """Best-effort virtual camera.

    Backends (first that works):
    1. pyvirtualcam (OBS / v4l2loopback)
    2. Docker: write looping Y4M for Chromium --use-file-for-fake-video-capture
    3. Preview window only (OpenCV) — always available under Xvfb/noVNC
    """

    def __init__(self, settings: Settings, face: DinosaurFace):
        self.settings = settings
        self.face = face
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cam = None
        self.preview = True
        self.backend = "none"
        self.fake_video_path: Optional[Path] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._prepare_docker_fake_video()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="virtual-cam", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._close_cam()

    def _prepare_docker_fake_video(self) -> None:
        if not self.settings.in_docker:
            return
        try:
            from botc_player.vision.y4m import write_face_y4m

            frames = [
                self.face._frames[MouthState.IDLE],  # noqa: SLF001
                self.face._frames[MouthState.MID],  # noqa: SLF001
                self.face._frames[MouthState.OPEN],  # noqa: SLF001
                self.face._frames[MouthState.MID],  # noqa: SLF001
            ]
            out = Path(os.environ.get("BOTC_FAKE_VIDEO", "/tmp/botc_dino.y4m"))
            self.fake_video_path = write_face_y4m(
                frames, out, fps=self.settings.virtual_cam_fps, repeats=20
            )
            if self.backend == "none":
                self.backend = f"y4m:{self.fake_video_path}"
        except Exception:
            logger.exception("Failed to write Docker fake video Y4M")

    def _open_cam(self):
        # Prefer explicit v4l2 device from env (Linux + v4l2loopback)
        device = os.environ.get("BOTC_V4L2_DEVICE") or self.settings.v4l2_device
        try:
            import pyvirtualcam

            kwargs = {
                "width": self.settings.face_width,
                "height": self.settings.face_height,
                "fps": self.settings.virtual_cam_fps,
                "fmt": pyvirtualcam.PixelFormat.RGB,
            }
            if device:
                kwargs["device"] = device
            cam = pyvirtualcam.Camera(**kwargs)
            self.backend = f"pyvirtualcam:{cam.device}"
            logger.info("Virtual camera started: %s", self.backend)
            return cam
        except Exception as e:
            logger.warning(
                "Virtual camera unavailable (%s). "
                "Preview still runs; in Docker Chromium can use the Y4M fake capture file.",
                e,
            )
            if self.fake_video_path:
                self.backend = f"y4m:{self.fake_video_path}"
            else:
                self.backend = "preview-only"
            return None

    def _close_cam(self) -> None:
        if self._cam is not None:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None

    def _run(self) -> None:
        import cv2

        self._cam = self._open_cam()
        frame_time = 1.0 / max(1, self.settings.virtual_cam_fps)
        window = "BotC Agent — Dino Face (webcam feed)"
        if self.preview:
            try:
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, self.settings.face_width, self.settings.face_height)
            except Exception:
                logger.warning("OpenCV preview window unavailable")
                self.preview = False

        while not self._stop.is_set():
            t0 = time.time()
            bgr = self.face.bgr_frame()
            rgb = self.face.rgb_frame()
            if self._cam is not None:
                try:
                    self._cam.send(rgb)
                    self._cam.sleep_until_next_frame()
                except Exception:
                    logger.exception("Virtual cam send failed")
                    self._close_cam()
            if self.preview:
                try:
                    cv2.imshow(window, bgr)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                except Exception:
                    self.preview = False
            elapsed = time.time() - t0
            if self._cam is None:
                time.sleep(max(0.0, frame_time - elapsed))

        if self.preview:
            try:
                cv2.destroyWindow(window)
            except Exception:
                pass
        self._close_cam()

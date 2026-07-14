"""Tiny HTTP server that serves the latest dinosaur face JPEG for browser injection."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Optional

import cv2

if TYPE_CHECKING:
    from botc_player.vision.face import DinosaurFace

logger = logging.getLogger(__name__)


class FrameServer:
    def __init__(self, face: "DinosaurFace", host: str = "127.0.0.1", port: int = 9191):
        self.face = face
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def frame_url(self) -> str:
        return f"http://{self.host}:{self.port}/frame.jpg"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        face = self.face

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.split("?")[0] not in ("/frame.jpg", "/"):
                    self.send_error(404)
                    return
                ok, buf = cv2.imencode(".jpg", face.bgr_frame(), [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ok:
                    self.send_error(500)
                    return
                data = buf.tobytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):  # noqa: A003
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="frame-server", daemon=True)
        self._thread.start()
        logger.info("Face frame server at %s", self.frame_url)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

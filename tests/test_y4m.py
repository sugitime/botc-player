from pathlib import Path

import numpy as np

from botc_player.vision.y4m import write_face_y4m


def test_write_y4m(tmp_path: Path):
    frames = [
        np.zeros((64, 64, 3), dtype=np.uint8),
        np.full((64, 64, 3), 128, dtype=np.uint8),
    ]
    out = tmp_path / "dino.y4m"
    path = write_face_y4m(frames, out, fps=10, repeats=2)
    data = path.read_bytes()
    assert data.startswith(b"YUV4MPEG2")
    assert data.count(b"FRAME\n") == 4

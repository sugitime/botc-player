import numpy as np

from botc_player.audio.pitch import pitch_shift_pcm


def test_pitch_shift_same_length():
    sr = 24000
    t = np.linspace(0, 1, sr, dtype=np.float32)
    wave = 0.2 * np.sin(2 * np.pi * 220 * t)
    out = pitch_shift_pcm(wave, sr, 3.0)
    assert out.shape == wave.shape
    assert np.isfinite(out).all()


def test_pitch_shift_zero_noop():
    x = np.array([0.1, -0.2, 0.3], dtype=np.float32)
    out = pitch_shift_pcm(x, 24000, 0.0)
    assert np.allclose(out, x)

"""Simple pitch shifting for a slightly higher male voice."""

from __future__ import annotations

import numpy as np


def pitch_shift_pcm(
    samples: np.ndarray,
    sample_rate: int,
    semitones: float,
) -> np.ndarray:
    """Resample-based pitch shift (changes duration slightly — OK for short speech).

    Positive semitones => higher pitch. Avoids heavy deps (librosa).
    """
    if abs(semitones) < 0.01 or samples.size == 0:
        return samples

    mono = samples.astype(np.float32)
    if mono.ndim > 1:
        mono = mono.mean(axis=1)

    factor = 2.0 ** (semitones / 12.0)
    # Higher pitch: play faster then resample back conceptually by indexing denser
    x = np.arange(len(mono), dtype=np.float32)
    new_len = max(1, int(len(mono) / factor))
    xi = np.linspace(0, len(mono) - 1, new_len)
    shifted = np.interp(xi, x, mono).astype(np.float32)

    # Stretch duration back toward original with linear resample
    target_len = len(mono)
    yi = np.linspace(0, len(shifted) - 1, target_len)
    out = np.interp(yi, np.arange(len(shifted)), shifted).astype(np.float32)
    peak = np.max(np.abs(out)) if out.size else 0.0
    if peak > 1.0:
        out = out / peak
    return out

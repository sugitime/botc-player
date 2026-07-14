"""Audio device discovery helpers (BlackHole / virtual mics)."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def list_devices() -> list[dict[str, Any]]:
    try:
        import sounddevice as sd
    except ImportError:
        logger.warning("sounddevice not installed")
        return []
    devices = sd.query_devices()
    result = []
    for i, d in enumerate(devices):
        result.append(
            {
                "index": i,
                "name": d["name"],
                "max_input_channels": d["max_input_channels"],
                "max_output_channels": d["max_output_channels"],
                "default_samplerate": d["default_samplerate"],
            }
        )
    return result


def find_device(name_substr: str, *, want_input: bool = False, want_output: bool = False) -> Optional[int]:
    if not name_substr:
        return None
    needle = name_substr.lower()
    candidates: list[dict[str, Any]] = []
    for d in list_devices():
        name = d["name"].lower()
        if needle not in name:
            continue
        if want_input and d["max_input_channels"] < 1:
            continue
        if want_output and d["max_output_channels"] < 1:
            continue
        candidates.append(d)

    if not candidates:
        return None

    def score(d: dict[str, Any]) -> tuple[int, int, int]:
        name = d["name"].lower()
        # Prefer monitor sources when capturing a sink's output (PulseAudio)
        mon = 0 if (want_input and "monitor" in name) else 1
        exact = 0 if name == needle or name.startswith(needle + ".") or name.startswith(needle) else 1
        return (exact, mon, d["index"])

    candidates.sort(key=score)
    return candidates[0]["index"]


def format_device_table() -> str:
    rows = list_devices()
    if not rows:
        return "(no devices — install sounddevice / check permissions)"
    lines = ["idx | in | out | name", "----+----+-----+-----"]
    for d in rows:
        lines.append(
            f"{d['index']:>3} | {d['max_input_channels']:>2} | {d['max_output_channels']:>3} | {d['name']}"
        )
    return "\n".join(lines)

#!/usr/bin/env bash
# Create PulseAudio virtual devices for the BotC agent inside Docker.
#
# BotC_Agent_Mic  — Chromium microphone (hears TTS played into VirtualMic)
# VirtualMic      — sink that TTS / espeak play into
# GameOut         — Chromium speakers (game audio); STT can record GameOut.monitor
set -euo pipefail

export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"

echo "[audio] Waiting for PulseAudio at ${PULSE_SERVER}..."
for i in $(seq 1 50); do
  if pactl info >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! pactl info >/dev/null 2>&1; then
  echo "[audio] ERROR: PulseAudio not reachable" >&2
  exit 1
fi

existing_sinks="$(pactl list short sinks 2>/dev/null || true)"
existing_sources="$(pactl list short sources 2>/dev/null || true)"

if ! grep -q "VirtualMic" <<<"$existing_sinks"; then
  pactl load-module module-null-sink \
    sink_name=VirtualMic \
    sink_properties=device.description="BotC_Agent_Speaker_Loop" \
    rate=48000 \
    channels=2
  echo "[audio] Created sink VirtualMic"
else
  echo "[audio] Sink VirtualMic already exists"
fi

if ! grep -q "GameOut" <<<"$existing_sinks"; then
  pactl load-module module-null-sink \
    sink_name=GameOut \
    sink_properties=device.description="BotC_Game_Output" \
    rate=48000 \
    channels=2
  echo "[audio] Created sink GameOut"
else
  echo "[audio] Sink GameOut already exists"
fi

# Remap VirtualMic.monitor → a proper *source* with a clear mic label for Chromium
if ! grep -q "BotC_Agent_Mic" <<<"$existing_sources"; then
  pactl load-module module-remap-source \
    master=VirtualMic.monitor \
    source_name=BotC_Agent_Mic \
    source_properties=device.description="BotC_Agent_Mic" \
    || true
  echo "[audio] Created source BotC_Agent_Mic (from VirtualMic.monitor)"
else
  echo "[audio] Source BotC_Agent_Mic already exists"
fi

# Chromium output (game audio) → GameOut
pactl set-default-sink GameOut || true
# Chromium mic → BotC_Agent_Mic (agent TTS / espeak play into VirtualMic)
if pactl list short sources | grep -q "BotC_Agent_Mic"; then
  pactl set-default-source BotC_Agent_Mic || true
elif pactl list short sources | grep -q "VirtualMic.monitor"; then
  pactl set-default-source VirtualMic.monitor || true
fi

# Set volume high so speech is audible to WebRTC
pactl set-sink-volume VirtualMic 100% || true
pactl set-sink-volume GameOut 100% || true
pactl set-source-volume BotC_Agent_Mic 100% 2>/dev/null || \
  pactl set-source-volume VirtualMic.monitor 100% || true

echo "[audio] Default sink=$(pactl get-default-sink 2>/dev/null || true)"
echo "[audio] Default source=$(pactl get-default-source 2>/dev/null || true)"
echo "[audio] --- sinks ---"
pactl list short sinks || true
echo "[audio] --- sources ---"
pactl list short sources || true

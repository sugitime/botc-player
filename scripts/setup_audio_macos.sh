#!/usr/bin/env bash
# Helper notes + checks for routing botc.app audio on macOS.
set -euo pipefail

echo "=== BotC Agent audio setup (macOS) ==="
echo
echo "Goal:"
echo "  1) Firefox mic  <- agent TTS  (virtual INPUT for the browser)"
echo "  2) Agent STT    <- botc.app   (capture site / call audio)"
echo "  3) Firefox cam  <- dino face  (OBS Virtual Camera or pyvirtualcam)"
echo

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh then re-run."
  exit 1
fi

echo "Recommended packages:"
echo "  brew install blackhole-2ch"
echo "  # Optional multi-output helper:"
echo "  # Create a Multi-Output Device in Audio MIDI Setup that includes"
echo "  # your speakers + BlackHole 2ch so you can hear the game AND the agent can listen."
echo

if brew list blackhole-2ch >/dev/null 2>&1; then
  echo "✓ blackhole-2ch is installed"
else
  echo "• blackhole-2ch not installed yet"
  read -r -p "Install blackhole-2ch now via Homebrew? [y/N] " ans
  if [[ "${ans:-}" =~ ^[Yy]$ ]]; then
    brew install blackhole-2ch
  fi
fi

echo
echo "Firefox settings (botc.app):"
echo "  • Camera: OBS Virtual Camera (or the device pyvirtualcam prints)"
echo "  • Microphone: BlackHole 2ch  (agent speaks into this)"
echo
echo "Agent .env:"
echo "  AUDIO_OUTPUT_DEVICE=BlackHole  # TTS plays here (Firefox mic)"
echo "  AUDIO_INPUT_DEVICE=BlackHole   # or Multi-Output/loopback for STT"
echo
echo "Tip: For simultaneous local hearing + STT capture, use Audio MIDI Setup"
echo "→ '+' → Multi-Output Device → check Speakers + BlackHole, then set that"
echo "as macOS output while Firefox still uses BlackHole as mic."
echo
echo "Done."

#!/usr/bin/env bash
# Full stack inside Docker, then run the AI companion.
# Default: pass-through to `botc-player join ...`
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export DISPLAY_WIDTH="${DISPLAY_WIDTH:-1600}"
export DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-1000}"
export DOCKER=1
export BOTC_IN_DOCKER=1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-botc}"
export PULSE_RUNTIME_PATH="${XDG_RUNTIME_DIR}/pulse"
export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
export HOME="${HOME:-/home/botc}"

mkdir -p "$XDG_RUNTIME_DIR" "$PULSE_RUNTIME_PATH" /tmp/botc /var/log/botc 2>/dev/null || true
chmod 700 "$XDG_RUNTIME_DIR" || true

log() { echo "[entrypoint] $*"; }

cleanup() {
  log "Shutting down…"
  pkill -P $$ >/dev/null 2>&1 || true
  pulseaudio --kill >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# --- PulseAudio ---
log "Starting PulseAudio…"
pulseaudio --kill >/dev/null 2>&1 || true
rm -f /tmp/pulse-socket "${PULSE_RUNTIME_PATH}/pid" 2>/dev/null || true

pulseaudio \
  --daemonize=true \
  --exit-idle-time=-1 \
  --file=/dev/null \
  --load="module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-socket" \
  --load="module-always-sink" \
  --log-target=file:/var/log/botc/pulse.log \
  --disallow-exit \
  || pulseaudio --start --exit-idle-time=-1 || true

if [[ ! -S /tmp/pulse-socket ]]; then
  pactl load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-socket 2>/dev/null || true
fi

/app/scripts/docker-audio-setup.sh || log "WARN: audio setup had issues (continuing)"

# --- Xvfb desktop (for Chromium + optional noVNC watch) ---
log "Starting Xvfb on ${DISPLAY}…"
pkill -f "Xvfb ${DISPLAY}" >/dev/null 2>&1 || true
Xvfb "${DISPLAY}" -screen 0 "${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}x24" -ac +extension GLX +render -noreset \
  >/var/log/botc/xvfb.log 2>&1 &
sleep 0.4

openbox >/var/log/botc/openbox.log 2>&1 &
command -v xsetroot >/dev/null 2>&1 && xsetroot -solid "#1a1f2e" || true

x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw -xkb -repeat \
  -o /var/log/botc/x11vnc.log >/dev/null 2>&1 &

NOVNC_HOME="${NOVNC_HOME:-/usr/share/novnc}"
if [[ -d "$NOVNC_HOME" ]]; then
  log "noVNC → http://localhost:6080/vnc.html?autoconnect=1&resize=scale"
  websockify --web="$NOVNC_HOME" 6080 localhost:5900 >/var/log/botc/novnc.log 2>&1 &
fi

if [[ -e /dev/video0 ]]; then
  export BOTC_V4L2_DEVICE=/dev/video0
fi

cd /app

# No args → help
if [[ $# -eq 0 ]]; then
  exec python -m botc_player.main join --help
fi

# Utility modes
case "${1:-}" in
  shell)
    shift || true
    log "Interactive shell"
    exec bash "$@"
    ;;
  test)
    shift || true
    exec pytest -q "$@"
    ;;
  gui)
    shift || true
    exec python -m botc_player.main gui "$@"
    ;;
  list-devices|speak|cli)
    exec python -m botc_player.main "$@"
    ;;
  join)
    shift || true
    log "Starting AI companion (join)…"
    exec python -m botc_player.main join "$@"
    ;;
  -*)
    # Flags → join
    log "Starting AI companion (join)…"
    exec python -m botc_player.main join "$@"
    ;;
  *)
    # Anything else → pass to botc_player
    exec python -m botc_player.main "$@"
    ;;
esac

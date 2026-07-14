#!/usr/bin/env bash
# One-command launcher for the BotC AI companion (Docker).
#
# Usage:
#   ./run.sh --username USER --password PASS --player-name Dino --lobby https://botc.app/join/test
#
# Or short flags:
#   ./run.sh -u USER -p PASS -n Dino -l test
#
# Requires XAI_API_KEY in the environment or in ./.env
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ $# -eq 0 ]]; then
  cat <<'EOF'
BotC AI Companion (Docker)

Usage:
  ./run.sh --username USER --password PASS --player-name NAME --lobby LOBBY

Examples:
  ./run.sh -u myuser -p 'secret' -n Dino -l https://botc.app/join/test
  ./run.sh -u myuser -p 'secret' -n Dino -l test

Environment:
  XAI_API_KEY   required (or set in .env)
  XAI_MODEL     optional (default grok-4.5)

Watch the session:
  http://localhost:6080/vnc.html?autoconnect=1&resize=scale
EOF
  exit 1
fi

# Load .env if present (without printing secrets)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${XAI_API_KEY:-}" ]]; then
  echo "ERROR: XAI_API_KEY is not set. Add it to .env or export it." >&2
  exit 2
fi

# Build image if missing
if ! docker image inspect botc-player:latest >/dev/null 2>&1; then
  echo "Building Docker image (first run)…"
  docker compose build
fi

echo "Starting companion…  (noVNC: http://localhost:6080/vnc.html?autoconnect=1&resize=scale)"
exec docker compose run --rm --service-ports botc-player join "$@"

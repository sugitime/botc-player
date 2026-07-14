# Fully self-contained BotC AI companion.
# One command joins a lobby and plays.

FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    DISPLAY_WIDTH=1600 \
    DISPLAY_HEIGHT=1000 \
    DOCKER=1 \
    BOTC_IN_DOCKER=1 \
    PULSE_SERVER=unix:/tmp/pulse-socket \
    XDG_RUNTIME_DIR=/tmp/runtime-botc \
    HOME=/home/botc \
    LANG=C.UTF-8 \
    AUDIO_OUTPUT_DEVICE=VirtualMic \
    AUDIO_INPUT_DEVICE=GameOut \
    XAI_MODEL=grok-4.5 \
    XAI_TTS_VOICE=rex \
    TTS_PITCH_SEMITONES=3 \
    BOTC_URL=https://botc.app \
    LOG_LEVEL=INFO \
    NOVNC_HOME=/usr/share/novnc

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    python3-dev \
    portaudio19-dev \
    libportaudio2 \
    libasound2 \
    libasound2-plugins \
    pulseaudio \
    pulseaudio-utils \
    alsa-utils \
    espeak-ng \
    ffmpeg \
    xvfb \
    x11vnc \
    xterm \
    openbox \
    curl \
    ca-certificates \
    novnc \
    websockify \
    dbus-x11 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Playwright image already has uid 1000 (pwuser). Reuse it as "botc" when possible.
RUN if id -u botc >/dev/null 2>&1; then \
      echo "user botc exists"; \
    elif id -u pwuser >/dev/null 2>&1; then \
      usermod -l botc pwuser 2>/dev/null || true; \
      groupmod -n botc pwuser 2>/dev/null || true; \
      usermod -d /home/botc -m botc 2>/dev/null || mkdir -p /home/botc; \
    else \
      useradd -m -s /bin/bash botc; \
    fi \
    && mkdir -p /app /tmp/runtime-botc /var/log/botc /home/botc \
    && chown -R 1000:1000 /app /tmp/runtime-botc /var/log/botc /home/botc || \
       chown -R botc:botc /app /tmp/runtime-botc /var/log/botc /home/botc

WORKDIR /app

COPY --chown=1000:1000 pyproject.toml README.md ./
COPY --chown=1000:1000 src ./src
COPY --chown=1000:1000 assets ./assets
COPY --chown=1000:1000 scripts ./scripts
COPY --chown=1000:1000 tests ./tests

RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -e ".[dev]" \
    && (pip install --no-cache-dir pyvirtualcam || true) \
    && playwright install chromium \
    && chmod +x /app/scripts/docker-entrypoint.sh /app/scripts/docker-audio-setup.sh \
    && if [ -f /app/run.sh ]; then chmod +x /app/run.sh; fi

# Stay as root for entrypoint (Pulse/Xvfb), then drop privileges for the app if needed.
# Playwright base often expects non-root for browsers — use uid 1000.
USER 1000

EXPOSE 6080 5900

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD []

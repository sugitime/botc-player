# BotC AI Companion

A **fully Dockerized** AI that joins [botc.app](https://botc.app) and plays Blood on the Clocktower as a polite talking dinosaur.

One command: log in → join lobby → play.

---

## Quick start

### 1. Prerequisites

- Docker + Docker Compose
- [xAI API key](https://console.x.ai)

### 2. Configure API key

```bash
cp .env.example .env
# set XAI_API_KEY=...
```

### 3. Launch the companion

```bash
./run.sh \
  --username YOUR_BOTC_USER \
  --password 'YOUR_BOTC_PASSWORD' \
  --player-name Dino \
  --lobby https://botc.app/join/test
```

Short form (lobby code only):

```bash
./run.sh -u YOUR_BOTC_USER -p 'YOUR_BOTC_PASSWORD' -n Dino -l test
```

Equivalent pure Docker:

```bash
docker compose build
docker compose run --rm --service-ports botc-player join \
  --username YOUR_BOTC_USER \
  --password 'YOUR_BOTC_PASSWORD' \
  --player-name Dino \
  --lobby https://botc.app/join/test
```

### 4. Watch it (optional)

Open **http://localhost:6080/vnc.html?autoconnect=1&resize=scale**  
You’ll see Chromium on botc.app plus the dino face preview.

Stop with `Ctrl+C`.

---

## What the container includes

| Component | Purpose |
|-----------|---------|
| Playwright + Chromium | Logs into botc.app, joins lobby, clicks hand/vote/etc. |
| PulseAudio virtual devices | TTS → mic, game audio → STT |
| Dino face + WebRTC inject | Other players see the dinosaur camera |
| xAI Grok | Game brain, speech-to-text, text-to-speech |
| Xvfb + noVNC | Optional live view on port 6080 |

You do **not** need BlackHole, OBS, or a host Python install.

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--username` / `-u` | botc.app account username or email |
| `--password` / `-p` | botc.app password |
| `--player-name` / `-n` | Display name in the lobby |
| `--lobby` / `-l` | Full URL (`https://botc.app/join/test`) or code (`test`) |
| `--headless` | Hide Chromium (still works; noVNC won’t show the game page) |
| `--no-listen` | Disable speech-to-text |

---

## Environment (`.env`)

```env
XAI_API_KEY=           # required
XAI_MODEL=grok-4.5
XAI_TTS_VOICE=rex      # male voice
TTS_PITCH_SEMITONES=3  # a bit higher than deep male
BOTC_URL=https://botc.app
```

---

## Agent behavior

- Knows Blood on the Clocktower (roles, when to lie/tell truth, team win)
- Raises hand; does not overtalk public speakers
- Speaks when called on; answers night pings; votes
- Male voice, slightly higher pitch; dinosaur face on camera

If botc.app’s UI changes and auto-login/join misses a button, use noVNC to finish the click — the agent keeps running.

---

## Other commands

```bash
docker compose run --rm botc-player shell          # debug shell
docker compose run --rm botc-player test           # pytest
docker compose run --rm botc-player list-devices   # Pulse devices
docker compose run --rm --service-ports botc-player gui  # manual control panel
```

---

## Disclaimer

Only use on tables that welcome an AI player. Tell the Storyteller. Be kind — Dino is built to be polite.

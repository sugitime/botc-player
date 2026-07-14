"""One-shot: start companion, log into botc.app, join a lobby, play."""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass

from botc_player.browser.botc_client import normalize_lobby_url
from botc_player.config import Settings
from botc_player.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


@dataclass
class JoinRequest:
    username: str
    password: str
    player_name: str
    lobby: str
    headless_browser: bool = False
    no_listen: bool = False


def run_join(settings: Settings, req: JoinRequest) -> int:
    """Spin up the AI companion and join the given lobby. Blocks until stopped."""
    lobby_url = normalize_lobby_url(req.lobby)

    orch = Orchestrator(settings)
    orch.brain.state.my_name = req.player_name
    orch.settings.agent_player_name = req.player_name  # type: ignore[misc]
    orch.on_log = lambda m: print(m, flush=True)

    stop = {"flag": False}

    def _handle_sig(_signum, _frame):  # noqa: ANN001
        print("\nShutting down…", flush=True)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    print("=" * 60, flush=True)
    print("  BotC AI Companion — joining session", flush=True)
    print(f"  Account : {req.username}", flush=True)
    print(f"  Player  : {req.player_name}", flush=True)
    print(f"  Lobby   : {lobby_url}", flush=True)
    print("  Watch   : http://localhost:6080/vnc.html?autoconnect=1", flush=True)
    print("=" * 60, flush=True)

    # Face / audio first so media inject works when browser opens
    orch.start(
        start_browser=False,
        start_listener=not req.no_listen,
        start_camera=True,
    )

    try:
        orch.log("Opening browser…")
        orch.browser.connect(headless=req.headless_browser, start_url=settings.botc_url)
        # Remember run.sh --lobby immediately so any lobby-list screen bounces back here
        orch.browser.pinned_lobby_url = lobby_url
        orch.browser.pinned_lobby_code = lobby_url.rsplit("/", 1)[-1].lower()
        orch.log(f"Assigned lobby from run.sh: {lobby_url}")
        orch.log("Logging in…")
        if not orch.browser.login(req.username, req.password):
            orch.log("ERROR: login failed. Check credentials or use noVNC to log in manually.")
            # Still try join in case session cookies / already logged in
        orch.log(f"Joining lobby {lobby_url}…")
        ok = orch.browser.join_lobby(lobby_url, req.player_name)
        if ok:
            orch.log("Joined lobby — AI companion is live.")
            orch.inject_event(
                f"You joined the game as {req.player_name}. "
                "Observe, raise hand when appropriate, help your team win."
            )
        else:
            orch.log("WARN: join uncertain — companion still running; fix via noVNC if needed.")

        # Ensure Chromium sees Dino camera + Pulse mic/speakers
        try:
            orch.log("Warming media devices (mic/camera)…")
            orch.browser.log_media_status()
            orch.browser.open_chat_settings()
            orch.log(
                "In Settings → Chat, pick:\n"
                "  Microphone: BotC_Agent_Mic (or Default / VirtualMic)\n"
                "  Camera: Dino Face Camera (or any — dino is forced)\n"
                "  Speakers: BotC_Game_Output / GameOut / Default"
            )
        except Exception:
            logger.exception("media setup failed")

        if orch.browser.lobby_locked:
            orch.log(
                f"LOBBY LOCKED to {orch.browser.pinned_lobby_code or orch.browser.pinned_lobby_url} "
                "— will never leave or join another lobby."
            )
        orch.log("Agent running. Ctrl+C to stop.")
        orch.log('Voice command ready: say "AI, take a seat" to claim an open chair.')
        # Keep Playwright frames pumping on THIS thread only (Playwright is not thread-safe).
        # Drain UI commands (e.g. take_seat) here so Playwright stays on one thread.
        # Also re-assert lobby lock so we never drift into another room.
        lock_check = 0
        while not stop["flag"] and orch.running:
            try:
                orch.process_ui_commands()
                orch.browser.pump_frames()
                lock_check += 1
                if lock_check % 24 == 0:  # ~2s at 12 fps
                    orch.browser.enforce_lobby_lock()
            except Exception:
                logger.debug("pump_frames/ui/lock failed", exc_info=True)
            time.sleep(1 / 12)
    except Exception:
        logger.exception("join session failed")
        orch.log("Fatal error during join — see logs.")
        orch.stop()
        return 1
    finally:
        orch.stop()

    return 0


def parse_join_args(argv: list[str] | None = None):
    """Argparse for the join subcommand / docker default command."""
    import argparse

    p = argparse.ArgumentParser(
        prog="botc-player",
        description="Launch the BotC AI companion and join a lobby",
    )
    p.add_argument("--username", "-u", required=True, help="botc.app account username/email")
    p.add_argument("--password", "-p", required=True, help="botc.app account password")
    p.add_argument(
        "--player-name",
        "-n",
        required=True,
        help="Display name in the lobby (e.g. Dino)",
    )
    p.add_argument(
        "--lobby",
        "-l",
        required=True,
        help="Lobby URL or code (e.g. https://botc.app/join/test or test)",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium headless (no window; noVNC won't show the game)",
    )
    p.add_argument("--no-listen", action="store_true", help="Disable STT microphone capture")
    return p.parse_args(argv)

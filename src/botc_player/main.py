"""CLI entrypoint — default: join a botc.app lobby as the AI companion."""

from __future__ import annotations

import argparse
import logging
import sys


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Default command is "join" when flags look like join args or no subcommand
    if not argv or argv[0].startswith("-"):
        argv = ["join", *argv]
    elif argv[0] in {
        "--username",
        "-u",
        "--password",
        "-p",
        "--player-name",
        "-n",
        "--lobby",
        "-l",
    }:
        argv = ["join", *argv]

    parser = argparse.ArgumentParser(
        description="Blood on the Clocktower AI companion (Dino)",
    )
    sub = parser.add_subparsers(dest="command")

    # --- join (primary) ---
    join_p = sub.add_parser("join", help="Log in, join a lobby, run the AI companion")
    join_p.add_argument("--username", "-u", required=True, help="botc.app username/email")
    join_p.add_argument("--password", "-p", required=True, help="botc.app password")
    join_p.add_argument("--player-name", "-n", required=True, help="In-game display name")
    join_p.add_argument(
        "--lobby",
        "-l",
        required=True,
        help="Lobby URL or code (https://botc.app/join/test or test)",
    )
    join_p.add_argument("--headless", action="store_true", help="Headless Chromium")
    join_p.add_argument("--no-listen", action="store_true", help="Disable STT")

    # --- utilities ---
    sub.add_parser("gui", help="Open control panel GUI (optional)")
    sub.add_parser("list-devices", help="List audio devices")
    speak_p = sub.add_parser("speak", help="TTS smoke test")
    speak_p.add_argument("text", help="Text to speak")
    sub.add_parser("cli", help="Interactive CLI agent loop")

    args = parser.parse_args(argv)

    from botc_player.config import get_settings

    settings = get_settings()
    _configure_logging(settings.log_level)

    cmd = args.command or "join"

    if cmd == "join":
        from botc_player.join import JoinRequest, run_join

        if not settings.xai_api_key:
            print(
                "ERROR: XAI_API_KEY is not set.\n"
                "  docker:  -e XAI_API_KEY=...   or put it in .env\n"
                "  local:   export XAI_API_KEY=... / .env file",
                file=sys.stderr,
            )
            return 2
        req = JoinRequest(
            username=args.username,
            password=args.password,
            player_name=args.player_name,
            lobby=args.lobby,
            headless_browser=bool(getattr(args, "headless", False)),
            no_listen=bool(getattr(args, "no_listen", False)),
        )
        return run_join(settings, req)

    if cmd == "list-devices":
        from botc_player.audio.devices import format_device_table

        print(format_device_table())
        return 0

    if cmd == "speak":
        from botc_player.audio.tts import TextToSpeech

        TextToSpeech(settings).speak(args.text, block=True)
        return 0

    if cmd == "gui":
        from botc_player.ui.app import run_app

        run_app()
        return 0

    if cmd == "cli":
        return _run_cli(settings)

    parser.print_help()
    return 1


def _run_cli(settings) -> int:  # noqa: ANN001
    from botc_player.orchestrator import Orchestrator

    orch = Orchestrator(settings)
    orch.on_log = lambda m: print(m, flush=True)
    orch.start(start_browser=False, start_listener=True, start_camera=True)
    print("CLI agent running. Type events, or quit.")
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line or line in {"quit", "exit", "q"}:
                break
            orch.inject_event(line)
    except KeyboardInterrupt:
        pass
    finally:
        orch.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

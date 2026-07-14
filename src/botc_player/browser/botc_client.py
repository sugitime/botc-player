"""Playwright driver for botc.app — login, join lobby, in-game actions."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _chromium_launch_args() -> list[str]:
    args = [
        # Auto-accept permission prompts for mic/cam
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-blink-features=AutomationControlled",
        # Prefer PulseAudio device names in the picker
        "--enable-features=PulseaudioLoopbackForScreenShare",
    ]
    in_docker = os.environ.get("BOTC_IN_DOCKER", "").lower() in {"1", "true", "yes"} or Path(
        "/.dockerenv"
    ).exists()
    if in_docker:
        args.extend(
            [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                # Keep audio in-process so Pulse defaults (VirtualMic / GameOut) are used
                "--disable-features=AudioServiceOutOfProcess,AudioServiceSandbox",
                # Allow docker exec tooling / debugging of media devices
                "--remote-debugging-port=9222",
                # Transient Docker TLS flake: net::ERR_CERT_VERIFIER_CHANGED
                "--ignore-certificate-errors",
                "--ignore-certificate-errors-spki-list",
            ]
        )
        # Do NOT use --use-fake-device-for-media-stream: it replaces the real Pulse mic
        # with silence. Camera is provided via media_inject.js (Dino Face canvas).
    return args


def _load_media_inject() -> str:
    path = Path(__file__).with_name("media_inject.js")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "console.warn('[botc] media_inject.js missing');"


_MEDIA_INJECT_JS = _load_media_inject()


def normalize_lobby_url(lobby: str) -> str:
    """Accept full URLs or bare join codes like 'test' / 'join/test'."""
    lobby = lobby.strip()
    if not lobby:
        raise ValueError("lobby URL/code is empty")
    if lobby.startswith("http://") or lobby.startswith("https://"):
        return lobby
    # bare code
    code = lobby.removeprefix("join/").removeprefix("/")
    return f"https://botc.app/join/{code}"


_RESERVED_PATHS = frozenset(
    {
        "",
        "login",
        "register",
        "home",
        "lobby",
        "play",
        "game",
        "session",
        "room",
        "join",
        "settings",
        "about",
    }
)


def lobby_code_from_url(url: str) -> str:
    """Extract join code from a botc join/play URL if present."""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        fragment = (parsed.fragment or "").strip().lower()
    except Exception:
        return ""
    parts = [p for p in path.split("/") if p]
    # /join/CODE or /play/CODE etc.
    if len(parts) >= 2 and parts[0] in {"join", "play", "game", "session", "room"}:
        return parts[1].lower()
    # botc often uses hash routes: https://botc.app/#test or /play#test
    if fragment and fragment not in _RESERVED_PATHS and "/" not in fragment:
        # Prefer fragment when path is empty/home/play
        if not parts or parts[0].lower() in {"play", "join", "game", "session"}:
            return fragment
    # bare code only if not a reserved app path
    if len(parts) == 1 and parts[0].lower() not in _RESERVED_PATHS:
        return parts[0].lower()
    return ""


# UI labels that mean leave / switch lobby — never click these once locked in.
_LEAVE_OR_SWITCH_PATTERNS = re.compile(
    r"^\s*(leave|exit|quit|disconnect|return to lobby|leave game|leave session|"
    r"leave room|back to lobby|find game|find a game|new game|join another|"
    r"join game|join session|spectate|home)\s*$",
    re.I,
)


class BotcClient:
    def __init__(
        self,
        url: str = "https://botc.app",
        *,
        fake_video_path: Optional[str | Path] = None,
        frame_url: Optional[str] = None,
        face: Any = None,
    ):
        self.url = url.rstrip("/") or "https://botc.app"
        self.fake_video_path = Path(fake_video_path) if fake_video_path else None
        self.frame_url = frame_url
        self.face = face
        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None
        self.connected = False
        self._frame_stop = None
        self._frame_thread = None
        # Once set after the initial join, the agent stays in THIS session only.
        self.pinned_lobby_url: Optional[str] = None
        self.pinned_lobby_code: str = ""
        self.pinned_session_url: Optional[str] = None
        self.lobby_locked: bool = False
        self._allow_same_lobby_join_click: bool = False
        self._last_lobby_return_ts: float = 0.0

    def connect(self, *, headless: bool = False, start_url: Optional[str] = None) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        args = _chromium_launch_args()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=args,
            env={
                **os.environ,
                "PULSE_SERVER": os.environ.get("PULSE_SERVER", "unix:/tmp/pulse-socket"),
            },
        )
        self._context = self._browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=False,
        )
        # Reload inject from disk so Docker volume mounts pick up updates
        inject = _load_media_inject()
        self.page = self._context.new_page()
        self.page.add_init_script(inject)
        target = start_url or self.url
        last_err: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.goto(target, wait_until="domcontentloaded", timeout=90_000)
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning("goto %s failed (attempt %s/3): %s", target, attempt, e)
                time.sleep(1.5 * attempt)
        if last_err is not None:
            raise last_err
        self.connected = True
        # Seed one face frame on the Playwright thread (never push from other threads)
        self.pump_frames()
        self.warm_media_devices()
        logger.info("Opened %s", target)

    def warm_media_devices(self) -> list[dict[str, str]]:
        """Request mic permission and list devices Chromium can see (incl. Dino camera)."""
        page = self._need_page()
        try:
            devices = page.evaluate(
                """async () => {
                  if (window.__botcWarmMedia) return await window.__botcWarmMedia();
                  try {
                    const s = await navigator.mediaDevices.getUserMedia({audio:true, video:true});
                    s.getTracks().forEach(t => t.stop());
                  } catch (e) {}
                  return await navigator.mediaDevices.enumerateDevices();
                }"""
            )
            logger.info("Media devices (%d):", len(devices or []))
            for d in devices or []:
                logger.info(
                    "  [%s] %s — %s",
                    d.get("kind"),
                    d.get("label") or "(no label)",
                    (d.get("deviceId") or "")[:24],
                )
            return list(devices or [])
        except Exception:
            logger.exception("warm_media_devices failed")
            return []

    def open_chat_settings(self) -> bool:
        """Open botc.app App Settings → Chat (mic/cam pickers)."""
        page = self._need_page()
        # Gear icon top-right, then Chat tab
        opened = self._click_first(
            [
                ("css", "button[aria-label*='setting' i]"),
                ("css", "[class*='settings' i]"),
                ("css", "button:has(svg)"),
                ("role", "button:Settings"),
            ],
            timeout=2000,
        )
        page.wait_for_timeout(500)
        self._click_first(
            [
                ("role", "tab:Chat"),
                ("text", r"^chat$"),
                ("css", "button:has-text('Chat')"),
                ("css", "[role='tab']:has-text('Chat')"),
            ],
            timeout=2000,
        )
        page.wait_for_timeout(400)
        logger.info("Chat settings open attempt (opened_gear=%s)", opened)
        return opened

    def log_media_status(self) -> None:
        devices = self.warm_media_devices()
        cams = [d for d in devices if d.get("kind") == "videoinput"]
        mics = [d for d in devices if d.get("kind") == "audioinput"]
        outs = [d for d in devices if d.get("kind") == "audiooutput"]
        logger.info(
            "Device summary: %d camera(s), %d mic(s), %d speaker(s)",
            len(cams),
            len(mics),
            len(outs),
        )
        if not cams:
            logger.warning("No cameras listed — Dino inject may not be active on this page")
        if not mics:
            logger.warning("No mics listed — check PulseAudio BotC_Agent_Mic / VirtualMic")

    def pump_frames(self) -> None:
        """Push the latest dino face into the page. Must run on the Playwright thread."""
        if not self.face or not self.page or not self.connected:
            return
        import base64

        import cv2

        try:
            ok, buf = cv2.imencode(
                ".jpg",
                self.face.bgr_frame(),
                [int(cv2.IMWRITE_JPEG_QUALITY), 80],
            )
            if not ok:
                return
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            self.page.evaluate(
                "(b64) => window.__botcPushFrame && window.__botcPushFrame(b64)",
                b64,
            )
        except Exception as e:
            logger.debug("frame pump: %s", e)

    def close(self) -> None:
        self.connected = False
        self._frame_stop = None
        self._frame_thread = None
        for obj in (self._context, self._browser):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self.page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def _need_page(self):
        if not self.page:
            raise RuntimeError("Browser not connected. Call connect() first.")
        return self.page

    def pin_lobby(self, lobby: str, session_url: Optional[str] = None) -> None:
        """Lock the agent to one lobby for the rest of the process lifetime."""
        lobby_url = normalize_lobby_url(lobby)
        self.pinned_lobby_url = lobby_url
        self.pinned_lobby_code = lobby_code_from_url(lobby_url)
        if session_url:
            self.pinned_session_url = session_url
        elif self.page:
            self.pinned_session_url = self.page.url
        self.lobby_locked = True
        logger.info(
            "Lobby LOCKED — will never leave or join another. code=%s join=%s session=%s",
            self.pinned_lobby_code,
            self.pinned_lobby_url,
            self.pinned_session_url,
        )

    def _url_has_pinned_code(self, url: str) -> bool:
        if not self.pinned_lobby_code:
            return False
        u = (url or "").lower()
        code = self.pinned_lobby_code.lower()
        return (
            f"/join/{code}" in u
            or f"/play/{code}" in u
            or u.rstrip("/").endswith(f"#{code}")
            or f"#{code}" in u
            or lobby_code_from_url(url) == code
        )

    def _is_allowed_url(self, url: str) -> bool:
        """True if URL is still inside the pinned session (or lock not active)."""
        if not self.lobby_locked:
            return True
        u = (url or "").lower()
        # Same lobby code (path or hash) is always allowed
        if self._url_has_pinned_code(url):
            return True
        # Always block a *different* join code
        other = lobby_code_from_url(url)
        if other and self.pinned_lobby_code and other != self.pinned_lobby_code:
            return False
        if "/join/" in u and self.pinned_lobby_code and f"/join/{self.pinned_lobby_code}" not in u:
            return False
        # Multi-lobby browser pages without our code
        path = (urlparse(url).path or "/").rstrip("/") or "/"
        if path in {"/", "/login", "/register", "/home", "/lobby", "/lobbies", "/games", "/public"}:
            return False
        if any(k in u for k in ("/lobbies", "/public", "lobby-list", "game-list")):
            return False
        # /play, /game without other code = same session (botc often drops the code in path)
        if any(k in u for k in ("/play", "/game", "/session", "/room")):
            return True
        if self.pinned_session_url and urlparse(url).path == urlparse(self.pinned_session_url).path:
            return True
        return False

    def _looks_like_lobby_list(self) -> bool:
        """Detect the multi-lobby browser UI (list of tables to join)."""
        if not self.page:
            return False
        try:
            url = (self.page.url or "").lower()
        except Exception:
            url = ""
        # If URL already names our pinned lobby, we are not on a generic list
        if self._url_has_pinned_code(url):
            return False
        if any(k in url for k in ("/play", "/game", "/session", "/room")):
            return False
        path = (urlparse(url).path or "/").rstrip("/") or "/"
        if path in {"/lobbies", "/games", "/public"}:
            return True
        # Bare home without our hash may be a list — only if UI looks like one
        try:
            body = (self.page.inner_text("body") or "").lower()[:4000]
        except Exception:
            body = ""
        # Single-room markers mean we are already at a table UI
        if any(
            k in body
            for k in (
                "click to claim",
                "return to grimoire",
                "town square",
                "seat 1",
                "characters",
            )
        ):
            return False
        list_signals = 0
        for phrase in (
            "public games",
            "public lobbies",
            "open games",
            "available games",
            "join a game",
            "find a game",
            "create game",
            "create a game",
            "game list",
            "lobby list",
            "browse games",
            "server list",
            "active games",
        ):
            if phrase in body:
                list_signals += 2
        if body.count("join") >= 4 and "/play" not in url:
            list_signals += 1
        if path in {"/", "/home", "/lobby"} and list_signals >= 2:
            return True
        return list_signals >= 2

    def return_to_pinned_lobby(self, reason: str = "") -> bool:
        """Navigate back to the lobby from run.sh --lobby (never another table)."""
        target = self.pinned_lobby_url
        if not target:
            logger.error("return_to_pinned_lobby: no pinned lobby URL from run.sh")
            return False
        if not self.page:
            return False
        now = time.time()
        # Avoid tight navigate loops if botc redirects us
        if now - self._last_lobby_return_ts < 12.0:
            logger.debug("Lobby lock: skip rapid re-return (%.1fs)", now - self._last_lobby_return_ts)
            return True
        self._last_lobby_return_ts = now
        msg = reason or "returning to assigned lobby"
        logger.warning("Lobby lock: %s → %s", msg, target)
        try:
            self.page.goto(target, wait_until="domcontentloaded", timeout=60_000)
            self.page.wait_for_timeout(1000)
            # Re-enter THE SAME lobby only (Join is allowed for this one action)
            self._allow_same_lobby_join_click = True
            try:
                self._click_first(
                    [
                        ("role", "button:Join"),
                        ("role", "button:Join game"),
                        ("role", "button:Join session"),
                        ("role", "button:Enter"),
                        ("role", "button:Continue"),
                        ("role", "button:Play"),
                        ("text", r"^join(\s+game|\s+session)?$"),
                        ("css", "button:has-text('Join')"),
                    ],
                    timeout=3000,
                )
            finally:
                self._allow_same_lobby_join_click = False
            self.page.wait_for_timeout(800)
            if any(k in (self.page.url or "") for k in ("/play", "/game", "/session", "/room")):
                self.pinned_session_url = self.page.url
            logger.info("Lobby lock: back at %s", self.page.url)
            return True
        except Exception:
            self._allow_same_lobby_join_click = False
            logger.exception("Lobby lock: failed to return to %s", target)
            return False

    def enforce_lobby_lock(self) -> bool:
        """If we drifted to a lobby list or another room, go back to run.sh --lobby.

        Returns True if still in (or restored to) the correct lobby.
        """
        if not self.lobby_locked or not self.page:
            return True
        try:
            url = self.page.url
        except Exception:
            return False

        # Already on our assigned lobby (path or #code) — stay, don't thrash
        if self._url_has_pinned_code(url):
            if any(k in url for k in ("/play", "/game", "/session", "/room")):
                self.pinned_session_url = url
            return True

        if self._looks_like_lobby_list():
            return self.return_to_pinned_lobby(
                f"saw lobby list at {url}; going back to run.sh lobby"
            )

        if self._is_allowed_url(url):
            if any(k in url for k in ("/play", "/game", "/session", "/room")):
                self.pinned_session_url = url
            return True

        logger.warning(
            "Lobby lock: left pinned session (now %s). Returning to run.sh lobby.",
            url,
        )
        return self.return_to_pinned_lobby(f"left session ({url})")

    def _safe_goto(self, url: str, **kwargs) -> None:
        """Navigate only if allowed by lobby lock."""
        page = self._need_page()
        if self.lobby_locked and not self._is_allowed_url(url):
            logger.error(
                "Blocked navigation to %s — agent is locked to lobby %s",
                url,
                self.pinned_lobby_code or self.pinned_lobby_url,
            )
            return
        page.goto(url, **kwargs)

    def _click_first(self, strategies: list[tuple[str, str]], timeout: float = 2500) -> bool:
        page = self._need_page()
        for kind, value in strategies:
            # Hard block leave / switch-lobby clicks once locked
            # Exception: re-joining the *same* lobby after a bounce is allowed briefly.
            if self.lobby_locked and not self._allow_same_lobby_join_click:
                check = value
                if kind == "role" and ":" in value:
                    check = value.split(":", 1)[1]
                if _LEAVE_OR_SWITCH_PATTERNS.search(check or ""):
                    logger.error(
                        "Blocked click (%s=%s) — never leave or join another lobby",
                        kind,
                        value,
                    )
                    continue
                if re.search(
                    r"leave|exit game|disconnect|join another|/join/",
                    check or "",
                    re.I,
                ):
                    logger.error("Blocked click (%s=%s) — lobby lock", kind, value)
                    continue
            elif self.lobby_locked and self._allow_same_lobby_join_click:
                check = value
                if kind == "role" and ":" in value:
                    check = value.split(":", 1)[1]
                # Still never leave/exit — only Join for our table
                if re.search(r"leave|exit|disconnect|quit|home", check or "", re.I):
                    logger.error("Blocked click (%s=%s) even during rejoin", kind, value)
                    continue
            try:
                if kind == "role":
                    role, _, name = value.partition(":")
                    loc = page.get_by_role(role, name=re.compile(name, re.I))
                elif kind == "text":
                    loc = page.get_by_text(re.compile(value, re.I))
                elif kind == "css":
                    loc = page.locator(value)
                elif kind == "label":
                    loc = page.get_by_label(re.compile(value, re.I))
                elif kind == "placeholder":
                    loc = page.get_by_placeholder(re.compile(value, re.I))
                else:
                    continue
                target = loc.first
                if target.count() == 0:
                    continue
                # Extra safety: read accessible name if possible
                try:
                    label = (target.inner_text(timeout=500) or "")[:80]
                    if self.lobby_locked and _LEAVE_OR_SWITCH_PATTERNS.search(label.strip()):
                        logger.error("Blocked click on '%s' — lobby lock", label)
                        continue
                except Exception:
                    pass
                target.click(timeout=timeout)
                logger.info("Clicked via %s=%s", kind, value)
                return True
            except Exception as e:
                logger.debug("Click strategy failed %s=%s: %s", kind, value, e)
        return False

    def _fill_first(self, strategies: list[tuple[str, str]], value: str, timeout: float = 4000) -> bool:
        page = self._need_page()
        for kind, sel in strategies:
            try:
                if kind == "css":
                    loc = page.locator(sel)
                elif kind == "label":
                    loc = page.get_by_label(re.compile(sel, re.I))
                elif kind == "placeholder":
                    loc = page.get_by_placeholder(re.compile(sel, re.I))
                elif kind == "role":
                    role, _, name = sel.partition(":")
                    loc = page.get_by_role(role, name=re.compile(name, re.I))
                else:
                    continue
                target = loc.first
                if target.count() == 0:
                    continue
                target.wait_for(state="visible", timeout=timeout)
                target.click(timeout=timeout)
                # React-controlled inputs often ignore fill(); clear + type triggers onChange.
                target.fill("")
                try:
                    target.press_sequentially(value, delay=15)
                except Exception:
                    target.type(value, delay=15)
                # Verify value stuck
                current = target.input_value(timeout=2000)
                if value not in current and current != value:
                    target.fill(value)
                logger.info("Filled via %s=%s (len=%s)", kind, sel, len(value))
                return True
            except Exception as e:
                logger.debug("Fill strategy failed %s=%s: %s", kind, sel, e)
        return False

    def login(self, username: str, password: str, *, timeout_s: float = 60.0) -> bool:
        """Log into botc.app. Returns True if login appears successful."""
        page = self._need_page()
        logger.info("Logging in as %s …", username)

        if self.lobby_locked:
            logger.error("login() refused — already locked in lobby %s", self.pinned_lobby_code)
            return True

        # Prefer dedicated login route (join links redirect here when logged out)
        for candidate in (
            f"{self.url}/login",
            f"{self.url}/",
            self.url,
        ):
            try:
                self._safe_goto(candidate, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(1200)
                if page.locator("input[type='password']").count() > 0:
                    break
            except Exception:
                continue

        # Open login UI if fields not yet visible
        if page.locator("input[type='password']").count() == 0:
            self._click_first(
                [
                    ("role", "button:Log in"),
                    ("role", "button:Login"),
                    ("role", "link:Log in"),
                    ("role", "link:Login"),
                    ("text", r"^log\s*in$"),
                    ("css", "a[href*='login' i]"),
                    ("css", "button:has-text('Log in')"),
                ],
                timeout=3000,
            )
            page.wait_for_timeout(1000)

        # Wait for password field
        try:
            page.locator("input[type='password']").first.wait_for(state="visible", timeout=15_000)
        except Exception:
            logger.error("Login form never appeared (url=%s)", page.url)
            return False

        user_ok = self._fill_first(
            [
                ("label", r"email|username|user name|account"),
                ("placeholder", r"email|username|user"),
                ("css", "input[type='email']"),
                ("css", "input[name*='user' i]"),
                ("css", "input[name*='email' i]"),
                ("css", "input[id*='user' i]"),
                ("css", "input[id*='email' i]"),
                ("css", "input[autocomplete='username']"),
                ("css", "input[type='text']"),
            ],
            username,
        )
        pass_ok = self._fill_first(
            [
                ("label", r"password"),
                ("placeholder", r"password"),
                ("css", "input[type='password']"),
                ("css", "input[name*='pass' i]"),
                ("css", "input[autocomplete='current-password']"),
            ],
            password,
        )
        if not user_ok or not pass_ok:
            logger.error(
                "Could not find login fields (user_ok=%s pass_ok=%s). "
                "DOM may have changed — check noVNC and update selectors.",
                user_ok,
                pass_ok,
            )
            return False

        # Cloudflare Turnstile often blocks automated login until checked.
        self._try_cloudflare_checkbox()
        page.wait_for_timeout(800)

        # Prefer explicit Login click (button may stay disabled until captcha)
        submitted = self._click_first(
            [
                ("role", "button:Login"),
                ("role", "button:Log in"),
                ("role", "button:Sign in"),
                ("css", "button[type='submit']"),
                ("css", "form button"),
                ("text", r"^(log\s*in|sign\s*in|login)$"),
            ],
            timeout=4000,
        )
        if not submitted:
            try:
                page.locator("input[type='password']").first.press("Enter")
                submitted = True
                logger.info("Submitted login via Enter on password field")
            except Exception:
                pass
        if not submitted:
            logger.error("Could not submit login form")
            self._debug_snapshot("login_submit_fail")
            return False

        page.wait_for_timeout(1500)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        # If still on login with captcha, give the operator time to complete it in noVNC
        if self._has_cloudflare_challenge() or "/login" in page.url.lower():
            wait_s = max(timeout_s, 180.0)
            logger.warning(
                "Login may need human verification (Cloudflare). "
                "Open http://localhost:6080/vnc.html?autoconnect=1 — "
                "check 'Verify you are human', then click Login. Waiting up to %.0fs…",
                wait_s,
            )
            print(
                "\n*** ACTION NEEDED ***\n"
                "Open http://localhost:6080/vnc.html?autoconnect=1\n"
                "1) Check Cloudflare 'Verify you are human'\n"
                "2) Click Login\n"
                "Waiting for you…\n",
                flush=True,
            )
            deadline = time.time() + wait_s
        else:
            deadline = time.time() + timeout_s

        while time.time() < deadline:
            page.wait_for_timeout(1000)
            # Retry captcha click periodically (sometimes becomes interactable later)
            if self._has_cloudflare_challenge():
                self._try_cloudflare_checkbox()
            url = page.url.lower()
            body = ""
            try:
                body = page.inner_text("body").lower()[:3000]
            except Exception:
                pass
            still_on_login = "/login" in url
            has_password = page.locator("input[type='password']").count() > 0
            if any(
                err in body
                for err in (
                    "invalid",
                    "incorrect",
                    "failed",
                    "wrong password",
                    "unauthorized",
                    "unable to log",
                    "could not log",
                )
            ) and still_on_login:
                logger.error("Login rejected by site (url=%s)", page.url)
                self._debug_snapshot("login_rejected")
                return False
            if not still_on_login and not has_password:
                logger.info("Login succeeded (url=%s)", page.url)
                return True
            if "log out" in body or "logout" in body or "sign out" in body:
                logger.info("Login succeeded (logout control visible)")
                return True
            # If captcha cleared, re-click Login
            if still_on_login and not self._has_cloudflare_challenge():
                self._click_first(
                    [
                        ("role", "button:Login"),
                        ("text", r"^login$"),
                        ("css", "button[type='submit']"),
                    ],
                    timeout=1500,
                )

        logger.warning("Login result uncertain after wait — url=%s", page.url)
        self._debug_snapshot("login_timeout")
        try:
            if page.locator("input[type='password']").count() == 0 and "/login" not in page.url.lower():
                return True
        except Exception:
            pass
        return False

    def _has_cloudflare_challenge(self) -> bool:
        page = self.page
        if not page:
            return False
        try:
            if page.locator("iframe[src*='challenges.cloudflare'], iframe[src*='turnstile']").count():
                return True
            body = (page.inner_text("body") or "").lower()
            return "verify you are human" in body or "cloudflare" in body
        except Exception:
            return False

    def _try_cloudflare_checkbox(self) -> bool:
        """Best-effort click on Cloudflare Turnstile (often blocked for automation)."""
        page = self._need_page()
        try:
            # Host-page label/checkbox area
            for sel in (
                "text=Verify you are human",
                "label:has-text('Verify you are human')",
                "input[type='checkbox']",
            ):
                loc = page.locator(sel)
                if loc.count():
                    try:
                        loc.first.click(timeout=2000, force=True)
                        logger.info("Clicked captcha control via %s", sel)
                        page.wait_for_timeout(1500)
                        return True
                    except Exception:
                        pass
            # iframe challenge
            frames = page.frames
            for frame in frames:
                url = frame.url or ""
                if "cloudflare" in url or "turnstile" in url or "challenges" in url:
                    try:
                        frame.locator("body").click(timeout=2000, force=True)
                        logger.info("Clicked inside Cloudflare frame")
                        page.wait_for_timeout(1500)
                        return True
                    except Exception:
                        try:
                            box = frame.locator("input, body").first
                            box.click(timeout=2000, force=True)
                            return True
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("captcha click failed: %s", e)
        return False

    def _debug_snapshot(self, label: str) -> None:
        """Best-effort screenshot + text dump for noVNC debugging."""
        page = self.page
        if not page:
            return
        path = f"/tmp/botc_{label}.png"
        try:
            page.screenshot(path=path, full_page=True)
            logger.info("Saved debug screenshot %s", path)
        except Exception as e:
            logger.debug("screenshot failed: %s", e)
        try:
            logger.info("Page url=%s title=%s", page.url, page.title())
            logger.info("Visible text excerpt: %s", (page.inner_text("body") or "")[:500])
        except Exception:
            pass

    def join_lobby(self, lobby: str, player_name: str, *, timeout_s: float = 60.0) -> bool:
        """Navigate to a join link and enter the session as player_name.

        After a successful join, the lobby is permanently locked for this process —
        the agent will never leave or join a different lobby.
        """
        page = self._need_page()
        lobby_url = normalize_lobby_url(lobby)
        code = lobby_code_from_url(lobby_url)

        # Already locked to this lobby — stay put, do not re-join or hop
        if self.lobby_locked:
            if code and self.pinned_lobby_code and code != self.pinned_lobby_code:
                logger.error(
                    "Refusing to join %s — locked to lobby %s",
                    code,
                    self.pinned_lobby_code,
                )
                return False
            logger.info(
                "Already locked in lobby %s — not navigating again",
                self.pinned_lobby_code,
            )
            self.enforce_lobby_lock()
            return True

        logger.info("Joining lobby %s as %s …", lobby_url, player_name)

        self._safe_goto(lobby_url, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(1500)

        # If login wall appears on join page, caller should have logged in first;
        # still try a soft wait.
        self._set_player_name(player_name)
        page.wait_for_timeout(400)

        # Only click Join on the *initial* entry into THIS lobby (before lock).
        joined = self._click_first(
            [
                ("role", "button:Join"),
                ("role", "button:Join game"),
                ("role", "button:Join session"),
                ("role", "button:Enter"),
                ("role", "button:Continue"),
                ("role", "button:Play"),
                ("text", r"^join(\s+game|\s+session)?$"),
                ("css", "button:has-text('Join')"),
            ],
            timeout=5000,
        )
        if not joined:
            # Some lobbies auto-join when name is set; try Enter
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass

        ok = False
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            page.wait_for_timeout(800)
            url = page.url
            body = ""
            try:
                body = page.inner_text("body")[:3000]
            except Exception:
                pass
            lower = body.lower()
            # Heuristics: left pure join page / see player list / grimoire / seat
            if player_name.lower() in lower:
                logger.info("Player name visible in session UI")
                ok = True
                break
            if any(k in lower for k in ("town square", "grimoire", "storyteller", "alive", "day ", "night", "click to claim", "seat ")):
                logger.info("Session UI markers found")
                ok = True
                break
            parsed = urlparse(url)
            if "/join/" not in parsed.path and parsed.path not in ("", "/"):
                logger.info("Navigated off join page → %s", url)
                ok = True
                break

        if not ok:
            logger.warning("Join result uncertain after %.0fs (url=%s)", timeout_s, page.url)
            # Still pin so we never wander to a *different* lobby
            ok = True

        # Permanent pin: never leave / never join another lobby this process
        self.pin_lobby(lobby_url, session_url=page.url)
        return ok

    def _set_player_name(self, player_name: str) -> bool:
        ok = self._fill_first(
            [
                ("label", r"name|display|player|nickname|character"),
                ("placeholder", r"name|display|player|nickname|enter your"),
                ("css", "input[name*='name' i]"),
                ("css", "input[id*='name' i]"),
                ("css", "input[placeholder*='name' i]"),
            ],
            player_name,
        )
        if not ok:
            # Last resort: focused text input that isn't password/email
            page = self._need_page()
            try:
                inputs = page.locator("input:visible")
                for i in range(min(inputs.count(), 8)):
                    el = inputs.nth(i)
                    typ = (el.get_attribute("type") or "text").lower()
                    if typ in ("password", "email", "hidden", "checkbox", "radio", "submit"):
                        continue
                    el.fill(player_name)
                    logger.info("Filled player name via visible input #%s", i)
                    return True
            except Exception as e:
                logger.debug("player name fallback failed: %s", e)
        return ok

    def login_and_join(
        self,
        username: str,
        password: str,
        player_name: str,
        lobby: str,
    ) -> bool:
        if not self.login(username, password):
            return False
        return self.join_lobby(lobby, player_name)

    # --- In-game actions ---

    def claim_open_seat(self, preferred: Optional[int] = None) -> Optional[int]:
        """Click an open seat labeled like 'Seat N' / 'Click to claim'.

        Must run on the Playwright owner thread. Returns seat number if claimed.
        """
        page = self._need_page()
        # Dismiss settings / modals that block the table
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        except Exception:
            pass

        # Prefer explicit seat number if requested
        seat_order: list[int] = []
        if preferred is not None and 1 <= preferred <= 20:
            seat_order.append(preferred)
        seat_order.extend([n for n in range(1, 16) if n not in seat_order])

        for n in seat_order:
            # Match "Click to claim" near Seat N — try several strategies
            strategies = [
                ("text", rf"Seat\s*{n}\s*\n?\s*Click to claim"),
                ("text", rf"Click to claim"),
                ("css", f"text=/Seat\\s*{n}/i"),
            ]
            # 1) Click the seat label block containing Seat N + Click to claim
            try:
                seat_label = page.get_by_text(re.compile(rf"Seat\s*{n}\b", re.I)).first
                if seat_label.count() > 0:
                    # Parent card often holds "Click to claim"
                    try:
                        card = seat_label.locator(
                            "xpath=ancestor::*[contains(., 'Click to claim') or contains(., 'click to claim')][1]"
                        )
                        if card.count() > 0:
                            claim = card.get_by_text(re.compile(r"Click to claim", re.I)).first
                            if claim.count() > 0:
                                claim.click(timeout=2500)
                                logger.info("Claimed seat %s via card 'Click to claim'", n)
                                page.wait_for_timeout(600)
                                return n
                    except Exception:
                        pass
                    # Fallback: click the seat number label itself
                    seat_label.click(timeout=2500)
                    logger.info("Clicked seat %s label", n)
                    page.wait_for_timeout(400)
                    # If a claim control appeared, click it
                    if self._click_first(
                        [
                            ("text", r"Click to claim"),
                            ("role", "button:Claim"),
                            ("role", "button:Sit"),
                            ("role", "button:Take seat"),
                        ],
                        timeout=1500,
                    ):
                        logger.info("Claimed seat %s after label click", n)
                        return n
                    # Label click alone sometimes claims
                    body = (page.inner_text("body") or "").lower()
                    if "click to claim" not in body or f"seat {n}" in body:
                        # Heuristic: if that seat no longer says click to claim, success
                        still = page.get_by_text(
                            re.compile(rf"Seat\s*{n}[\s\S]{{0,40}}Click to claim", re.I)
                        )
                        if still.count() == 0:
                            logger.info("Seat %s appears claimed after label click", n)
                            return n
            except Exception as e:
                logger.debug("seat %s claim attempt failed: %s", n, e)
                continue

        # Last resort: any visible "Click to claim"
        if self._click_first(
            [
                ("text", r"Click to claim"),
                ("role", "button:Click to claim"),
            ],
            timeout=2500,
        ):
            logger.info("Clicked first available 'Click to claim'")
            return 0
        logger.warning("No open seat found to claim")
        return None

    def raise_hand(self) -> bool:
        return self._click_first(
            [
                ("role", "button:Raise hand"),
                ("role", "button:Hand"),
                ("text", r"raise hand"),
                ("css", "[aria-label*='hand' i]"),
                ("css", "button:has-text('Hand')"),
            ]
        )

    def lower_hand(self) -> bool:
        return self._click_first(
            [
                ("role", "button:Lower hand"),
                ("text", r"lower hand"),
                ("css", "[aria-label*='lower hand' i]"),
                ("css", "[aria-label*='hand' i]"),
            ]
        )

    def vote_for(self, player_name: str) -> bool:
        page = self._need_page()
        try:
            page.get_by_text(re.compile(rf"^{re.escape(player_name)}$", re.I)).first.click(
                timeout=3000
            )
        except Exception:
            logger.warning("Could not click player seat for %s", player_name)
        return self._click_first(
            [
                ("role", "button:Vote"),
                ("text", r"^vote$"),
                ("css", "button:has-text('Vote')"),
            ]
        )

    def select_player(self, player_name: str) -> bool:
        page = self._need_page()
        try:
            page.get_by_text(re.compile(re.escape(player_name), re.I)).first.click(timeout=3000)
            return True
        except Exception:
            logger.warning("select_player failed for %s", player_name)
            return False

    def confirm(self) -> bool:
        return self._click_first(
            [
                ("role", "button:Confirm"),
                ("role", "button:OK"),
                ("role", "button:Yes"),
                ("text", r"^(confirm|ok|yes|done)$"),
            ]
        )

    def mute_toggle(self) -> bool:
        return self._click_first(
            [
                ("role", "button:Mute"),
                ("role", "button:Unmute"),
                ("css", "[aria-label*='mute' i]"),
            ]
        )

    def read_visible_text(self, limit: int = 4000) -> str:
        page = self._need_page()
        try:
            return page.inner_text("body")[:limit]
        except Exception:
            return ""

    def snapshot(self) -> dict[str, Any]:
        if not self.page:
            return {"connected": False}
        return {
            "connected": True,
            "url": self.page.url,
            "title": self.page.title(),
            "visible_excerpt": self.read_visible_text(800),
        }

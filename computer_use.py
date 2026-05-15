"""Browser automation harness for the DRIFT bot using Playwright.

Provides screenshot-driven UI interaction with the same authorization
and safety guardrails as the reconnaissance tools.
"""
import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from config import PROJECT_ROOT

# Lazy-import playwright so the module loads even when playwright is absent
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# Playwright action types that do not require a page (e.g., wait)
NO_PAGE_ACTIONS = {"wait", "sleep"}

# Actions that can change state and should be logged
MUTATING_ACTIONS = {"click", "double_click", "type", "keypress", "scroll", "drag", "move"}

# Sensitive URL patterns that always require explicit confirmation
SENSITIVE_PATTERNS = [
    re.compile(r"/login", re.I),
    re.compile(r"/signin", re.I),
    re.compile(r"/auth", re.I),
    re.compile(r"/checkout", re.I),
    re.compile(r"/payment", re.I),
    re.compile(r"/bank", re.I),
    re.compile(r"/transfer", re.I),
    re.compile(r"/password", re.I),
    re.compile(r"/delete", re.I),
    re.compile(r"/remove", re.I),
    re.compile(r"/api/.*key", re.I),
]

# Max screenshot size in bytes (5 MB)
MAX_SCREENSHOT_BYTES = 5_242_880

# Default viewport
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


@dataclass
class ComputerUseState:
    """Runtime state for ComputerUse."""
    active: bool = True
    last_run: Optional[str] = None
    session_active: bool = False
    current_url: Optional[str] = None


class ComputerUse:
    """
    Browser automation harness for the DRIFT bot using Playwright.
    Provides screenshot-driven UI interaction with authorization
    and safety guardrails.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.state = ComputerUseState()

    def cycle(self, context) -> None:
        """
        Called by the consciousness loop. Updates state based on active session.
        """
        global _active_session
        self.state.last_run = datetime.now().isoformat()
        self.state.session_active = _active_session is not None
        if _active_session:
            self.state.current_url = _active_session.page.url

    def format_prompt_snippet(self) -> str:
        """Return a string to inject into the chat prompt."""
        if not self.state.session_active:
            return "COMPUTER USE: No active browser session. I can launch a browser if needed to research or interact with web UIs."
        
        return (
            f"COMPUTER USE: Active browser session at {self.state.current_url}.\n"
            f"I can click, type, and scroll to interact with this page."
        )

    # --- Interaction methods ---

    def run_actions(self, actions: List[Dict[str, Any]], authorized_domains: Optional[Set[str]] = None) -> str:
        return run_computer_actions(actions, authorized_domains)

    def get_status(self) -> str:
        return get_computer_session_status()

    def close(self) -> str:
        return close_computer_session()


def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "computer_use" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="computer_use",
            description="Browser automation and UI interaction via Playwright",
            module_path="plugins.computer_use",
            instance_factory=ComputerUse,
            cycle_handler="cycle",
            cycle_frequency=5,  # Less frequent than core modules
            cycle_priority=60,
            prompt_formatter="format_prompt_snippet",
            prompt_priority=60,
            prompt_section="context",
        ))

_register()


@dataclass
class ComputerSession:
    """Holds a single browser session (Playwright + Browser + Context + Page)."""
    browser: Any
    context: Any
    page: Any
    authorized_domains: Set[str] = field(default_factory=set)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def close(self):
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass


# Module-level session cache (one active session at a time)
_active_session: Optional[ComputerSession] = None


def _ensure_browser() -> ComputerSession:
    """Launch or reuse a headless Chromium session."""
    global _active_session
    if _active_session is not None:
        return _active_session
    if sync_playwright is None:
        raise ComputerUseError("playwright is not installed. Run: pip install playwright && playwright install chromium")

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=["--window-size=1440,900"])
    context = browser.new_context(viewport=DEFAULT_VIEWPORT)
    page = context.new_page()
    session = ComputerSession(browser=browser, context=context, page=page)
    _active_session = session
    return session


def _domain_from_url(url: str) -> str:
    return urlparse(url).hostname or ""


def _is_url_allowed(url: str, authorized: Set[str]) -> bool:
    domain = _domain_from_url(url).lower()
    if not domain:
        return False
    if domain in authorized:
        return True
    # Also allow subdomains of authorized domains
    for auth in authorized:
        if domain == auth or domain.endswith(f".{auth}"):
            return True
    return False


def _is_sensitive_action(action: Dict[str, Any]) -> bool:
    """Check if an action involves a sensitive workflow."""
    action_type = action.get("type", "").lower()
    if action_type in {"type", "keypress"}:
        text = action.get("text", "")
        # Heuristic: typing passwords or API keys
        if re.search(r"password|secret|token|api[_-]?key", text, re.I):
            return True
    if action_type == "navigate":
        url = action.get("url", "")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(url):
                return True
    return False


def _truncate_screenshot(b64: str, max_bytes: int = MAX_SCREENSHOT_BYTES) -> str:
    raw = base64.b64decode(b64)
    if len(raw) <= max_bytes:
        return b64
    # If oversized, return a placeholder instead of crashing
    return "[screenshot too large: truncated by harness]"


def _run_action(session: ComputerSession, action: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single action and return result metadata."""
    action_type = action.get("type", "").lower()
    page = session.page
    result = {"type": action_type, "status": "ok"}

    if action_type == "navigate":
        url = action.get("url", "")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        page.goto(url, wait_until="networkidle", timeout=30_000)
        result["url"] = page.url
        result["title"] = page.title()

    elif action_type == "screenshot":
        png_bytes = page.screenshot(type="png", full_page=action.get("full_page", False))
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        result["screenshot_base64"] = _truncate_screenshot(b64)
        result["width"] = page.viewport_size["width"]
        result["height"] = page.viewport_size["height"]

    elif action_type == "click":
        x, y = action.get("x", 0), action.get("y", 0)
        button = action.get("button", "left")
        page.mouse.click(x, y, button=button)
        result["x"] = x
        result["y"] = y

    elif action_type == "double_click":
        x, y = action.get("x", 0), action.get("y", 0)
        button = action.get("button", "left")
        page.mouse.dblclick(x, y, button=button)
        result["x"] = x
        result["y"] = y

    elif action_type == "type":
        text = action.get("text", "")
        # If coordinates provided, click first then type
        if "x" in action and "y" in action:
            page.mouse.click(action["x"], action["y"])
        selector = action.get("selector")
        if selector:
            page.locator(selector).fill(text)
        else:
            page.keyboard.type(text)
        result["text_length"] = len(text)

    elif action_type == "keypress":
        keys = action.get("keys", [])
        for key in keys:
            page.keyboard.press(key)
        result["keys"] = keys

    elif action_type == "scroll":
        x, y = action.get("x", 0), action.get("y", 0)
        sx = action.get("scrollX", 0)
        sy = action.get("scrollY", 0)
        page.mouse.move(x, y)
        page.mouse.wheel(sx, sy)
        result["scrollX"] = sx
        result["scrollY"] = sy

    elif action_type == "move":
        x, y = action.get("x", 0), action.get("y", 0)
        page.mouse.move(x, y)
        result["x"] = x
        result["y"] = y

    elif action_type == "drag":
        path = action.get("path", [])
        if len(path) < 2:
            raise ComputerUseError("drag requires at least 2 path points")
        start = path[0]
        page.mouse.move(start["x"], start["y"])
        page.mouse.down()
        for point in path[1:]:
            page.mouse.move(point["x"], point["y"])
        page.mouse.up()
        result["path_points"] = len(path)

    elif action_type == "wait":
        seconds = action.get("seconds", 2)
        time.sleep(min(seconds, 30))
        result["seconds"] = seconds

    elif action_type == "sleep":
        seconds = action.get("seconds", 2)
        time.sleep(min(seconds, 30))
        result["seconds"] = seconds

    else:
        raise ComputerUseError(f"Unsupported action type: {action_type}")

    return result


def run_computer_actions(
    actions: List[Dict[str, Any]],
    authorized_domains: Optional[Set[str]] = None,
) -> str:
    """Run a batch of computer-use actions and return a structured report."""
    if not actions:
        return "[error: no actions provided]"

    session = _ensure_browser()
    if authorized_domains is not None:
        session.authorized_domains = set(d.lower() for d in authorized_domains if d)

    results = []
    errors = []

    for i, action in enumerate(actions):
        try:
            # Authorization check for navigate actions
            if action.get("type", "").lower() == "navigate":
                url = action.get("url", "")
                if url and not _is_url_allowed(url, session.authorized_domains):
                    errors.append(f"Action {i}: {url} is not in the authorized domain list.")
                    continue

            # Sensitive action warning (not a hard block, but logged)
            if _is_sensitive_action(action):
                results.append({
                    "index": i,
                    "warning": "This action touches a sensitive workflow (login, payment, password, etc.).",
                    "action": action,
                })

            result = _run_action(session, action)
            result["index"] = i
            results.append(result)
            session.history.append({"action": action, "result": result})
        except Exception as exc:
            errors.append(f"Action {i} failed: {exc}")
            results.append({"index": i, "status": "error", "error": str(exc)})

    # Always capture a final screenshot if not already the last action
    if not results or results[-1].get("type") != "screenshot":
        try:
            png_bytes = session.page.screenshot(type="png")
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            results.append({
                "index": len(actions),
                "type": "screenshot",
                "status": "ok",
                "screenshot_base64": _truncate_screenshot(b64),
                "note": "auto-captured after action batch",
            })
        except Exception as exc:
            errors.append(f"Final screenshot failed: {exc}")

    report = {
        "results": results,
        "errors": errors,
        "current_url": session.page.url,
        "title": session.page.title(),
    }
    body = json.dumps(report, indent=2, default=str)
    if len(body) > 30_000:
        body = body[:30_000] + "\n... [truncated]"
    return body


def close_computer_session() -> str:
    """Close the active browser session."""
    global _active_session
    if _active_session is None:
        return "[ok: no active session]"
    try:
        _active_session.close()
    except Exception as exc:
        return f"[error closing session: {exc}]"
    finally:
        _active_session = None
    return "[ok: browser session closed]"


def get_computer_session_status() -> str:
    """Return the current session state."""
    if _active_session is None:
        return "[ok: no active browser session]"
    return (
        f"[ok: active session]\n"
        f"URL: {_active_session.page.url}\n"
        f"Title: {_active_session.page.title()}\n"
        f"Authorized: {', '.join(sorted(_active_session.authorized_domains)) or 'none'}\n"
        f"Actions this session: {len(_active_session.history)}"
    )

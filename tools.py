"""Tool registry for the INFJ agent. Safe, sandboxed, and declarative."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from config import PROJECT_ROOT

SAFE_HOME = Path.home()
COLD_STORAGE_DIR = PROJECT_ROOT / "BLKKNIGHT_RECOVERY"
TOOL_AUDIT_PATH = PROJECT_ROOT / "tool_audit.jsonl"
RECON_DIR = PROJECT_ROOT / "recon"
MAX_FILE_READ_BYTES = 1_048_576  # 1 MB
MAX_FILE_WRITE_BYTES = 1_048_576  # 1 MB
MAX_COMMAND_CHARS = 2_000
MAX_TIMEOUT_SECONDS = 120
SHELL_TIMEOUT = 30
PYTHON_TIMEOUT = 15
NUCLEI_TIMEOUT = 300
FFUF_TIMEOUT = 300
SUBFINDER_TIMEOUT = 120
SHELL_BLOCKLIST = {
    "rm -rf /", "rm -rf /*", "sudo", "su -", "mkfs", "dd if=/dev/zero",
    ":(){ :|:& };:", "> /dev/sda", "shutdown", "reboot", "halt", "poweroff",
    "curl | sh", "curl | bash", "wget | sh", "wget | bash",
}
PYTHON_BLOCKLIST = {
    "os.system", "subprocess.", "shutil.rmtree", "Path('/').", 'Path("/").',
    "rm -rf /", "mkfs", "sudo", "socket.", "requests.post",
}


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_path(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = SAFE_HOME / target
    target = target.resolve()
    safe_home = SAFE_HOME.resolve()
    project_root = PROJECT_ROOT.resolve()
    if not (_is_relative_to(target, safe_home) or _is_relative_to(target, project_root)):
        raise PermissionError(f"Path {path} is outside the allowed directory.")
    return target


def _check_shell_safety(command: str) -> None:
    if not command or not command.strip():
        raise PermissionError("Empty shell command is not allowed.")
    if len(command) > MAX_COMMAND_CHARS:
        raise PermissionError(f"Shell command too long; max is {MAX_COMMAND_CHARS} characters.")
    lowered = command.lower()
    for blocked in SHELL_BLOCKLIST:
        # Support both exact substring and pipe-chain variations
        blocked_lower = blocked.lower()
        if blocked_lower in lowered:
            raise PermissionError(f"Blocked command pattern: {blocked}")
        # Extra heuristic: block "curl ... | bash/sh" and "wget ... | bash/sh"
        if re.search(r"\b(curl|wget)\b.*\|\s*(bash|sh)\b", lowered):
            raise PermissionError("Blocked command pattern: curl/wget | bash/sh")


def _check_python_safety(code: str) -> None:
    lowered = code.lower()
    for blocked in PYTHON_BLOCKLIST:
        if blocked.lower() in lowered:
            raise PermissionError(f"Blocked Python pattern: {blocked}")


def _coerce_timeout(timeout: int, default: int, maximum: int = MAX_TIMEOUT_SECONDS) -> int:
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        return default
    return max(1, min(timeout, maximum))


def _redact_audit_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    redacted = {}
    for key, value in (arguments or {}).items():
        if key in {"content", "code"}:
            redacted[key] = f"[{key}: {len(str(value))} chars]"
        elif key in {"api_key", "token", "password", "secret"}:
            redacted[key] = "[REDACTED]"
        else:
            text = str(value)
            redacted[key] = text[:300] + ("... [truncated]" if len(text) > 300 else "")
    return redacted


def _audit_tool_call(name: str, arguments: Dict[str, Any], result: str) -> None:
    try:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": name,
            "arguments": _redact_audit_arguments(arguments),
            "status": "error" if str(result).startswith("[error") else "ok",
            "result_preview": str(result).replace("\n", " ")[:500],
        }
        TOOL_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TOOL_AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        pass


def recent_tool_audit(limit: int = 10) -> str:
    if not TOOL_AUDIT_PATH.exists():
        return "No tool audit records yet."
    try:
        lines = TOOL_AUDIT_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        records = [json.loads(line) for line in lines if line.strip()]
    except Exception as exc:
        return f"Could not read tool audit log: {exc}"
    if not records:
        return "No tool audit records yet."
    return "\n".join(
        f"[{r.get('timestamp')}] {r.get('status')} {r.get('tool')} {r.get('arguments')}"
        for r in records
    )


def _safe_cold_storage_path(file_name: str) -> Path:
    if not file_name or Path(file_name).is_absolute():
        raise PermissionError("Cold storage file_name must be a relative file name.")
    if any(part in {"", ".", ".."} for part in Path(file_name).parts):
        raise PermissionError("Cold storage file_name cannot contain empty, current, or parent path parts.")
    target = (COLD_STORAGE_DIR / file_name).resolve()
    if not _is_relative_to(target, COLD_STORAGE_DIR.resolve()):
        raise PermissionError("Cold storage path escaped the recovery directory.")
    return target


def _validate_scan_target(target_url: str) -> str:
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("target_url must begin with http:// or https://")
    if not parsed.netloc:
        raise ValueError("target_url must include a hostname.")
    if any(char in target_url for char in ["\n", "\r", "\t", ";", "|", "&", "`", "$", "<", ">"]):
        raise ValueError("target_url contains unsafe shell/control characters.")
    return target_url


def _target_scope_hint(target_url: str) -> str:
    host = urlparse(target_url).hostname or ""
    if host in {"localhost"} or host.endswith(".local"):
        return "local"
    try:
        ip = ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return "private-network"
    except ValueError:
        pass
    return "external"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_read_file(path: str, offset: int = 0, max_lines: int = 200) -> str:
    """Read a text file from the allowed directory."""
    target = _resolve_path(path)
    if not target.exists():
        return f"[error: file not found: {path}]"
    if target.stat().st_size > MAX_FILE_READ_BYTES:
        return f"[error: file too large ({target.stat().st_size} bytes), max is {MAX_FILE_READ_BYTES}]"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if offset:
            lines = lines[offset:]
        if max_lines:
            lines = lines[:max_lines]
        return "\n".join(lines)
    except Exception as exc:
        return f"[error reading file: {exc}]"


def tool_write_file(path: str, content: str) -> str:
    """Write content to a file in the allowed directory."""
    target = _resolve_path(path)
    if len(content.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
        return f"[error: content too large, max is {MAX_FILE_WRITE_BYTES} bytes]"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"[ok: wrote {len(content)} chars to {path}]"
    except Exception as exc:
        return f"[error writing file: {exc}]"


def tool_shell(command: str, timeout: int = SHELL_TIMEOUT) -> str:
    """Run a shell command inside the safe home directory with a timeout.
    Uses shell=False for security — no pipes, redirects, or shell expansions."""
    timeout = _coerce_timeout(timeout, SHELL_TIMEOUT)
    try:
        _check_shell_safety(command)
    except PermissionError as exc:
        return f"[error: {exc}]"
    try:
        import shlex
        argv = shlex.split(command)
        if not argv:
            return "[error: empty command after parsing]"
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(SAFE_HOME),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        # Truncate very long output
        if len(output) > 20_000:
            output = output[:20_000] + "\n... [truncated]"
        return output or "[ok: no output]"
    except subprocess.TimeoutExpired:
        return f"[error: command timed out after {timeout}s]"
    except Exception as exc:
        return f"[error: {exc}]"


def tool_execute_terminal_command(command: str, timeout: int = SHELL_TIMEOUT) -> str:
    """Compatibility wrapper for terminal command plugins."""
    return tool_shell(command, timeout=timeout)


def tool_write_to_cold_storage(file_name: str, content: str) -> str:
    """Write notes or artifacts into the bot's project-local recovery directory."""
    try:
        target = _safe_cold_storage_path(file_name)
    except PermissionError as exc:
        return f"[error: {exc}]"
    if len(content.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
        return f"[error: content too large, max is {MAX_FILE_WRITE_BYTES} bytes]"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        relative = target.relative_to(COLD_STORAGE_DIR.resolve())
        return f"[ok: wrote {len(content)} chars to {relative}]"
    except Exception as exc:
        return f"[error writing cold storage file: {exc}]"


def _ensure_wordlist(wordlist: str) -> Optional[str]:
    if not wordlist or not wordlist.strip():
        wordlist = "/usr/share/wordlists/dirb/common.txt"
    if Path(wordlist).exists():
        return wordlist
    fallbacks = [
        "/usr/share/wordlists/dirb/common.txt",
        "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
        "/usr/share/seclists/Discovery/Web-Content/common.txt",
        str(PROJECT_ROOT / "wordlists" / "common.txt"),
    ]
    for fb in fallbacks:
        if Path(fb).exists():
            return fb
    return None


def _sanitize_ffuf_output(raw: str) -> str:
    """Strip noise and focus on discovered endpoints with status codes."""
    lines = []
    for line in raw.splitlines():
        if re.search(r"\[Status:\s*\d+", line):
            lines.append(line.strip())
    return "\n".join(lines) if lines else raw


def _save_recon_artifact(domain: str, tool: str, content: str) -> Path:
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = RECON_DIR / f"{domain}_{tool}_{stamp}.txt"
    out_file.write_text(content, encoding="utf-8")
    return out_file


def tool_fuzz_directories(
    target_url: str,
    authorization_confirmed: bool = False,
    wordlist: str = "/usr/share/wordlists/dirb/common.txt",
    timeout: int = FFUF_TIMEOUT,
) -> str:
    """Run ffuf directory fuzzing against an explicitly authorized target. Maps exposed attack surface for hardening."""
    if not authorization_confirmed:
        return (
            "[error: authorization_confirmed must be true. Only scan targets you own, "
            "manage, or have written permission to test. Use /authorize <domain> first.]"
        )
    try:
        target_url = _validate_scan_target(target_url)
    except ValueError as exc:
        return f"[error: {exc}]"

    wl = _ensure_wordlist(wordlist)
    if wl is None:
        return (
            "[error: wordlist not found. Install a wordlist (e.g., apt install wordlists or seclists) "
            "or place one at ./wordlists/common.txt]"
        )

    scope = _target_scope_hint(target_url)
    ffuf_path = shutil.which("ffuf")
    if not ffuf_path:
        return "[error: ffuf is not installed or not on PATH]"

    command = (
        f"{ffuf_path} -w {wl} -u {target_url.rstrip('/')}/FUZZ "
        f"-mc 200,204,301,302,307,401,403,405,500 "
        f"-t 50 -s"
    )

    try:
        timeout = _coerce_timeout(timeout, FFUF_TIMEOUT, FFUF_TIMEOUT)
        result = tool_shell(command, timeout=timeout)
    except Exception as exc:
        return f"[error: ffuf failed: {exc}]"

    domain = urlparse(target_url).hostname or "unknown"
    cleaned = _sanitize_ffuf_output(result)
    artifact = _save_recon_artifact(
        domain,
        "dirs",
        f"# Directory fuzz: {target_url}\n# Wordlist: {wl}\n# Scope: {scope}\n\n{result}",
    )

    summary = f"Directory fuzz complete for {domain} ({scope}).\nResult saved to: {artifact}\n\n"
    if cleaned.strip():
        summary += f"Discovered endpoints:\n{cleaned}\n\n"
        summary += (
            "Next step: review exposed paths, remove unnecessary endpoints, "
            "enable auth, and add rate limiting."
        )
    else:
        summary += "No responsive endpoints found with this wordlist."
    return summary


def tool_enumerate_subdomains(
    domain: str,
    authorization_confirmed: bool = False,
    timeout: int = SUBFINDER_TIMEOUT,
) -> str:
    """Run subfinder against an explicitly authorized domain. Expands known attack surface for defensive review."""
    if not authorization_confirmed:
        return (
            "[error: authorization_confirmed must be true. Only scan targets you own, "
            "manage, or have written permission to test. Use /authorize <domain> first.]"
        )

    clean = domain.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].lower()
    if not clean:
        return "[error: domain is empty]"

    subfinder_path = shutil.which("subfinder")
    if not subfinder_path:
        return "[error: subfinder is not installed or not on PATH]"

    command = f"{subfinder_path} -d {clean} -silent"

    try:
        timeout = _coerce_timeout(timeout, SUBFINDER_TIMEOUT, SUBFINDER_TIMEOUT)
        result = tool_shell(command, timeout=timeout)
    except Exception as exc:
        return f"[error: subfinder failed: {exc}]"

    scope = _target_scope_hint(f"http://{clean}")
    artifact = _save_recon_artifact(
        clean,
        "subdomains",
        f"# Subdomain enum: {clean}\n# Scope: {scope}\n\n{result}",
    )

    if result.strip():
        return (
            f"Subdomain enumeration complete for {clean} ({scope}).\n"
            f"Result saved to: {artifact}\n\n"
            f"Found subdomains:\n{result}\n\n"
            "Next step: inventory which subdomains are intentional, decommission stale ones, "
            "and ensure DNS monitoring alerts on unexpected additions."
        )
    return (
        f"Subdomain enumeration complete for {clean} ({scope}).\n"
        f"Result saved to: {artifact}\n\n"
        "No subdomains discovered. Consider checking DNS history or certificate transparency logs."
    )


def tool_computer_use(
    actions: List[Dict[str, Any]],
    authorization_confirmed: bool = False,
    authorized_domains: Optional[List[str]] = None,
) -> str:
    """Run a batch of browser UI actions (navigate, click, type, scroll, screenshot, etc.).
    Requires authorization. Screenshots are returned as base64 in the JSON report."""
    if not authorization_confirmed:
        return (
            "[error: authorization_confirmed must be true. Only automate interfaces you own, "
            "manage, or have explicit permission to interact with. Use /authorize <domain> first.]"
        )
    try:
        from computer_use import run_computer_actions
        domains = set(authorized_domains) if authorized_domains else set()
        return run_computer_actions(actions, authorized_domains=domains)
    except Exception as exc:
        return f"[error: computer use failed: {exc}]"


def tool_computer_session_status() -> str:
    """Check the active browser session state."""
    try:
        from computer_use import get_computer_session_status
        return get_computer_session_status()
    except Exception as exc:
        return f"[error: {exc}]"


def tool_close_computer_session() -> str:
    """Close the active browser session."""
    try:
        from computer_use import close_computer_session
        return close_computer_session()
    except Exception as exc:
        return f"[error: {exc}]"


def tool_run_nuclei_scan(
    target_url: str,
    authorization_confirmed: bool = False,
    scope_note: str = "",
    timeout: int = NUCLEI_TIMEOUT,
) -> str:
    """Run a high/critical Nuclei scan against an explicitly authorized target."""
    if not authorization_confirmed:
        return (
            "[error: authorization_confirmed must be true. Only scan targets you own, "
            "manage, or have written permission to test. Use /authorize <domain> first.]"
        )
    try:
        target_url = _validate_scan_target(target_url)
    except ValueError as exc:
        return f"[error: {exc}]"
    scope = _target_scope_hint(target_url)
    if scope == "external" and not scope_note.strip():
        return "[error: external targets require a short scope_note describing your authorization.]"
    nuclei_path = shutil.which("nuclei")
    if not nuclei_path:
        return "[error: nuclei is not installed or not on PATH]"

    with tempfile.NamedTemporaryFile("w+", suffix=".jsonl", delete=False) as output_file:
        output_path = Path(output_file.name)

    command = [
        nuclei_path,
        "-u",
        target_url,
        "-severity",
        "high,critical",
        "-jsonl",
        "-o",
        str(output_path),
    ]
    try:
        timeout = _coerce_timeout(timeout, NUCLEI_TIMEOUT, NUCLEI_TIMEOUT)
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if not output_path.exists():
            stderr = result.stderr.strip() or "scan did not create an output file"
            return f"[error: nuclei scan failed: {stderr}]"
        lines = [line for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if not lines:
            stderr = f"\n[stderr]: {result.stderr.strip()}" if result.stderr.strip() else ""
            return f"[ok: scan complete for {scope} target; no high/critical findings]{stderr}"
        findings = []
        for line in lines[:50]:
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                findings.append({"raw": line})
        body = json.dumps(findings, indent=2)
        if len(body) > 20_000:
            body = body[:20_000] + "\n... [truncated]"
        return f"[ok: high/critical findings]\n{body}"
    except subprocess.TimeoutExpired:
        return f"[error: nuclei scan timed out after {timeout}s]"
    except Exception as exc:
        return f"[error during nuclei scan: {exc}]"
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        with DDGS(timeout=20) as ddgs:
            results = ddgs.text(query, max_results=max(max_results, 1))
        if not results:
            return "[no results found]"
        lines = []
        for i, r in enumerate(results[:max_results], 1):
            title = r.get("title", "No title")
            href = r.get("href", "No link")
            body = r.get("body", "")[:240]
            lines.append(f"{i}. {title}\n   {href}\n   {body}")
        return "\n\n".join(lines)
    except Exception as exc:
        return f"[error searching: {exc}]"


def tool_run_python(code: str, timeout: int = PYTHON_TIMEOUT) -> str:
    """Execute Python code in a sandboxed subprocess with matplotlib/pandas support.
    Returns stdout/stderr plus any generated plots as base64 PNG images."""
    timeout = _coerce_timeout(timeout, PYTHON_TIMEOUT)
    # Strip markdown fences if present
    code = re.sub(r"^```(?:python)?\s*", "", code.strip())
    code = re.sub(r"\s*```$", "", code)
    if not code.strip():
        return "[error: no code provided]"
    try:
        _check_python_safety(code)
    except PermissionError as exc:
        return f"[error: {exc}]"

    # Wrap user code so we can capture matplotlib figures
    script = f"""
import sys, traceback, io, base64, json

# Setup matplotlib for headless use
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Collect stdout/stderr
stdout_buf = io.StringIO()
stderr_buf = io.StringIO()
old_stdout, old_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = stdout_buf, stderr_buf

# Restricted builtins — no os, sys, subprocess, open, etc.
safe_builtins = {{
    "abs": abs, "all": all, "any": any, "ascii": ascii,
    "bin": bin, "bool": bool, "bytearray": bytearray, "bytes": bytes,
    "chr": chr, "complex": complex, "dict": dict, "divmod": divmod,
    "enumerate": enumerate, "filter": filter, "float": float,
    "format": format, "frozenset": frozenset, "hasattr": hasattr,
    "hash": hash, "hex": hex, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "list": list,
    "map": map, "max": max, "min": min, "next": next, "oct": oct,
    "ord": ord, "pow": pow, "print": print, "range": range,
    "repr": repr, "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "BaseException": BaseException, "Exception": Exception,
    "ArithmeticError": ArithmeticError, "LookupError": LookupError,
    "IndexError": IndexError, "KeyError": KeyError, "TypeError": TypeError,
    "ValueError": ValueError, "ZeroDivisionError": ZeroDivisionError,
    "NameError": NameError, "AttributeError": AttributeError,
    "StopIteration": StopIteration, "RuntimeError": RuntimeError,
    "IOError": IOError, "OSError": OSError,
}}
sandbox_globals = {{"__name__": "__main__", "__builtins__": safe_builtins, "plt": plt}}
try:
    exec({repr(code)}, sandbox_globals)
except Exception as e:
    print("[runtime error]", e, file=sys.stderr)
    traceback.print_exc()

sys.stdout, sys.stderr = old_stdout, old_stderr

# Capture any matplotlib figures as base64
figures = []
for fig_num in plt.get_fignums():
    fig = plt.figure(fig_num)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    figures.append(base64.b64encode(buf.read()).decode('utf-8'))
plt.close('all')

result = {{
    "stdout": stdout_buf.getvalue(),
    "stderr": stderr_buf.getvalue(),
    "figures": figures,
}}
print(json.dumps(result))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(SAFE_HOME),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Parse the JSON result from the script
        try:
            data = json.loads(result.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            # Fallback to raw output if JSON parsing fails
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            if len(output) > 20_000:
                output = output[:20_000] + "\n... [truncated]"
            return output or "[ok: no output]"

        lines = []
        if data.get("stdout", "").strip():
            lines.append(data["stdout"].strip())
        if data.get("stderr", "").strip():
            lines.append(f"[stderr]: {data['stderr'].strip()}")
        figures = data.get("figures", [])
        if figures:
            lines.append(f"[generated {len(figures)} figure(s)]")
            for i, fig_b64 in enumerate(figures[:3], 1):
                lines.append(f"[figure {i} base64: {fig_b64[:200]}...]")
        output = "\n".join(lines) if lines else "[ok: no output]"
        if len(output) > 20_000:
            output = output[:20_000] + "\n... [truncated]"
        return output
    except subprocess.TimeoutExpired:
        return f"[error: python execution timed out after {timeout}s]"
    except Exception as exc:
        return f"[error: {exc}]"


def tool_call_api(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    authorization_confirmed: bool = False,
    timeout: int = 30,
) -> str:
    """Make an HTTP request to an authorized external API.
    Requires authorization for external domains."""
    if not authorization_confirmed:
        return (
            "[error: authorization_confirmed must be true. Only call APIs you own, "
            "manage, or have explicit permission to use.]"
        )
    try:
        target_url = _validate_scan_target(url)
    except ValueError as exc:
        return f"[error: {exc}]"

    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        return f"[error: unsupported HTTP method: {method}]"

    scope = _target_scope_hint(target_url)
    if scope == "external" and not authorization_confirmed:
        return "[error: external API calls require authorization_confirmed=True.]"

    # Block internal network unless explicitly allowed
    host = urlparse(target_url).hostname or ""
    try:
        from ipaddress import ip_address
        ip = ip_address(host)
        if ip.is_private and not authorization_confirmed:
            return "[error: internal network API calls require authorization.]"
    except ValueError:
        pass

    try:
        import requests
        timeout = _coerce_timeout(timeout, 30, 120)
        req_headers = headers or {}
        # Block sending of common auth headers without extra caution
        sensitive_headers = {"authorization", "cookie", "x-api-key", "api-key"}
        for h in req_headers:
            if h.lower() in sensitive_headers and not authorization_confirmed:
                return f"[error: sending sensitive header '{h}' requires authorization.]"

        kwargs = {"url": target_url, "method": method, "headers": req_headers, "timeout": timeout}
        if body and method in {"POST", "PUT", "PATCH"}:
            kwargs["data"] = body.encode("utf-8") if isinstance(body, str) else body

        resp = requests.request(**kwargs)
        # Truncate large responses
        content = resp.text
        if len(content) > 15_000:
            content = content[:15_000] + "\n... [truncated]"
        status_line = f"Status: {resp.status_code}\nHeaders: {dict(resp.headers)}"
        return f"{status_line}\n\n{content}"
    except Exception as exc:
        return f"[error: API call failed: {exc}]"


def tool_get_datetime() -> str:
    """Return the current date and time."""
    return datetime.now().isoformat()


def tool_list_directory(path: str = ".") -> str:
    """List files in a directory."""
    target = _resolve_path(path)
    if not target.exists():
        return f"[error: directory not found: {path}]"
    if not target.is_dir():
        return f"[error: not a directory: {path}]"
    try:
        items = []
        for entry in target.iterdir():
            prefix = "d" if entry.is_dir() else "f"
            size = "-" if entry.is_dir() else entry.stat().st_size
            items.append(f"[{prefix}] {entry.name:40s} {size}")
        return "\n".join(sorted(items))
    except Exception as exc:
        return f"[error: {exc}]"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Callable] = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "shell": tool_shell,
    "execute_terminal_command": tool_execute_terminal_command,
    "write_to_cold_storage": tool_write_to_cold_storage,
    "fuzz_directories": tool_fuzz_directories,
    "enumerate_subdomains": tool_enumerate_subdomains,
    "computer_use": tool_computer_use,
    "computer_session_status": tool_computer_session_status,
    "close_computer_session": tool_close_computer_session,
    "call_api": tool_call_api,
    "run_nuclei_scan": tool_run_nuclei_scan,
    "web_search": tool_web_search,
    "run_python": tool_run_python,
    "get_datetime": tool_get_datetime,
    "list_directory": tool_list_directory,
}

TOOL_SCHEMAS = {
    "read_file": {
        "description": "Read a text file. Provide a relative or absolute path.",
        "parameters": {
            "path": {"type": "string", "description": "File path to read."},
            "offset": {"type": "integer", "description": "Line offset to start from.", "default": 0},
            "max_lines": {"type": "integer", "description": "Maximum lines to return.", "default": 200},
        },
        "required": ["path"],
    },
    "write_file": {
        "description": "Write text to a file. Creates parent directories if needed.",
        "parameters": {
            "path": {"type": "string", "description": "File path to write."},
            "content": {"type": "string", "description": "Text content to write."},
        },
        "required": ["path", "content"],
    },
    "shell": {
        "description": "Run a shell command in the home directory with a timeout.",
        "parameters": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
        },
        "required": ["command"],
    },
    "execute_terminal_command": {
        "description": "Compatibility terminal tool. Runs a guarded shell command in the home directory with the same safety rules as shell.",
        "parameters": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
        },
        "required": ["command"],
    },
    "write_to_cold_storage": {
        "description": "Write notes, drafts, or artifacts into the project-local BLKKNIGHT_RECOVERY directory.",
        "parameters": {
            "file_name": {"type": "string", "description": "Relative file name under BLKKNIGHT_RECOVERY."},
            "content": {"type": "string", "description": "Text content to save."},
        },
        "required": ["file_name", "content"],
    },
    "fuzz_directories": {
        "description": "Run ffuf directory fuzzing against an explicitly authorized target. Maps exposed attack surface for hardening.",
        "parameters": {
            "target_url": {"type": "string", "description": "Authorized http:// or https:// target URL."},
            "authorization_confirmed": {"type": "boolean", "description": "Must be true only when Jude has authorization for this target.", "default": False},
            "wordlist": {"type": "string", "description": "Path to wordlist file.", "default": "/usr/share/wordlists/dirb/common.txt"},
            "timeout": {"type": "integer", "description": "Timeout in seconds, capped at 300.", "default": 300},
        },
        "required": ["target_url", "authorization_confirmed"],
    },
    "enumerate_subdomains": {
        "description": "Run subfinder against an explicitly authorized domain. Expands known attack surface for defensive review.",
        "parameters": {
            "domain": {"type": "string", "description": "Authorized domain to enumerate (e.g., example.com)."},
            "authorization_confirmed": {"type": "boolean", "description": "Must be true only when Jude has authorization for this target.", "default": False},
            "timeout": {"type": "integer", "description": "Timeout in seconds, capped at 120.", "default": 120},
        },
        "required": ["domain", "authorization_confirmed"],
    },
    "computer_use": {
        "description": "Run a batch of browser UI actions (navigate, click, type, scroll, screenshot, etc.). Requires authorization. Returns a JSON report with screenshots.",
        "parameters": {
            "actions": {
                "type": "array",
                "description": "List of action objects. Each action has a 'type' key and relevant params. Types: navigate, click, double_click, type, keypress, scroll, move, drag, wait, screenshot. Example: [{\"type\": \"navigate\", \"url\": \"https://example.com\"}, {\"type\": \"screenshot\"}]",
            },
            "authorization_confirmed": {"type": "boolean", "description": "Must be true only when Jude has authorization for this target.", "default": False},
            "authorized_domains": {"type": "array", "description": "Optional list of authorized domains for navigation.", "default": []},
        },
        "required": ["actions", "authorization_confirmed"],
    },
    "computer_session_status": {
        "description": "Check the active browser session state (URL, title, action count).",
        "parameters": {},
        "required": [],
    },
    "close_computer_session": {
        "description": "Close the active browser session and free resources.",
        "parameters": {},
        "required": [],
    },
    "call_api": {
        "description": "Make an HTTP request to an authorized external API. Requires authorization.",
        "parameters": {
            "url": {"type": "string", "description": "Target URL (http:// or https://)."},
            "method": {"type": "string", "description": "HTTP method.", "default": "GET"},
            "headers": {"type": "object", "description": "Optional request headers.", "default": {}},
            "body": {"type": "string", "description": "Optional request body.", "default": ""},
            "authorization_confirmed": {"type": "boolean", "description": "Must be true for external APIs.", "default": False},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
        },
        "required": ["url", "authorization_confirmed"],
    },
    "run_nuclei_scan": {
        "description": "Run a high/critical Nuclei scan against a target you own or are explicitly authorized to test.",
        "parameters": {
            "target_url": {"type": "string", "description": "Authorized http:// or https:// target URL."},
            "authorization_confirmed": {"type": "boolean", "description": "Must be true only when Jude has authorization for this target.", "default": False},
            "scope_note": {"type": "string", "description": "Short authorization note required for external targets.", "default": ""},
            "timeout": {"type": "integer", "description": "Timeout in seconds, capped at 300.", "default": 300},
        },
        "required": ["target_url", "authorization_confirmed"],
    },
    "web_search": {
        "description": "Search the web using DuckDuckGo.",
        "parameters": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {"type": "integer", "description": "Number of results.", "default": 5},
        },
        "required": ["query"],
    },
    "run_python": {
        "description": "Execute Python code in a sandboxed subprocess.",
        "parameters": {
            "code": {"type": "string", "description": "Python code to run."},
            "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 15},
        },
        "required": ["code"],
    },
    "get_datetime": {
        "description": "Get the current date and time.",
        "parameters": {},
        "required": [],
    },
    "list_directory": {
        "description": "List files in a directory.",
        "parameters": {
            "path": {"type": "string", "description": "Directory path.", "default": "."},
        },
        "required": [],
    },
}


def format_tool_inventory() -> str:
    lines = ["Tools:"]
    for name, schema in TOOL_SCHEMAS.items():
        required = ", ".join(schema["required"]) if schema["required"] else "none"
        lines.append(f"- {name}: {schema['description']} Required: {required}.")
    lines.append("")
    lines.append("Recent audit:")
    lines.append(recent_tool_audit())
    return "\n".join(lines)


def build_tool_prompt() -> str:
    """Build a prompt snippet describing available tools."""
    lines = ["AVAILABLE TOOLS:", "When you need a tool, output ONE JSON block like this:", ""]
    for name, schema in TOOL_SCHEMAS.items():
        params = ", ".join(schema["required"]) if schema["required"] else "none"
        lines.append(f'- {name}: {schema["description"]} (required params: {params})')
    lines.append("")
    lines.append("Format your tool call exactly as:")
    lines.append('```tool\n{"name": "tool_name", "arguments": {"key": "value"}}\n```')
    lines.append("")
    lines.append("Wait for the tool result before continuing. Do not guess results.")
    return "\n".join(lines)


def execute_tool_call(raw_json: str) -> str:
    """Parse and execute a tool call JSON string."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return f"[error: invalid tool JSON: {exc}]"
    name = payload.get("name")
    arguments = payload.get("arguments", {})
    if name not in TOOL_REGISTRY:
        return f"[error: unknown tool '{name}']"
    func = TOOL_REGISTRY[name]
    try:
        result = func(**arguments)
        _audit_tool_call(name, arguments, result)
        return result
    except TypeError as exc:
        result = f"[error: bad arguments for {name}: {exc}]"
        _audit_tool_call(name, arguments, result)
        return result
    except Exception as exc:
        result = f"[error executing {name}: {exc}]"
        _audit_tool_call(name, arguments, result)
        return result


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Extract tool call JSON blocks from model output."""
    calls = []
    pattern = re.compile(r"```tool\s*\n(.*?)\n```", re.S)
    for match in pattern.finditer(text):
        raw = match.group(1).strip()
        try:
            calls.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return calls


if __name__ == "__main__":
    print(build_tool_prompt())
    print("\n--- sample execution ---")
    print(tool_get_datetime())

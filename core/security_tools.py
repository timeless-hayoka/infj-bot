"""Authorization gate for recon wrappers layered on core tools."""

from __future__ import annotations

from urllib.parse import urlparse

from tools import tool_enumerate_subdomains, tool_fuzz_directories, tool_run_nuclei_scan


def _hostname(target: str) -> str:
    t = target.strip()
    if "://" in t:
        host = urlparse(t).hostname
        return (host or "").lower()
    return t.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].lower()


def is_authorized(target: str, authorized: set[str]) -> bool:
    if not authorized:
        return False
    host = _hostname(target)
    if not host:
        return False
    allowed = {a.lower() for a in authorized}
    if host in allowed:
        return True
    return any(host == a or host.endswith("." + a) for a in allowed)


def _reject(target: str) -> str:
    return f"[error: {target} is not in the authorized targets list.]"


def tool_recon_summary(target_url: str, authorized: set[str] | None = None) -> str:
    authorized = authorized or set()
    if not is_authorized(target_url, authorized):
        return _reject(target_url)
    return tool_run_nuclei_scan(
        target_url,
        authorization_confirmed=True,
        scope_note="authorized recon summary",
    )


def tool_recon_enum(domain: str, authorized: set[str] | None = None) -> str:
    authorized = authorized or set()
    if not is_authorized(domain, authorized):
        return _reject(domain)
    return tool_enumerate_subdomains(domain, authorization_confirmed=True)


def tool_recon_fuzz(target_url: str, authorized: set[str] | None = None) -> str:
    authorized = authorized or set()
    if not is_authorized(target_url, authorized):
        return _reject(target_url)
    return tool_fuzz_directories(target_url, authorization_confirmed=True)

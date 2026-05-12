"""
Security reconnaissance helpers for the INFJ bot.

This module re-exports the hardened reconnaissance tools from tools.py
with a thin wrapper that accepts an `authorized` set for command-level
authorization (used by /recon commands).

All defensive scan tools require authorization_confirmed=True when called
by the model, and require the domain to be in the session authorized set
when called via slash commands.
"""

from tools import (
    tool_enumerate_subdomains,
    tool_fuzz_directories,
)


def _domain_from_url(url: str) -> str:
    """Extract the bare domain from a URL or domain string."""
    url = url.replace("https://", "").replace("http://", "")
    return url.split("/")[0].split(":")[0].lower()


def is_authorized(target: str, authorized: set) -> bool:
    """Check whether a target (URL or domain) is in the authorized set."""
    target_domain = _domain_from_url(target)
    return target_domain in authorized


def tool_recon_summary(
    target_url: str,
    authorized: set,
    timeout_dirs: int = 300,
    timeout_subs: int = 120,
) -> str:
    """
    Run a combined reconnaissance pass (directory fuzz + subdomain enum)
    against a target that must already be in the authorized set.
    Returns a defensive summary and saves artifacts to ./recon/.
    """
    domain = _domain_from_url(target_url)
    if not is_authorized(target_url, authorized):
        return (
            f"[error: {domain} is not in the authorized targets list. "
            f"Use /authorize <domain> first.]"
        )

    results = []

    results.append(f"[DIR FUZZ] {target_url}")
    dir_result = tool_fuzz_directories(
        target_url=target_url,
        authorization_confirmed=True,
        timeout=timeout_dirs,
    )
    results.append(dir_result)

    results.append(f"\n[SUBDOMAIN ENUM] {domain}")
    sub_result = tool_enumerate_subdomains(
        domain=domain,
        authorization_confirmed=True,
        timeout=timeout_subs,
    )
    results.append(sub_result)

    return "\n".join(results)


def tool_recon_enum(
    domain: str,
    authorized: set,
    timeout: int = 120,
) -> str:
    """
    Enumerate subdomains for a single authorized domain.
    """
    if not is_authorized(domain, authorized):
        return (
            f"[error: {domain} is not in the authorized targets list. "
            f"Use /authorize <domain> first.]"
        )
    return tool_enumerate_subdomains(
        domain=domain,
        authorization_confirmed=True,
        timeout=timeout,
    )


def tool_recon_fuzz(
    target_url: str,
    authorized: set,
    timeout: int = 300,
) -> str:
    """
    Run directory fuzzing for a single authorized target URL.
    """
    if not is_authorized(target_url, authorized):
        return (
            f"[error: {target_url} is not in the authorized targets list. "
            f"Use /authorize <domain> first.]"
        )
    return tool_fuzz_directories(
        target_url=target_url,
        authorization_confirmed=True,
        timeout=timeout,
    )

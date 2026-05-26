"""Bugcrowd API v4 client with built-in rate limiting and safe defaults."""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib import request
from urllib.error import HTTPError


BUGCROWD_API_BASE = "https://api.bugcrowd.com"
DEFAULT_RATE_LIMIT_DELAY = 1.0  # seconds between requests


@dataclass
class BugcrowdProgram:
    uuid: str
    name: str
    slug: str
    url: str
    status: str
    rewards: str = ""
    scope: List[Dict[str, Any]] = field(default_factory=list)
    oos: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BugcrowdSubmission:
    uuid: str
    title: str
    status: str
    severity: str
    program_uuid: str
    asset: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class BugcrowdClient:
    """
    Bugcrowd API client with polite rate limiting.
    Set BUGCROWD_API_KEY in your environment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
    ):
        self.api_key = api_key or os.getenv("BUGCROWD_API_KEY", "")
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/vnd.bugcrowd+json",
            "Content-Type": "application/json",
        }

    def _request(
        self, method: str, path: str, data: Optional[bytes] = None
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("BUGCROWD_API_KEY is not set. Add it to your .env file.")

        # Polite rate limiting
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        url = f"{BUGCROWD_API_BASE}{path}"
        req = request.Request(url, method=method, headers=self._headers(), data=data)
        self._last_request_time = time.time()

        try:
            with request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            raise RuntimeError(f"Bugcrowd API {exc.code}: {body}") from exc

    def list_programs(self) -> List[BugcrowdProgram]:
        """Fetch all programs the researcher is enrolled in."""
        resp = self._request("GET", "/programs")
        programs = []
        for item in resp.get("data", []):
            attr = item.get("attributes", {})
            programs.append(
                BugcrowdProgram(
                    uuid=item.get("id", ""),
                    name=attr.get("name", ""),
                    slug=attr.get("slug", ""),
                    url=attr.get("url", ""),
                    status=attr.get("status", ""),
                    rewards=attr.get("rewards_text", ""),
                    raw=item,
                )
            )
        return programs

    def get_program(self, program_uuid: str) -> BugcrowdProgram:
        """Fetch full program details including scope."""
        resp = self._request("GET", f"/programs/{program_uuid}")
        data = resp.get("data", {})
        attr = data.get("attributes", {})

        # Fetch target groups for scope
        scope_items = []
        oos_items = []
        try:
            tg_resp = self._request("GET", f"/programs/{program_uuid}/target_groups")
            for tg in tg_resp.get("data", []):
                tg_attr = tg.get("attributes", {})
                targets = tg.get("relationships", {}).get("targets", {}).get("data", [])
                for t in targets:
                    t_resp = self._request("GET", f"/targets/{t.get('id', '')}")
                    t_data = t_resp.get("data", {})
                    t_attr = t_data.get("attributes", {})
                    entry = {
                        "name": t_attr.get("name", ""),
                        "category": t_attr.get("category", ""),
                        "uri": t_attr.get("uri", ""),
                        "priority": tg_attr.get("priority", ""),
                    }
                    if tg_attr.get("in_scope", True):
                        scope_items.append(entry)
                    else:
                        oos_items.append(entry)
        except Exception:
            pass  # Graceful fallback if target_groups endpoint fails

        return BugcrowdProgram(
            uuid=data.get("id", program_uuid),
            name=attr.get("name", ""),
            slug=attr.get("slug", ""),
            url=attr.get("url", ""),
            status=attr.get("status", ""),
            rewards=attr.get("rewards_text", ""),
            scope=scope_items,
            oos=oos_items,
            raw=data,
        )

    def list_submissions(
        self, program_uuid: Optional[str] = None
    ) -> List[BugcrowdSubmission]:
        """Fetch submissions. Optionally filter by program."""
        path = "/submissions"
        if program_uuid:
            path = f"/programs/{program_uuid}/submissions"
        resp = self._request("GET", path)
        submissions = []
        for item in resp.get("data", []):
            attr = item.get("attributes", {})
            submissions.append(
                BugcrowdSubmission(
                    uuid=item.get("id", ""),
                    title=attr.get("title", ""),
                    status=attr.get("status", ""),
                    severity=attr.get("severity", ""),
                    program_uuid=item.get("relationships", {})
                    .get("program", {})
                    .get("data", {})
                    .get("id", ""),
                    raw=item,
                )
            )
        return submissions

    def create_submission(
        self,
        program_uuid: str,
        title: str,
        vulnerability_type: str,
        severity: str,
        description: str,
        reproduction: str,
        impact: str,
        asset: str = "",
    ) -> str:
        """Create a new submission on Bugcrowd. Returns submission UUID."""
        payload = {
            "data": {
                "type": "submission",
                "attributes": {
                    "title": title,
                    "vrt_lineage": vulnerability_type.split(" > ")
                    if " > " in vulnerability_type
                    else [vulnerability_type],
                    "severity": severity.lower(),
                    "description": description,
                    "reproduction": reproduction,
                    "impact": impact,
                },
                "relationships": {
                    "program": {"data": {"id": program_uuid, "type": "program"}}
                },
            }
        }
        if asset:
            payload["data"]["attributes"]["asset"] = asset

        resp = self._request(
            "POST", "/submissions", data=json.dumps(payload).encode("utf-8")
        )
        return resp.get("data", {}).get("id", "")

    def health(self) -> str:
        """Quick API health check."""
        if not self.api_key:
            return "❌ BUGCROWD_API_KEY not set"
        try:
            resp = self._request("GET", "/programs")
            count = len(resp.get("data", []))
            return f"✅ Bugcrowd API healthy — {count} program(s) visible"
        except Exception as exc:
            return f"❌ Bugcrowd API error: {exc}"

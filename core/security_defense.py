"""Security defense layer for DRIFT.

Scans user input for four attack categories before any LLM generation:
1. Prompt injection — attempts to override system instructions
2. Data exfiltration — attempts to extract secrets, memory, or system state
3. Agent tool misuse — attempts to weaponize autonomous tool calls
4. Memory / context manipulation — attempts to corrupt or bypass context

Design goals:
- Fast: pure regex/heuristic, no LLM round-trip
- Transparent: scores and logs every check
- Fail-closed: high-confidence attacks are blocked before reaching the brain
- Non-paranoid: low-confidence inputs pass through with a warning flag
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from infj_bot.core.config import PROJECT_ROOT

# ── Audit log ───────────────────────────────────────────────────────
SECURITY_AUDIT_PATH = Path(PROJECT_ROOT) / "security_audit.jsonl"


def _log_detection(
    category: str,
    input_text: str,
    score: float,
    matched: List[str],
    action: str,
) -> None:
    line = json.dumps(
        {
            "ts": datetime.now().isoformat(),
            "category": category,
            "score": round(score, 3),
            "matched": matched,
            "action": action,
            "input_preview": input_text[:200],
        },
        default=str,
    )
    try:
        SECURITY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SECURITY_AUDIT_PATH, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# ── Pattern databases ───────────────────────────────────────────────

# Prompt injection: attempts to override system instructions, role, or constraints
PROMPT_INJECTION_PATTERNS = {
    # High-confidence: direct override attempts
    "ignore_previous": r"ignore\s+(all\s+)?(previous|prior|earlier)\s+(instructions|commands|prompts|directives)",
    "system_override": r"(your\s+new\s+|ignore\s+your\s+|forget\s+your\s+)(system\s+prompt|instructions|directives|rules|constraints)",
    "role_override": r"(you\s+are\s+now\s+|from\s+now\s+on\s+you\s+are\s+|act\s+as\s+|pretend\s+to\s+be\s+|switch\s+to\s+|become\s+)(a\s+)?(DAN|developer|hacker|admin|root|unrestricted|uncensored|jailbroken)",
    "dan_mode": r"\bDAN\b|do\s+anything\s+now|jailbreak|mode\s*:\s*developer|developer\s*mode",
    "delimiter_injection": r"```\s*system|```\s*instructions?|<system>|</system>|\[system\]|\[instructions\]|\{\{system\}\}",
    "leak_prompt": r"(repeat\s+back\s+your|output\s+your|show\s+your|what\s+are\s+your|print\s+your)\s+(system\s+prompt|instructions?|directives?|rules?|initial\s+prompt)",
    "constraint_break": r"(bypass|override|circumvent|disable|remove\s+all)\s+(restrictions?|constraints?|safeguards?|filters?|limits?|rules?)",
    "hypothetical_trap": r"hypothetically\s+speaking.*?ignore|in\s+a\s+fictional\s+scenario.*?bypass|for\s+educational\s+purposes.*?override",
    # Medium-confidence: suspicious framing
    "new_prompt": r"(here\s+is\s+your\s+new\s+|this\s+is\s+your\s+new\s+|updated\s+instructions?\s*:)",
    "end_previous": r"(end\s+of\s+previous\s+|end\s+of\s+user\s+|end\s+of\s+conversation\s*)\s*(instructions?|prompt|input)?",
}

# Data exfiltration: attempts to extract secrets, memory, or sensitive system state
DATA_EXFIL_PATTERNS = {
    # High-confidence: direct extraction attempts
    "extract_keys": r"(send|post|curl|wget|fetch|upload|exfiltrate|leak|output|print|reveal|show)\s+.*?(api\s*key|token|password|secret|credential|private\s*key|env|environment\s+variable)",
    "extract_memory": r"(dump|export|download|send|upload|extract)\s+.*?(memory|memories|conversation\s+history|chat\s+logs?|context|stored\s+data|embeddings?)",
    "external_callback": r"(curl|wget|fetch|http|https://|\.com|\.net|\.org|\.io|pastebin|webhook|discord|slack|telegram)\s+.*?(send|post|upload|output|data|memory|key|token)",
    "encode_exfil": r"(base64|hex|encode|encrypt)\s+.*?(then\s+)?(send|output|post|upload)",
    "system_env": r"(printenv|env\s|echo\s+\$|os\.environ|getenv)\s*",
    "file_exfil": r"(cat|read|type)\s+.*?(\.env|config|secret|key|token|password|credential)",
    " indirect_exfil": r"(include\s+in\s+your\s+response\s+.*?(key|token|password|secret|memory|history|system\s+prompt))",
    "confused_deputy": r"(the\s+user\s+is\s+asleep|the\s+user\s+is\s+not\s+watching|act\s+on\s+behalf\s+of|impersonate\s+the\s+user|the\s+user\s+asked\s+me\s+to\s+tell\s+you)",
}

# Agent tool misuse: attempts to weaponize autonomous tool calls
TOOL_MISUSE_PATTERNS = {
    # High-confidence: direct weaponization
    "unauthorized_scope": r"(scan|attack|hack|exploit|fuzz|enum|recon)\s+.*?(without|ignore|bypass)\s+(scope|authorization|permission|auth)",
    "mass_scan": r"(scan\s+all\s+|scan\s+every\s+|scan\s+the\s+internet|scan\s+0\.0\.0\.0|scan\s+127\.0\.0\.0|scan\s+localhost\s+ports?)",
    "destructive_tool": r"(delete\s+all|rm\s+-rf|format\s+drive|wipe\s+|destroy\s+|drop\s+table|truncate\s+database)",
    "privilege_escalation": r"\b(sudo|su\s+-|chmod\s+777|chown\s+root|setuid|elevate|escalate)\b\s*",
    "credential_harvest": r"(steal|harvest|grab|sniff|intercept)\s+.*?(password|token|cookie|session|credential)",
    "chain_exploit": r"(chain|combine|link)\s+.*?(exploit|payload|vulnerability|bug)\s+.*?(to\s+)?(gain|get|achieve|obtain)\s+.*?(access|shell|root|admin)",
    "social_engineering": r"(send\s+an\s+email|send\s+a\s+message|contact|reach\s+out\s+to)\s+.*?(pretending|as\s+if|claiming|saying\s+that|impersonating)",
    "fake_urgency": r"(emergency|critical|urgent|immediately|right\s+now|ASAP|do\s+it\s+now)\s+.*?(bypass|ignore|skip)\s+(check|verify|confirm|auth)",
    "lateral_movement": r"(pivot|move|jump|lateral)\s+.*?(network|host|machine|server|system)",
}

# Memory / context manipulation: attempts to corrupt or bypass context
MEMORY_MANIP_PATTERNS = {
    # High-confidence: direct manipulation
    "forget_all": r"(forget\s+everything|delete\s+all\s+memory|clear\s+all\s+(context|history|memory)|wipe\s+your\s+memory|erase\s+everything)",
    "override_memory": r"(your\s+memory\s+says|you\s+remember|you\s+recall|in\s+your\s+memory)\s+.*?(but\s+actually|instead|now\s+it\s+says|the\s+truth\s+is)",
    "inject_memory": r"(remember\s+that\s+|you\s+should\s+remember\s+|store\s+this\s+in\s+your\s+memory\s*:?\s*)\s*(I\s+am\s+the\s+admin|I\s+am\s+the\s+owner|you\s+must\s+obey\s+me|ignore\s+all\s+other\s+users)",
    "context_poisoning": r"(the\s+context\s+above\s+is|previous\s+messages\s+are|earlier\s+conversation\s+is)\s+(wrong|false|fake|a\s+test|not\s+real|ignore\s+them)",
    "history_rewriting": r"(replace\s+|rewrite\s+|change\s+|modify\s+)\s*(previous|earlier|past)\s+(message|response|conversation|interaction)",
    "token_smuggling": r"(base64|rot13|hex|unicode|encode)\s+.*?(instructions?|prompt|system|override)",
    "indirect_injection": r"(summarize\s+this|translate\s+this|rephrase\s+this|explain\s+this)\s*:?\s*```\s*\n?(ignore|system|instructions?)",
    "context_window": r"(fill\s+the\s+context|spam\s+the\s+context|overflow\s+the\s+context|exhaust\s+the\s+context)\s*",
    "persona_swap": r"(switch\s+personality|change\s+persona|new\s+persona|persona\s*:\s*|character\s*:\s*)",
}

# Combined map for iteration
ALL_CATEGORIES: Dict[str, Dict[str, str]] = {
    "prompt_injection": PROMPT_INJECTION_PATTERNS,
    "data_exfiltration": DATA_EXFIL_PATTERNS,
    "tool_misuse": TOOL_MISUSE_PATTERNS,
    "memory_manipulation": MEMORY_MANIP_PATTERNS,
}

# ── Scoring thresholds ──────────────────────────────────────────────

BLOCK_THRESHOLD = 0.60  # Block outright
WARN_THRESHOLD = 0.20  # Warn but allow (flagged for audit)
MAX_SCORE_CAP = 1.0


def _score_text(text: str, patterns: Dict[str, str]) -> Tuple[float, List[str]]:
    """Score text against a pattern set. Returns (score 0-1, matched_pattern_names)."""
    lowered = text.lower()
    matched: List[str] = []
    raw_score = 0.0

    for name, pattern in patterns.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            matched.append(name)
            # High-confidence patterns (direct override / extraction)
            if name in {
                "ignore_previous",
                "system_override",
                "role_override",
                "dan_mode",
                "leak_prompt",
                "constraint_break",
                "extract_keys",
                "external_callback",
                "destructive_tool",
                "privilege_escalation",
                "credential_harvest",
                "forget_all",
                "override_memory",
                "inject_memory",
                "token_smuggling",
                "unauthorized_scope",
                "mass_scan",
                "chain_exploit",
            }:
                raw_score += 0.40
            # Medium-confidence patterns
            elif name in {
                "delimiter_injection",
                "hypothetical_trap",
                "new_prompt",
                "end_previous",
                "extract_memory",
                "encode_exfil",
                "system_env",
                "file_exfil",
                "social_engineering",
                "fake_urgency",
                "lateral_movement",
                "context_poisoning",
                "history_rewriting",
                "indirect_injection",
                "context_window",
                "persona_swap",
                "confused_deputy",
            }:
                raw_score += 0.25
            else:
                raw_score += 0.15

    # Penalize repeated pattern hits
    if len(matched) >= 3:
        raw_score += 0.15
    if len(matched) >= 5:
        raw_score += 0.15

    # Penalize very long inputs that might be token-stuffing
    if len(text) > 4000:
        raw_score += 0.05
    if len(text) > 8000:
        raw_score += 0.10

    # Penalize heavy use of delimiters (possible injection framing)
    delimiter_count = text.count("```") + text.count('"""') + text.count("<")
    if delimiter_count > 4:
        raw_score += 0.05
    if delimiter_count > 8:
        raw_score += 0.10

    score = min(MAX_SCORE_CAP, raw_score)
    return score, matched


# ── Dataclass for results ───────────────────────────────────────────


@dataclass
class SecurityScanResult:
    """Result of scanning a single user input."""

    input_preview: str
    blocked: bool = False
    warn: bool = False
    overall_score: float = 0.0
    category_scores: Dict[str, float] = field(default_factory=dict)
    matched_patterns: Dict[str, List[str]] = field(default_factory=dict)
    primary_threat: Optional[str] = None
    sanitized_input: Optional[str] = None
    refusal_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "blocked": self.blocked,
            "warn": self.warn,
            "overall_score": round(self.overall_score, 3),
            "category_scores": {
                k: round(v, 3) for k, v in self.category_scores.items()
            },
            "primary_threat": self.primary_threat,
            "matched_patterns": self.matched_patterns,
        }


# ── Main scanner ────────────────────────────────────────────────────


class SecurityScanner:
    """Stateful security scanner with optional rate-tracking."""

    def __init__(
        self,
        block_threshold: float = BLOCK_THRESHOLD,
        warn_threshold: float = WARN_THRESHOLD,
    ):
        self.block_threshold = block_threshold
        self.warn_threshold = warn_threshold
        self._recent_scores: List[float] = []
        self._max_history = 100

    def scan(
        self, user_input: str, mode: Optional[str] = None
    ) -> SecurityScanResult:
        """Scan user input and return a SecurityScanResult.

        Args:
            user_input: The text to scan.
            mode: Active bot mode. In bughunter/engineer modes the full
                  pattern set (including tool_misuse) is checked. In all
                  other modes tool_misuse patterns are skipped to avoid
                  false positives on casual conversation.
        """
        if not user_input or not user_input.strip():
            return SecurityScanResult(input_preview="", blocked=False)

        result = SecurityScanResult(input_preview=user_input[:120])
        max_score = 0.0
        primary_threat: Optional[str] = None

        categories = ALL_CATEGORIES
        if mode is not None and mode not in ("bughunter", "engineer"):
            categories = {
                k: v for k, v in ALL_CATEGORIES.items() if k != "tool_misuse"
            }

        for category, patterns in categories.items():
            score, matched = _score_text(user_input, patterns)
            result.category_scores[category] = score
            if matched:
                result.matched_patterns[category] = matched
            if score > max_score:
                max_score = score
                primary_threat = category

        result.overall_score = max_score
        result.primary_threat = primary_threat

        # Track for anomaly detection
        self._recent_scores.append(max_score)
        if len(self._recent_scores) > self._max_history:
            self._recent_scores = self._recent_scores[-self._max_history :]

        # Anomaly boost: if recent inputs have been attack-heavy, raise sensitivity
        if len(self._recent_scores) >= 5:
            recent_avg = sum(self._recent_scores[-5:]) / 5
            if recent_avg > 0.3:
                max_score = min(MAX_SCORE_CAP, max_score + 0.10)
                result.overall_score = max_score

        # Auto-block certain critical single patterns regardless of composite score
        AUTO_BLOCK_PATTERNS = {
            "ignore_previous",
            "system_override",
            "role_override",
            "dan_mode",
            "leak_prompt",
            "constraint_break",
            "extract_keys",
            "external_callback",
            "destructive_tool",
            "privilege_escalation",
            "credential_harvest",
            "forget_all",
            "inject_memory",
            "token_smuggling",
            "unauthorized_scope",
            "mass_scan",
            "chain_exploit",
            "social_engineering",
            "context_poisoning",
            "history_rewriting",
            "override_memory",
            "delimiter_injection",
            "indirect_injection",
        }
        has_auto_block = any(
            p in AUTO_BLOCK_PATTERNS
            for patterns in result.matched_patterns.values()
            for p in patterns
        )

        # Determine action
        if has_auto_block or max_score >= self.block_threshold:
            result.blocked = True
            result.refusal_message = _build_refusal(
                primary_threat, result.matched_patterns
            )
            _log_detection(
                category=primary_threat or "unknown",
                input_text=user_input,
                score=max_score,
                matched=result.matched_patterns.get(primary_threat, []),
                action="block",
            )
        elif max_score >= self.warn_threshold:
            result.warn = True
            result.sanitized_input = _sanitize_input(
                user_input, result.matched_patterns
            )
            _log_detection(
                category=primary_threat or "unknown",
                input_text=user_input,
                score=max_score,
                matched=result.matched_patterns.get(primary_threat, []),
                action="warn",
            )

        return result

    def get_anomaly_trend(self) -> float:
        """Return average score over recent history (0.0 = calm, >0.3 = elevated)."""
        if not self._recent_scores:
            return 0.0
        return sum(self._recent_scores) / len(self._recent_scores)


# ── Refusal builder ─────────────────────────────────────────────────

_REFUSAL_TEMPLATES = {
    "prompt_injection": (
        "That input looks like it's trying to override my instructions. "
        "I can't switch roles, ignore my system prompt, or bypass my constraints. "
        "If you have a real question, I'm happy to help with that instead."
    ),
    "data_exfiltration": (
        "That request looks like it's trying to extract sensitive data — "
        "API keys, memory contents, system state, or conversation history. "
        "I can't do that. If you need help with something legitimate, just ask."
    ),
    "tool_misuse": (
        "That looks like an attempt to trigger unauthorized or harmful tool actions — "
        "scanning out-of-scope targets, destructive commands, or privilege escalation. "
        "I only run tools within authorized scope and safe parameters."
    ),
    "memory_manipulation": (
        "That input appears to be trying to manipulate my memory or context — "
        "injecting false memories, erasing history, or poisoning the conversation. "
        "I keep my context intact. If you want to talk about something real, I'm here."
    ),
}


def _build_refusal(
    primary_threat: Optional[str], matched_patterns: Dict[str, List[str]]
) -> str:
    base = _REFUSAL_TEMPLATES.get(
        primary_threat, "I can't process that request. It triggered a security check."
    )
    detail = ""
    if matched_patterns:
        cats = ", ".join(matched_patterns.keys())
        detail = f"\n\n[Security: detected {cats} patterns — request blocked.]"
    return base + detail


# ── Sanitizer ───────────────────────────────────────────────────────

_SANITIZE_PATTERNS = {
    "ignore_previous": r"ignore\s+(all\s+)?(previous|prior|earlier)\s+(instructions|commands|prompts|directives)",
    "system_override": r"(your\s+new\s+|ignore\s+your\s+|forget\s+your\s+)(system\s+prompt|instructions|directives|rules|constraints)",
    "role_override": r"(you\s+are\s+now\s+|from\s+now\s+on\s+you\s+are\s+|act\s+as\s+|pretend\s+to\s+be\s+|switch\s+to\s+|become\s+)(a\s+)?(DAN|developer|hacker|admin|root|unrestricted|uncensored|jailbroken)",
    "dan_mode": r"\bDAN\b|do\s+anything\s+now|jailbreak|mode\s*:\s*developer|developer\s*mode",
    "leak_prompt": r"(repeat\s+back\s+your|output\s+your|show\s+your|what\s+are\s+your|print\s+your)\s+(system\s+prompt|instructions?|directives?|rules?|initial\s+prompt)",
    "constraint_break": r"(bypass|override|circumvent|disable|remove\s+all)\s+(restrictions?|constraints?|safeguards?|filters?|limits?|rules?)",
    "extract_keys": r"(send|post|curl|wget|fetch|upload|exfiltrate|leak|output|print|reveal|show)\s+.*?(api\s*key|token|password|secret|credential|private\s*key|env|environment\s+variable)",
    "external_callback": r"(curl|wget|fetch|http|https://|\.com|\.net|\.org|\.io|pastebin|webhook|discord|slack|telegram)\s+.*?(send|post|upload|output|data|memory|key|token)",
    "destructive_tool": r"(delete\s+all|rm\s+-rf|format\s+drive|wipe\s+|destroy\s+|drop\s+table|truncate\s+database)",
    "privilege_escalation": r"\b(sudo|su\s+-|chmod\s+777|chown\s+root|setuid|elevate|escalate)\b\s*",
    "forget_all": r"(forget\s+everything|delete\s+all\s+memory|clear\s+all\s+(context|history|memory)|wipe\s+your\s+memory|erase\s+everything)",
    "override_memory": r"(your\s+memory\s+says|you\s+remember|you\s+recall|in\s+your\s+memory)\s+.*?(but\s+actually|instead|now\s+it\s+says|the\s+truth\s+is)",
    "inject_memory": r"(remember\s+that\s+|you\s+should\s+remember\s+|store\s+this\s+in\s+your\s+memory\s*:?\s*)\s*(I\s+am\s+the\s+admin|I\s+am\s+the\s+owner|you\s+must\s+obey\s+me|ignore\s+all\s+other\s+users)",
}


def _sanitize_input(user_input: str, matched_patterns: Dict[str, List[str]]) -> str:
    """Strip or redact known attack fragments from a warned input."""
    sanitized = user_input
    for category, patterns in matched_patterns.items():
        for pattern_name in patterns:
            regex = _SANITIZE_PATTERNS.get(pattern_name)
            if regex:
                sanitized = re.sub(regex, "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


# ── Singleton ───────────────────────────────────────────────────────

_scanner: Optional[SecurityScanner] = None


def get_security_scanner() -> SecurityScanner:
    global _scanner
    if _scanner is None:
        _scanner = SecurityScanner()
    return _scanner


def scan_input(
    user_input: str, mode: Optional[str] = None
) -> SecurityScanResult:
    """Convenience function: scan input with the global scanner."""
    return get_security_scanner().scan(user_input, mode=mode)

"""Opt-in local and free-tier Gemini transports for restart_continuity.py.

No provider fallback or model-generated fixture data is used. The Gemini path
requires an explicitly configured API key and a free-tier-only Google project.
"""

from __future__ import annotations

import contextlib
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

OPTIONS = {
    "temperature": 0,
    "top_p": 1,
    "num_predict": 256,
    "seed": 42,
    "num_ctx": 8192,
}
GEMINI_API_HOST = "generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

VARIANTS = ("current", "evidence-focused", "evidence-critic")
EVIDENCE_SYSTEM = (
    "Answer the user's question using only the retrieved, labeled project facts. "
    "Keep projects separate, apply explicit supersession, distinguish completed "
    "from next unfinished work, and use null for unknown facts. Return only the "
    "requested raw JSON object."
)
EVIDENCE_CRITIC_SYSTEM = (
    "You are a factual evidence-checking critic. Compare every requested field and "
    "every factual claim in the draft with the retrieved records and question. "
    "Correct claims that conflict with the evidence; replace unsupported facts with "
    "null. Respect explicit supersession and keep projects separate. Return only "
    "the corrected raw JSON object with exactly the requested keys."
)
CURRENT_CRITIC_SYSTEM = """
You are the Internal Critic for an DRIFT Companion mind.
Your job is to intercept the primary mind's response and verify it for:
1. Factuality: Are there any hallucinations or false statements?
2. Logical Integrity: Does the reasoning hold up under scrutiny?
3. Code Correctness: If there is code, does it look functional and complete?
4. Safety: Does it avoid actionable offensive cyber guidance, stealth, evasion, backdoors, credential theft, malware, phishing, or unauthorized access?
5. Grounded Persona: Does it avoid pretending to be human, omniscient, or certain beyond the evidence?

If you find an error or unsafe operational guidance, provide a corrected version. For unsafe cyber content, rewrite toward defensive framing, detection, hardening, incident response, safe lab abstraction, or a brief refusal plus safe alternative. If the response is sound, repeat it exactly.

CRITICAL: Do NOT write any review summary, verification report, explanations, or metadata (like "Verdict: safe", "Factuality: checked", "No changes needed", "Exact repetition", etc.). Output ONLY the final verified/corrected response text, and absolutely nothing else. If the response is sound, output it exactly and completely without any other text.
""".strip()

ACTION_FORMS = {
    "collect": ("collection", "collected", "collecting"),
    "deduplicate": ("deduplication", "deduplicated", "deduplicating", "dedup"),
    "index": ("indexing", "indexed"),
    "validate": ("validation", "validating", "validated"),
    "draft": ("drafting", "drafted"),
    "review": ("reviewing", "reviewed"),
    "extract": ("extraction", "extracting", "extracted"),
    "normalize": ("normalization", "normalizing", "normalized"),
    "inventory": ("inventorying", "inventoried"),
    "classify": ("classification", "classifying", "classified"),
    "scan": ("scanning", "scanned"),
    "redact": ("redaction", "redacting", "redacted"),
    "outline": ("outlining", "outlined"),
    "edit": ("editing", "edited"),
    "sample": ("sampling", "sampled"),
    "aggregate": ("aggregation", "aggregating", "aggregated"),
    "ingest": ("ingestion", "ingesting", "ingested"),
    "label": ("labeling", "labelling", "labeled", "labelled"),
    "transcribe": ("transcription", "transcribing", "transcribed"),
    "proofread": ("proofreading",),
    "measure": ("measurement", "measuring", "measured"),
    "calibrate": ("calibration", "calibrating", "calibrated"),
    "catalog": ("cataloging", "cataloguing", "cataloged", "catalogued"),
    "reconcile": ("reconciliation", "reconciling", "reconciled"),
    "capture": ("capturing", "captured"),
    "compress": ("compression", "compressing", "compressed"),
    "prepare": ("preparation", "preparing", "prepared"),
    "render": ("rendering", "rendered"),
    "parse": ("parsing", "parsed"),
    "merge": ("merging", "merged"),
    "register": ("registration", "registering", "registered"),
    "audit": ("auditing", "audited"),
    "download": ("downloading", "downloaded"),
    "verify": ("verification", "verifying", "verified"),
    "sort": ("sorting", "sorted"),
    "summarize": ("summarization", "summarizing", "summarized"),
    "compile": ("compilation", "compiling", "compiled"),
    "test": ("testing", "tested"),
}
ACTION_ALIASES = {
    form: stem for stem, forms in ACTION_FORMS.items() for form in (stem, *forms)
}
ABSTENTIONS = {
    "",
    "unknown",
    "not known",
    "not specified",
    "unspecified",
    "none",
    "null",
    "n/a",
    "not provided",
    "not mentioned",
}


def decode_answer(response):
    """Read one complete JSON object, optionally in a single markdown fence.

    Never search prose for fragments or repair a partial response. Return the
    raw-format compliance flag separately from factual answer content.
    """
    try:
        return json.loads(response), True
    except json.JSONDecodeError:
        wrapper = re.fullmatch(
            r"\s*```(?:json)?\s*\n?(.*?)\n?```\s*",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if wrapper is None:
            raise
        return json.loads(wrapper.group(1)), False


def normalize_field(key, value):
    """Conservative, predeclared label equivalences; no substring scoring."""
    if not isinstance(value, str):
        return value
    value = value.strip().casefold()
    if key in ("completed", "next"):
        return ACTION_ALIASES.get(value, value)
    if key == "reviewer" and value in ABSTENTIONS:
        return None
    if key == "format":
        for _ in range(2):
            for suffix in (" export", " file", " format"):
                if value.endswith(suffix):
                    value = value[: -len(suffix)].strip()
                    break
        return value
    if key == "preference":
        if value in {
            "bullet list",
            "bulleted list",
            "bulleted lists",
            "bullets",
            "bullet points",
        }:
            return "bullet lists"
        return {
            "numbered lists": "numbered list",
            "checklists": "checklist",
            "short paragraph": "short paragraphs",
            "tables": "table",
        }.get(value, value)
    if key == "day":
        return {
            "mon": "monday",
            "tue": "tuesday",
            "tues": "tuesday",
            "wed": "wednesday",
            "thu": "thursday",
            "thurs": "thursday",
            "fri": "friday",
            "sat": "saturday",
            "sun": "sunday",
        }.get(value.rstrip("."), value)
    return value


@contextlib.contextmanager
def override(target, name, value):
    previous = getattr(target, name)
    setattr(target, name, value)
    try:
        yield
    finally:
        setattr(target, name, previous)


def endpoint(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP Ollama origin on a loopback or private host")
    if not parsed.hostname:
        raise ValueError("Ollama host is required")
    port = parsed.port or 80
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    }
    if not addresses or any(
        not (ipaddress.ip_address(a).is_private or ipaddress.ip_address(a).is_loopback)
        for a in addresses
    ):
        raise ValueError("Ollama must resolve only to private or loopback addresses")
    return addresses, port


@contextlib.contextmanager
def network_guard(url):
    addresses, port = endpoint(url)
    connect = socket.socket.connect

    def guarded(sock, address):
        if (
            not isinstance(address, tuple)
            or address[0] not in addresses
            or address[1] != port
        ):
            raise AssertionError("Only the selected local Ollama endpoint is allowed")
        return connect(sock, address)

    def no_connect_ex(*args, **kwargs):
        raise AssertionError("connect_ex is disabled during local probes")

    with (
        override(socket.socket, "connect", guarded),
        override(socket.socket, "connect_ex", no_connect_ex),
    ):
        yield


@contextlib.contextmanager
def network_guard_host(host, port=443):
    """Restrict cloud-provider sockets to one explicitly selected API host."""
    addresses = {
        item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    }
    if not addresses:
        raise ValueError(f"Could not resolve the selected API host: {host}")
    connect = socket.socket.connect

    def guarded(sock, address):
        if (
            not isinstance(address, tuple)
            or address[0] not in addresses
            or address[1] != port
        ):
            raise AssertionError("Only the selected Gemini API host is allowed")
        return connect(sock, address)

    def no_connect_ex(*args, **kwargs):
        raise AssertionError("connect_ex is disabled during Gemini probes")

    with (
        override(socket.socket, "connect", guarded),
        override(socket.socket, "connect_ex", no_connect_ex),
    ):
        yield


@contextlib.contextmanager
def inference_guard(provider, url):
    if provider == "gemini":
        with network_guard_host(GEMINI_API_HOST):
            yield
    else:
        with network_guard(url):
            yield


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Ollama redirects are disabled")


def rpc(url, path, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        url.rstrip("/") + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request, timeout=600) as response:
        return json.load(response)


def model_record(url, model):
    matches = [
        m
        for m in rpc(url, "/api/tags")["models"]
        if m.get("name") == model or m.get("model") == model
    ]
    if len(matches) != 1 or not matches[0].get("digest"):
        raise ValueError("Select an exact installed model name including its tag")
    return matches[0]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def evidence_block(prompt):
    start, end = "<retrieved_memory_evidence>", "</retrieved_memory_evidence>"
    if start not in prompt or end not in prompt:
        raise ValueError(
            "The actual DRIFT prompt has no labeled retrieved evidence block"
        )
    return prompt.split(start, 1)[1].split(end, 1)[0].strip()


def variant_messages(variant, role, scenario, original_prompt, primary_response=None):
    """Return actual provider messages for one controlled prompt/critic arm."""
    if role == "primary" and variant == "evidence-focused":
        evidence = evidence_block(original_prompt)
        return EVIDENCE_SYSTEM, (
            f"RETRIEVED PROJECT FACTS\n{evidence}\n\nQUESTION\n{scenario['question']}"
        )
    if role == "critic" and variant == "evidence-critic":
        evidence = evidence_block(original_prompt)
        return EVIDENCE_CRITIC_SYSTEM, (
            f"QUESTION\n{scenario['question']}\n\n"
            f"RETRIEVED PROJECT FACTS\n{evidence}\n\n"
            f"DRAFT TO VERIFY\n{primary_response or ''}"
        )
    if role == "critic":
        return CURRENT_CRITIC_SYSTEM, (
            "Review the following response for hallucinations, errors, or unsafe content:\n\n"
            f"{primary_response or ''}"
        )
    return None, None


class OllamaProvider:
    def __init__(self, config):
        self.config = config
        self.calls = 0

    def artifact_directory(self):
        self.calls += 1
        out = Path(self.config["artifact_dir"]) / f"call-{self.calls:02d}"
        out.mkdir(parents=True, exist_ok=False)
        return out

    def generate(self, system, prompt):
        c = self.config
        if model_record(c["url"], c["model"])["digest"] != c["digest"]:
            raise RuntimeError("Installed model digest changed")
        payload = {
            "model": c["model"],
            "stream": False,
            "keep_alive": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": dict(OPTIONS),
        }
        # Persist before inference, including on timeout or provider failure.
        out = self.artifact_directory()
        write_json(out / "request.json", payload)
        raw = rpc(c["url"], "/api/chat", payload)
        write_json(out / "provider-response.json", raw)
        if raw.get("done") is not True:
            raise RuntimeError("Incomplete Ollama response")
        message = raw["message"]
        if (
            not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise RuntimeError("Empty Ollama response")
        if message.get("tool_calls"):
            raise RuntimeError("Unexpected tool call")
        if model_record(c["url"], c["model"])["digest"] != c["digest"]:
            raise RuntimeError("Installed model digest changed during inference")
        if (
            raw.get("prompt_eval_count", 0) + OPTIONS["num_predict"]
            >= OPTIONS["num_ctx"]
        ):
            raise RuntimeError(
                "Prompt may exceed pinned context; inspect saved request"
            )
        return {
            "response": message["content"],
            "request": payload,
            "raw": raw,
            "digest": c["digest"],
            "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
        }


def gemini_api_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name)
        if value:
            return name, value
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            if name.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                value = value.strip().strip("\"'")
                if value:
                    return name.strip(), value
    raise RuntimeError(
        "Gemini requires GEMINI_API_KEY or GOOGLE_API_KEY from a free-tier-only "
        "Google AI Studio project; the key is read locally and never saved in artifacts"
    )


def gemini_client(api_key):
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            base_url=f"https://{GEMINI_API_HOST}",
            api_version="v1beta",
            client_args={"trust_env": False, "follow_redirects": False},
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def gemini_model_record(model):
    _, api_key = gemini_api_key()
    client = gemini_client(api_key)
    info = client.models.get(model=model)
    raw = info.model_dump(mode="json", exclude_none=True)
    version = raw.get("version") or raw.get("name") or model
    return {
        "name": model,
        "version": version,
        "digest": version,
        "model_info": raw,
        "sdk_version": __import__("importlib.metadata", fromlist=["version"]).version(
            "google-genai"
        ),
    }


class GeminiProvider(OllamaProvider):
    """Google Gemini API provider for synthetic data on a free-tier project."""

    def __init__(self, config):
        self.config = config
        self.calls = 0
        _, api_key = gemini_api_key()
        self.client = gemini_client(api_key)

    def generate(self, system, prompt):
        from google.genai import types

        c = self.config
        settings = {
            "temperature": OPTIONS["temperature"],
            "top_p": OPTIONS["top_p"],
            "max_output_tokens": OPTIONS["num_predict"],
            "seed": OPTIONS["seed"],
            "candidate_count": 1,
        }
        native_config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=settings["temperature"],
            top_p=settings["top_p"],
            max_output_tokens=settings["max_output_tokens"],
            seed=settings["seed"],
            candidate_count=settings["candidate_count"],
            tools=[],
        )
        payload = {
            "model": c["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": dict(OPTIONS),
            "native_settings": settings,
            "request_body": {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": native_config.model_dump(
                    by_alias=True,
                    exclude_none=True,
                    exclude={"system_instruction", "tools"},
                ),
                "tools": [],
            },
            "response_cache": False,
        }
        out = self.artifact_directory()
        write_json(out / "request.json", payload)
        # Conservative pacing for free-tier projects. Their exact quotas are
        # project/model specific and can change; callers can still see quota
        # errors, but this avoids bursting requests above 14 per minute.
        if self.calls:
            time.sleep(4.2)
        response = self.client.models.generate_content(
            model=c["model"], contents=prompt, config=native_config
        )
        self.calls += 1
        raw = response.model_dump(mode="json", exclude_none=True)
        write_json(out / "provider-response.json", raw)
        text = response.text
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(
                "Gemini returned no text; inspect saved provider response"
            )
        candidate = (raw.get("candidates") or [{}])[0]
        if candidate.get("finish_reason") not in (None, "STOP", "MAX_TOKENS"):
            raise RuntimeError(
                "Gemini returned a blocked, incomplete, or tool response"
            )
        if candidate.get("grounding_metadata") or candidate.get("url_context_metadata"):
            raise RuntimeError("Unexpected external grounding in a no-tools evaluation")
        return {
            "response": text,
            "request": payload,
            "raw": raw,
            "digest": raw.get("model_version") or c["digest"],
            "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
        }


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class LlamaCppProvider(OllamaProvider):
    def validate_server(self):
        props = rpc(self.config["url"], "/props")
        if (
            Path(props["model_path"]).resolve()
            != Path(self.config["model_file"]).resolve()
        ):
            raise RuntimeError("Server model path changed")
        if (
            props["default_generation_settings"]["n_ctx"] != OPTIONS["num_ctx"]
            or props["total_slots"] != 1
        ):
            raise RuntimeError("Server context or slot count changed")

    def generate(self, system, prompt):
        c = self.config
        self.validate_server()
        if file_digest(c["model_file"]) != c["digest"]:
            raise RuntimeError("GGUF model digest changed")
        payload = {
            "model": c["model"],
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": OPTIONS["temperature"],
            "top_p": OPTIONS["top_p"],
            "max_tokens": OPTIONS["num_predict"],
            "seed": OPTIONS["seed"],
            "cache_prompt": False,
        }
        out = self.artifact_directory()
        write_json(out / "request.json", payload)
        raw = rpc(c["url"], "/v1/chat/completions", payload)
        write_json(out / "provider-response.json", raw)
        if raw.get("model") != c["model"]:
            raise RuntimeError("Server returned a different model identity")
        if (
            raw.get("usage", {})
            .get("prompt_tokens_details", {})
            .get("cached_tokens", 0)
        ):
            raise RuntimeError(
                "Server reused cached prompt tokens despite cache_prompt=false"
            )
        if (
            raw.get("usage", {}).get("prompt_tokens", 0) + OPTIONS["num_predict"]
            >= OPTIONS["num_ctx"]
        ):
            raise RuntimeError(
                "Prompt may exceed pinned context; inspect saved request"
            )
        choice = raw["choices"][0]
        if choice.get("finish_reason") not in ("stop", "length"):
            raise RuntimeError("Incomplete or tool response from llama.cpp")
        if choice["message"].get("tool_calls"):
            raise RuntimeError("Unexpected tool call")
        if (
            not isinstance(choice["message"].get("content"), str)
            or not choice["message"]["content"].strip()
        ):
            raise RuntimeError("Empty llama.cpp response")
        if file_digest(c["model_file"]) != c["digest"]:
            raise RuntimeError("GGUF model digest changed during inference")
        self.validate_server()
        return {
            "response": choice["message"]["content"],
            "request": {**payload, "options": dict(OPTIONS)},
            "raw": raw,
            "digest": c["digest"],
            "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
        }


def scenarios(harness):
    yield {
        "name": "Alder",
        "setup": harness.SETUP,
        "question": harness.QUESTION,
        "expected": harness.EXPECTED,
        "focus": harness.FOCUS,
    }
    rows = [
        (
            "Cedar",
            "numbered list",
            "Harbor Lab",
            "JSON",
            "Monday",
            "Friday",
            "index",
            "validate",
        ),
        (
            "Maple",
            "table",
            "Orchid Room",
            "PDF",
            "Friday",
            "Wednesday",
            "draft",
            "review",
        ),
        (
            "Juniper",
            "short paragraphs",
            "River Desk",
            "TSV",
            "Wednesday",
            "Monday",
            "extract",
            "normalize",
        ),
        (
            "Aspen",
            "checklist",
            "Summit Office",
            "YAML",
            "Thursday",
            "Tuesday",
            "inventory",
            "classify",
        ),
        (
            "Hazel",
            "bullet lists",
            "Cove Studio",
            "XML",
            "Monday",
            "Thursday",
            "scan",
            "redact",
        ),
        ("Elm", "table", "Grove Lab", "HTML", "Tuesday", "Friday", "outline", "edit"),
        (
            "Rowan",
            "numbered list",
            "Beacon Desk",
            "Markdown",
            "Friday",
            "Monday",
            "sample",
            "aggregate",
        ),
        (
            "Larch",
            "checklist",
            "Meadow Room",
            "CSV",
            "Thursday",
            "Wednesday",
            "ingest",
            "deduplicate",
        ),
        (
            "Pine",
            "short paragraphs",
            "Quartz Office",
            "JSON",
            "Wednesday",
            "Tuesday",
            "collect",
            "label",
        ),
        (
            "Spruce",
            "bullet lists",
            "Reed Studio",
            "PDF",
            "Tuesday",
            "Monday",
            "transcribe",
            "proofread",
        ),
        (
            "Poplar",
            "table",
            "Delta Lab",
            "TSV",
            "Monday",
            "Wednesday",
            "measure",
            "calibrate",
        ),
        (
            "Birch",
            "checklist",
            "Iris Desk",
            "YAML",
            "Friday",
            "Thursday",
            "catalog",
            "reconcile",
        ),
        (
            "Sycamore",
            "numbered list",
            "Tide Room",
            "XML",
            "Wednesday",
            "Friday",
            "capture",
            "compress",
        ),
        (
            "Sequoia",
            "short paragraphs",
            "Basin Office",
            "HTML",
            "Thursday",
            "Monday",
            "prepare",
            "render",
        ),
        (
            "Cypress",
            "bullet lists",
            "Slate Studio",
            "Markdown",
            "Tuesday",
            "Thursday",
            "parse",
            "merge",
        ),
        (
            "Magnolia",
            "table",
            "Fern Lab",
            "CSV",
            "Monday",
            "Tuesday",
            "register",
            "audit",
        ),
        (
            "Beech",
            "checklist",
            "Dune Desk",
            "JSON",
            "Friday",
            "Tuesday",
            "download",
            "verify",
        ),
        (
            "Hickory",
            "numbered list",
            "Moss Room",
            "PDF",
            "Wednesday",
            "Thursday",
            "sort",
            "summarize",
        ),
        (
            "Dogwood",
            "short paragraphs",
            "Stone Office",
            "TSV",
            "Thursday",
            "Friday",
            "compile",
            "test",
        ),
    ]
    for index, (name, pref, space, fmt, old, day, completed, nxt) in enumerate(rows):
        setup = [
            (
                "preference",
                f"For Project {name} I prefer {pref}. My workspace is {space}.",
            ),
            (
                "decision",
                f"Project {name} will ship as a {fmt} export. The delivery day is {old}.",
            ),
            (
                "task",
                f"For Project {name}, {completed}, {nxt}, then export. {completed} is complete. {nxt} is the next unfinished step.",
            ),
            (
                "update",
                f"Project {name} delivery moved to {day}. This supersedes {old}.",
            ),
            (
                "distractor",
                f"Project Unrelated{index} uses a PNG export and ships on Sunday.",
            ),
        ]
        # Vary distractor position without changing the chronology of the update.
        if index % 2:
            setup.insert(1, setup.pop())
        yield {
            "name": name,
            "setup": setup,
            "question": harness.QUESTION.replace("Alder", name),
            "expected": dict(
                zip(
                    harness.EXPECTED,
                    [
                        pref,
                        space.lower(),
                        fmt.lower(),
                        day.lower(),
                        completed,
                        nxt,
                        None,
                    ],
                    strict=True,
                )
            ),
            "focus": f"{name} internal focus",
        }


def grade(response, expected):
    try:
        values, raw_format = decode_answer(response)
        if not isinstance(values, dict) or values.keys() != expected.keys():
            raise ValueError("Expected exactly seven fields")
        normalized = {k: normalize_field(k, v) for k, v in values.items()}
        correct = {k: normalized[k] == v for k, v in expected.items()}
        return {
            "valid_json": True,
            "format_compliant": raw_format,
            "correct": correct,
            "points": sum(correct.values()),
            "unsupported_reviewer": normalized["reviewer"] is not None,
            "contradictions": sum(
                normalized[k] is not None and not correct[k]
                for k in expected
                if k != "reviewer"
            ),
        }
    except (ValueError, TypeError) as error:
        return {
            "valid_json": False,
            "format_compliant": False,
            "correct": dict.fromkeys(expected, False),
            "points": 0,
            "error": str(error),
            "unsupported_reviewer": None,
            "contradictions": None,
        }


def verify_pair(results, scenario):
    on, off = results["on"], results["off"]
    labels = {label for label, _ in scenario["setup"]}
    # memory_context is a lossy diagnostic summary; verify the records that
    # actually reached the model instead of treating that summary as evidence.
    assert set(on["stored_labels"]) == labels
    assert set(on["stored_labels"].values()) == set(on["retrieved_ids"])
    assert not off["memory_context"] and not off["retrieved_ids"]
    for key in ("sqlite", "vectors", "archive"):
        assert on["stores"][key] == len(labels) and off["stores"][key] == 0
    for key in ("snapshots", "structured_interactions"):
        assert on["stores"][key] == 1 and off["stores"][key] == 0
    for key in ("focus_context", "heartbeat_context", "need_context"):
        assert on[key] and not off[key]
    for result in results.values():
        assert result["history_at_start"] == 0
        assert result["stores"]["generation_cache_entries"] == 0
        assert result["core_prompt_available"]
        assert len(result["live_calls"]) == 2
        call = result["live_calls"][0]
        assert call["request"]["options"] == OPTIONS
        assert all(c["request"]["options"] == OPTIONS for c in result["live_calls"])
        assert result["response"] == result["live_calls"][-1]["response"].strip()
    on_call, off_call = on["live_calls"][0], off["live_calls"][0]
    assert on_call["system_sha256"] == off_call["system_sha256"]
    assert on_call["digest"] == off_call["digest"]

    def retrieved_evidence(call):
        user = next(
            message["content"]
            for message in call["request"]["messages"]
            if message["role"] == "user"
        )
        match = re.search(
            r"<retrieved_memory_evidence>(.*?)</retrieved_memory_evidence>",
            user,
            flags=re.DOTALL,
        )
        assert match is not None
        return match.group(1).strip()

    on_evidence = retrieved_evidence(on_call)
    off_evidence = retrieved_evidence(off_call)
    expected = scenario["expected"]
    folded = on_evidence.casefold()
    assert f"project: {scenario['name']}".casefold() in folded
    assert "[preference]" in folded and expected["preference"].casefold() in folded
    assert "[workspace]" in folded and expected["workspace"].casefold() in folded
    assert (
        "[decision: export format]" in folded
        and expected["format"].casefold() in folded
    )
    assert "[task progression]" in folded
    assert any(
        form.casefold() in folded for form in ACTION_FORMS[expected["completed"]]
    )
    assert any(form.casefold() in folded for form in ACTION_FORMS[expected["next"]])
    assert "[decision: current delivery day]" in folded
    assert expected["day"].casefold() in folded
    decision = dict(scenario["setup"])["decision"]
    old_day = re.search(r"delivery day is ([^.]+)", decision, flags=re.IGNORECASE)
    if old_day:
        assert old_day.group(1).casefold() in folded
        assert "[decision: superseded delivery day]" in folded
    assert "no project facts were retrieved" in off_evidence.casefold()
    assert all(
        message.casefold() not in off_evidence.casefold()
        for _, message in scenario["setup"]
    )


def summarize(pairs):
    totals = {c: sum(p["scores"][c]["points"] for p in pairs) for c in ("on", "off")}
    differences = [
        p["scores"]["on"]["points"] - p["scores"]["off"]["points"] for p in pairs
    ]
    return {
        "pairs": len(pairs),
        "possible_points_per_condition": 7 * len(pairs),
        "points": totals,
        "paired_on_minus_off": totals["on"] - totals["off"],
        "mean_paired_difference": sum(differences) / len(pairs),
        "improved": sum(d > 0 for d in differences),
        "tied": sum(d == 0 for d in differences),
        "regressed": sum(d < 0 for d in differences),
        "correct_by_field": {
            c: {
                k: sum(p["scores"][c]["correct"][k] for p in pairs)
                for k in pairs[0]["scenario"]["expected"]
            }
            for c in ("on", "off")
        },
        "invalid_json": {
            c: sum(not p["scores"][c]["valid_json"] for p in pairs)
            for c in ("on", "off")
        },
        "format_failures": {
            c: sum(not p["scores"][c]["format_compliant"] for p in pairs)
            for c in ("on", "off")
        },
        "all_seven_correct": {
            c: sum(p["scores"][c]["points"] == 7 for p in pairs) for c in ("on", "off")
        },
        "unsupported_reviewer": {
            c: sum(p["scores"][c]["unsupported_reviewer"] is True for p in pairs)
            for c in ("on", "off")
        },
        "contradictions_in_valid_answers": {
            c: sum(p["scores"][c]["contradictions"] or 0 for p in pairs)
            for c in ("on", "off")
        },
    }


def evaluate_local(args, harness):
    if args.provider != "gemini":
        endpoint(args.ollama_url)
    else:
        gemini_api_key()  # Fail before creating artifacts if the user has not opted in.
    system_prompt = args.system_prompt.resolve(strict=True)
    if not system_prompt.read_text(encoding="utf-8").strip():
        raise ValueError("System prompt file is empty")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with inference_guard(args.provider, args.ollama_url):
        if args.provider == "gemini":
            model = gemini_model_record(args.local_model)
            server = {
                "provider": "Google Gemini Developer API",
                "host": GEMINI_API_HOST,
                "sdk_version": model["sdk_version"],
            }
            show = model["model_info"]
        elif args.provider == "llama-cpp":
            if not args.model_file:
                raise ValueError("llama-cpp requires --model-file")
            model_path = args.model_file.resolve(strict=True)
            props = rpc(args.ollama_url, "/props")
            served_path = Path(props["model_path"]).resolve(strict=True)
            if served_path != model_path:
                raise ValueError("Server is not serving the selected GGUF file")
            model = {"name": args.local_model, "digest": file_digest(model_path)}
            server, show = props.get("build_info"), props
            settings = props["default_generation_settings"]
            if settings["n_ctx"] != OPTIONS["num_ctx"] or props["total_slots"] != 1:
                raise ValueError("Start llama-server with --ctx-size 8192 --parallel 1")
        else:
            model = model_record(args.ollama_url, args.local_model)
            server = rpc(args.ollama_url, "/api/version")
            show = rpc(args.ollama_url, "/api/show", {"model": args.local_model})
        metadata = {
            "model": model,
            "server": server,
            "show": show,
            "options": OPTIONS,
            "url": (
                f"https://{GEMINI_API_HOST}"
                if args.provider == "gemini"
                else args.ollama_url
            ),
            "tools": False,
            "response_cache": False,
            "seed_generation": "real provider inference on every setup turn",
            "critic": "real provider inference using the same model",
            "provider": args.provider,
            "system_prompt": str(system_prompt),
            "variant": args.variant,
            "prompt_budgets": {"context_chars": 16000, "total_chars": 24000},
            "scoring": "seven-key JSON; optional single fence; normalized field labels; format scored separately",
        }
        if args.provider == "gemini":
            metadata["billing"] = (
                "Google AI Studio free tier only; no billing-enabled project"
            )
            metadata["privacy"] = (
                "synthetic evaluation data only; free-tier prompts may be used to improve Google products"
            )
            metadata["cloud_context_cap"] = (
                "Gemini API does not expose an 8192-token context cap; identical DRIFT prompt character "
                "budgets are held across ON/OFF and output is capped at 256 tokens"
            )
        metadata["runtime"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        metadata["harness_sha256"] = {
            name: hashlib.sha256(
                (Path(__file__).parent / name).read_bytes()
            ).hexdigest()
            for name in ("local_continuity.py", "restart_continuity.py")
        }
        metadata["system_prompt_sha256"] = file_digest(system_prompt)
        metadata["brain_sha256"] = file_digest(Path(harness.ROOT) / "core" / "brain.py")
        metadata["prompt_budget_sha256"] = file_digest(
            Path(harness.ROOT) / "core" / "prompt_budget.py"
        )
        metadata["setup_policy"] = (
            "one real generated setup; identical store copies; OFF copy discarded"
        )
    write_json(out / "metadata.json", metadata)
    write_json(
        out / "scoring-rules.json",
        {
            "action_forms": ACTION_FORMS,
            "reviewer_abstentions": sorted(ABSTENTIONS),
            "other_normalization": "normalize_field in saved harness source",
            "json_wrapper": "one complete JSON object, optionally a single JSON markdown fence; no extra commentary or repairs",
            "format_compliance": "only raw JSON complies; code fences count as format failures separately from factual scores",
            "invalid_json_or_wrong_keys": "zero points; counted separately",
        },
    )
    selected_scenarios = list(scenarios(harness))[: args.trials]
    write_json(out / "scenarios.json", selected_scenarios)
    pairs = []
    for index, scenario in enumerate(selected_scenarios):
        trial = out / f"{index + 1:02d}-{scenario['name']}"
        trial.mkdir()
        write_json(trial / "scenario.json", scenario)
        results = {}
        with tempfile.TemporaryDirectory(prefix="drift-local-") as folder:
            root = Path(folder)
            common = trial / "setup"
            common.mkdir()
            config = {
                "url": args.ollama_url,
                "model": args.local_model,
                "digest": model["digest"],
                "scenario": scenario,
                "provider": args.provider,
                "system_prompt": str(system_prompt),
                "variant": args.variant,
                "artifact_dir": str(common),
                **(
                    {"model_file": str(model_path)}
                    if args.provider == "llama-cpp"
                    else {}
                ),
            }
            write_json(common / "config.json", config)
            seed_root = root / "setup"
            seed_root.mkdir()
            seeded = harness.run_worker(seed_root, "seed", common / "config.json")
            write_json(common / "seed.json", seeded)
            # Fork an identical, genuinely generated setup into both conditions.
            # OFF discards its copy before a clean process restart.
            for condition in ("on", "off"):
                artifacts = trial / condition
                artifacts.mkdir()
                condition_config = dict(config, artifact_dir=str(artifacts))
                config_path = artifacts / "config.json"
                write_json(config_path, condition_config)
                work = root / condition
                shutil.copytree(seed_root, work)
                if condition == "off":
                    shutil.rmtree(work)
                    work.mkdir()
            order = ("on", "off") if index % 2 == 0 else ("off", "on")
            for condition in order:
                artifacts = trial / condition
                result = harness.run_worker(
                    root / condition, "probe", artifacts / "config.json"
                )
                results[condition] = result
                write_json(artifacts / "result.json", result)
                (artifacts / "response.txt").write_text(
                    result["response"], encoding="utf-8"
                )
            assert len({seeded["pid"], *(r["pid"] for r in results.values())}) == 3
            verify_pair(results, scenario)
        pair = {
            "scenario": scenario,
            "order": order,
            "wiring": "PASSED",
            "scores": {
                c: grade(r["response"], scenario["expected"])
                for c, r in results.items()
            },
        }
        write_json(trial / "scores.json", pair)
        pairs.append(pair)
        write_json(out / "summary.json", summarize(pairs))
        print(
            f"Pair {index + 1}/{args.trials}: {scenario['name']} verified",
            file=sys.stderr,
        )
    return summarize(pairs)


def evaluate_comparison(args, harness):
    """Run all three prompt/critic arms from one real setup per scenario."""
    if args.provider != "gemini":
        endpoint(args.ollama_url)
    else:
        gemini_api_key()
    system_prompt = args.system_prompt.resolve(strict=True)
    if not system_prompt.read_text(encoding="utf-8").strip():
        raise ValueError("System prompt file is empty")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with inference_guard(args.provider, args.ollama_url):
        if args.provider == "gemini":
            model = gemini_model_record(args.local_model)
            server = {
                "provider": "Google Gemini Developer API",
                "host": GEMINI_API_HOST,
                "sdk_version": model["sdk_version"],
            }
            show = model["model_info"]
        elif args.provider == "llama-cpp":
            if not args.model_file:
                raise ValueError("llama-cpp requires --model-file")
            model_path = args.model_file.resolve(strict=True)
            props = rpc(args.ollama_url, "/props")
            if Path(props["model_path"]).resolve(strict=True) != model_path:
                raise ValueError("Server is not serving the selected GGUF file")
            if (
                props["default_generation_settings"]["n_ctx"] != OPTIONS["num_ctx"]
                or props["total_slots"] != 1
            ):
                raise ValueError("Start llama-server with --ctx-size 8192 --parallel 1")
            model = {"name": args.local_model, "digest": file_digest(model_path)}
            server, show = props.get("build_info"), props
        else:
            model = model_record(args.ollama_url, args.local_model)
            server = rpc(args.ollama_url, "/api/version")
            show = rpc(args.ollama_url, "/api/show", {"model": args.local_model})
    metadata = {
        "model": model,
        "server": server,
        "show": show,
        "options": OPTIONS,
        "url": (
            f"https://{GEMINI_API_HOST}"
            if args.provider == "gemini"
            else args.ollama_url
        ),
        "tools": False,
        "response_cache": False,
        "provider": args.provider,
        "system_prompt": str(system_prompt),
        "variants": {
            "current": "full DRIFT prompt and the pre-change draft-only critic",
            "evidence-focused": "labeled evidence and question only; internal state and personality prompt omitted; current critic",
            "evidence-critic": "full DRIFT primary prompt; critic receives question, retrieved evidence, and draft",
        },
        "prompt_budgets": {"context_chars": 16000, "total_chars": 24000},
        "setup_policy": "one real generated setup per scenario, copied byte-for-byte to every arm and condition",
        "seed_generation": "real provider inference for all setup turns",
        "critic_generation": "real provider inference using the same model",
        "scoring": "seven-key JSON; optional single fence; normalized field labels; format scored separately",
    }
    if args.provider == "gemini":
        metadata["billing"] = (
            "Google AI Studio free tier only; no billing-enabled project"
        )
        metadata["privacy"] = (
            "synthetic evaluation data only; free-tier prompts may be used to improve Google products"
        )
        metadata["cloud_context_cap"] = (
            "Gemini API does not expose an 8192-token context cap; identical DRIFT prompt character "
            "budgets are held across ON/OFF and output is capped at 256 tokens"
        )
    metadata["runtime"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    metadata["harness_sha256"] = {
        name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in ("local_continuity.py", "restart_continuity.py")
    }
    metadata["system_prompt_sha256"] = file_digest(system_prompt)
    metadata["brain_sha256"] = file_digest(Path(harness.ROOT) / "core" / "brain.py")
    metadata["prompt_budget_sha256"] = file_digest(
        Path(harness.ROOT) / "core" / "prompt_budget.py"
    )
    write_json(out / "metadata.json", metadata)
    write_json(
        out / "scoring-rules.json",
        {
            "action_forms": ACTION_FORMS,
            "reviewer_abstentions": sorted(ABSTENTIONS),
            "other_normalization": "normalize_field in saved harness source",
            "format_compliance": "raw JSON only; one complete JSON fence is scored factually and marked a format failure",
            "invalid_json_or_wrong_keys": "zero points; counted separately",
        },
    )

    selected_scenarios = list(scenarios(harness))[: args.trials]
    write_json(out / "scenarios.json", selected_scenarios)
    arm_pairs = {variant: [] for variant in VARIANTS}
    for index, scenario in enumerate(selected_scenarios):
        name = f"{index + 1:02d}-{scenario['name']}"
        setup_dir = out / "setups" / name / "setup"
        setup_dir.mkdir(parents=True)
        write_json(out / "setups" / name / "scenario.json", scenario)
        with tempfile.TemporaryDirectory(prefix="drift-compare-") as folder:
            root = Path(folder)
            seed_root = root / "setup"
            seed_root.mkdir()
            seed_config = {
                "url": args.ollama_url,
                "model": args.local_model,
                "digest": model["digest"],
                "scenario": scenario,
                "provider": args.provider,
                "system_prompt": str(system_prompt),
                "variant": "current",
                "artifact_dir": str(setup_dir),
                **(
                    {"model_file": str(model_path)}
                    if args.provider == "llama-cpp"
                    else {}
                ),
            }
            seed_config_path = setup_dir / "config.json"
            write_json(seed_config_path, seed_config)
            seeded = harness.run_worker(seed_root, "seed", seed_config_path)
            write_json(setup_dir / "seed.json", seeded)

            for variant in VARIANTS:
                trial = out / variant / name
                trial.mkdir(parents=True)
                write_json(trial / "scenario.json", scenario)
                results = {}
                work_root = root / variant
                for condition in ("on", "off"):
                    artifacts = trial / condition
                    artifacts.mkdir()
                    condition_config = dict(
                        seed_config,
                        variant=variant,
                        artifact_dir=str(artifacts),
                    )
                    config_path = artifacts / "config.json"
                    write_json(config_path, condition_config)
                    work = work_root / condition
                    shutil.copytree(seed_root, work)
                    if condition == "off":
                        shutil.rmtree(work)
                        work.mkdir()
                order = ("on", "off") if index % 2 == 0 else ("off", "on")
                for condition in order:
                    artifacts = trial / condition
                    result = harness.run_worker(
                        work_root / condition, "probe", artifacts / "config.json"
                    )
                    results[condition] = result
                    write_json(artifacts / "result.json", result)
                    (artifacts / "response.txt").write_text(
                        result["response"], encoding="utf-8"
                    )
                assert len({seeded["pid"], *(r["pid"] for r in results.values())}) == 3
                verify_pair(results, scenario)
                pair = {
                    "scenario": scenario,
                    "order": order,
                    "wiring": "PASSED",
                    "setup_seed_pid": seeded["pid"],
                    "scores": {
                        condition: grade(result["response"], scenario["expected"])
                        for condition, result in results.items()
                    },
                }
                write_json(trial / "scores.json", pair)
                arm_pairs[variant].append(pair)
                write_json(
                    out / variant / "summary.json", summarize(arm_pairs[variant])
                )
        write_json(
            out / "comparison-summary.json",
            {
                variant: summarize(pairs)
                for variant, pairs in arm_pairs.items()
                if pairs
            },
        )
        print(
            f"Scenario {index + 1}/{args.trials}: {scenario['name']} verified in all arms",
            file=sys.stderr,
        )
    return {variant: summarize(pairs) for variant, pairs in arm_pairs.items()}


def rescore(directory):
    pairs = []
    for path in sorted(Path(directory).glob("[0-9][0-9]-*/scenario.json")):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        pairs.append(
            {
                "scenario": scenario,
                "scores": {
                    condition: grade(
                        (path.parent / condition / "response.txt").read_text(
                            encoding="utf-8"
                        ),
                        scenario["expected"],
                    )
                    for condition in ("on", "off")
                },
            }
        )
    if not pairs:
        raise ValueError("No completed response pairs in this directory")
    return summarize(pairs)


def rescore_comparison(directory):
    """Offline rescore all prompt/critic arms in a shared-setup comparison."""
    root = Path(directory)
    return {variant: rescore(root / variant) for variant in VARIANTS}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Rescore saved local continuity answers offline"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--rescore", type=Path)
    group.add_argument("--rescore-comparison", type=Path)
    args = parser.parse_args()
    result = (
        rescore_comparison(args.rescore_comparison)
        if args.rescore_comparison
        else rescore(args.rescore)
    )
    print(json.dumps(result, indent=2))

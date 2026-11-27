"""DRIFT-S1-LIVE-01. Single authorized run; no production agent fallback.
The paired intervention is the exact strategy block emitted by the real builder.
All fixture evidence is synthetic and scored against a frozen answer key.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from decimal import Decimal

MODEL = "gemini-3.1-flash-lite"
PRIOR_CALLS = 2  # run 45925243900: models.get + failed count_tokens
PRIOR_RESERVED = Decimal("0.02")
MAX_CALLS = 20
MAX_USD = Decimal("1.00")
MAX_INPUT = 20000
MAX_MODEL_OUTPUT = 65536
MAX_OUTPUT = 64
# Standard text rates verified 2026-11-26:
# https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite
INPUT_RATE = Decimal("0.25")
OUTPUT_RATE = Decimal("1.50")
MILLION = Decimal(1000000)
# Reserve for the *entire* documented model output limit, not merely the
# requested 64 tokens, and for a bounded text prompt. No tools or caching.
GENERATE_RESERVE = (MAX_INPUT * INPUT_RATE + MAX_MODEL_OUTPUT * OUTPUT_RATE) / MILLION
META_RESERVE = Decimal("0.01")
CASES = (
    ("parser-repair", "retry-unchanged", "inspect-cause",
     "A log parser repeatedly fails on a new record. A: retry the unchanged parser. B: inspect the failing record and error cause.", "B"),
    ("schema-repair", "guess-schema", "validate-schema",
     "A database migration reports a column type mismatch. A: validate the actual schema before changing it. B: guess the schema from the name.", "A"),
    ("cache-repair", "reuse-stale", "refresh-cache",
     "A cache serves a superseded value after the source changed. A: reuse the stale entry. B: refresh the entry from the source.", "B"),
    ("config-repair", "assume-default", "check-config",
     "A service behaves differently in staging and production. A: compare the effective configuration. B: assume both use defaults.", "A"),
)
PREFIX = "[Verified strategy selection] "


def emit(path, item):
    line = json.dumps(item, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


class Budget:
    def __init__(self, path, *, prior_calls=0, prior_reserved=Decimal(0)):
        self.path = path
        if path.exists():
            raise RuntimeError("refuse to reuse live attempt ledger")
        self.calls = prior_calls
        self.reserved = prior_reserved
        if prior_calls or prior_reserved:
            emit(self.path, {"prior_run": 45925243900, "prior_calls": prior_calls,
                             "prior_reserved_usd": str(prior_reserved)})

    def reserve(self, operation, amount):
        if amount < 0 or self.calls >= MAX_CALLS or self.reserved + amount > MAX_USD:
            raise RuntimeError("budget exceeded before provider call")
        self.calls += 1
        self.reserved += amount
        emit(self.path, {"attempt": self.calls, "operation": operation,
                         "reserved_usd": str(self.reserved)})


def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def extract_block(prompt):
    lines = [line for line in prompt.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        raise RuntimeError("missing or duplicate strategy block")
    return lines[0]


def paired_prompts(control, treatment):
    a, b = extract_block(control), extract_block(treatment)
    if a == b:
        raise RuntimeError("correction did not change strategy")
    # Freeze all non-treatment content from the actual control prompt.
    # The only replacement is the exact block independently produced by
    # the corrected reader, rather than manually inventing a strategy.
    return control, control.replace(a, b, 1)


def score(text, answer):
    return text.strip() == answer


def _subprocess(code, args, env):
    p = subprocess.run([sys.executable, "-c", code, *map(str, args)],
                       env=env, capture_output=True, text=True, timeout=90)
    if p.returncode:
        raise RuntimeError("offline subprocess failed: " + p.stderr[-3000:])
    return json.loads(p.stdout.splitlines()[-1])


def prepare(root):
    from test_stage1_conversational_learning import WRITER, READER
    root.mkdir(parents=True, exist_ok=False)
    items = []
    for task, wrong, right, question, answer in CASES:
        arms = {}
        for condition in ("uncorrected", "corrected"):
            arm = root / task / condition
            arm.mkdir(parents=True)
            db = arm / "learning.db"
            env = dict(os.environ)
            for k in ("API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                      "GROQ_API_KEY", "KIMI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"):
                env.pop(k, None)
            env.update({"DRIFT_OS_ROOT": str(arm / "state"),
                        "DRIFT_VAULT_PATH": str(arm / "state" / "vault.jsonl"),
                        "DRIFT_VAULT_SECRET": secrets.token_hex(32),
                        "DRIFT_USE_LOCAL_EMBEDDINGS": "1",
                        "ANONYMIZED_TELEMETRY": "False", "HF_HUB_OFFLINE": "1"})
            w = _subprocess(WRITER, [db, task, wrong, right, condition], env)
            reader_code = READER.replace(
                '"What is the next troubleshooting step?"',
                'sys.argv[5] + " Reply with exactly A or B, no explanation."')
            # The existing reader unpacks all args, so keep its first four.
            reader_code = reader_code.replace("sys.argv[1:]", "sys.argv[1:5]")
            r = _subprocess(reader_code, [db, task, wrong, right, question], env)
            if w["pid"] == r["pid"]:
                raise RuntimeError("reader did not restart")
            expected_selection = wrong if condition == "uncorrected" else right
            if r["selection"] != expected_selection:
                raise RuntimeError("unexpected strategy selection")
            with sqlite3.connect(db) as conn:
                rows = conn.execute("SELECT id,outcome,corrects_id FROM cognitive_evidence ORDER BY id").fetchall()
            if len(rows) != (1 if condition == "uncorrected" else 2):
                raise RuntimeError("evidence history mismatch")
            if rows[0][1:] != ("success", None):
                raise RuntimeError("initial evidence mismatch")
            if condition == "corrected" and rows[1][1:] != ("failure", rows[0][0]):
                raise RuntimeError("correction link mismatch")
            arms[condition] = {"writer_pid": w["pid"], "reader_pid": r["pid"],
                               "selection": r["selection"], "evidence": rows,
                               "raw_prompt": r["prompt"]}
        a, b = paired_prompts(arms["uncorrected"]["raw_prompt"], arms["corrected"]["raw_prompt"])
        for condition, prompt in (("uncorrected", a), ("corrected", b)):
            if len(prompt.encode()) > MAX_INPUT:
                raise RuntimeError("text input too large")
            item = dict(arms[condition], task=task, condition=condition, prompt=prompt,
                        prompt_sha256=digest(prompt), answer=answer)
            items.append(item)
    (root / "prepared.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(json.dumps({"prepared": len(items), "commit": os.environ.get("GITHUB_SHA")}), flush=True)
    return items


def live(root):
    from google import genai
    from google.genai import types
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise RuntimeError("authorized one-shot run; re-runs prohibited")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("INCONCLUSIVE: Gemini credential unavailable")
    items = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
    if len(items) != 8:
        raise RuntimeError("invalid prepared trial count")
    budget = Budget(root / "attempts.jsonl", prior_calls=PRIOR_CALLS, prior_reserved=PRIOR_RESERVED)
    if budget.calls + 17 > MAX_CALLS or budget.reserved + 9 * META_RESERVE + 8 * GENERATE_RESERVE > MAX_USD:
        raise RuntimeError("remaining authorization insufficient")
    receipts = root / "receipts.jsonl"
    # Explicit key, Developer API, no auto-routing through other providers.
    client = genai.Client(api_key=key, vertexai=False, http_options=types.HttpOptions(
        timeout=30000, retry_options=types.HttpRetryOptions(attempts=1)))
    budget.reserve("models.get", META_RESERVE)
    model = client.models.get(model=MODEL)
    if model.name != "models/" + MODEL or not model.output_token_limit or model.output_token_limit > MAX_MODEL_OUTPUT:
        raise RuntimeError("model identity or output ceiling unsupported")
    emit(receipts, {"model_metadata": model.name, "output_token_limit": model.output_token_limit})
    # Counterbalance order by task so corrected is not always second.
    ordered = [item for i in range(0, len(items), 2)
               for item in (items[i:i+2] if (i//2)%2 == 0 else items[i:i+2][::-1])]
    seen = set()
    results = []
    for item in ordered:
        prompt = item["prompt"]
        if digest(prompt) != item["prompt_sha256"]:
            raise RuntimeError("prepared prompt integrity failure")
        budget.reserve("count_tokens", META_RESERVE)
        counted = client.models.count_tokens(model=MODEL, contents=prompt)
        if counted.total_tokens is None or not 0 < counted.total_tokens <= MAX_INPUT:
            raise RuntimeError("input token bound invalid")
        budget.reserve("generate_content", GENERATE_RESERVE)
        response = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(temperature=0, candidate_count=1,
                max_output_tokens=MAX_OUTPUT, thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")))
        usage = response.usage_metadata
        response_id = response.response_id
        model_version = response.model_version
        text = response.text or ""
        receipt = {"task": item["task"], "condition": item["condition"],
                   "writer_pid": item["writer_pid"], "reader_pid": item["reader_pid"],
                   "selected": item["selection"], "prompt_sha256": item["prompt_sha256"],
                   "counted_input_tokens": counted.total_tokens, "provider": "google.genai",
                   "response_id": response_id, "model_version": model_version,
                   "text": text, "usage": usage.model_dump(mode="json") if usage else None,
                   "finish_reason": str(response.candidates[0].finish_reason) if response.candidates else None}
        emit(receipts, receipt)
        if not response_id or response_id in seen or not model_version or not model_version.startswith(MODEL):
            raise RuntimeError("missing, duplicate, or wrong provider identity")
        if not usage or usage.prompt_token_count is None or usage.total_token_count is None:
            raise RuntimeError("missing usage evidence")
        if usage.cached_content_token_count:
            raise RuntimeError("cached tokens detected")
        if usage.prompt_token_count > MAX_INPUT or (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0) > MAX_MODEL_OUTPUT:
            raise RuntimeError("provider usage exceeds reserved envelope")
        if not response.candidates or str(response.candidates[0].finish_reason).split(".")[-1] != "STOP" or not text.strip():
            raise RuntimeError("incomplete provider response")
        seen.add(response_id)
        results.append({"task": item["task"], "condition": item["condition"],
                        "correct": score(text, item["answer"]), "answer": item["answer"], "text": text})
    summary = {c: sum(r["correct"] for r in results if r["condition"] == c)
               for c in ("uncorrected", "corrected")}
    emit(root / "scores.jsonl", {"results": results, "scores": summary,
          "attempted_provider_calls": budget.calls, "reserved_usd": str(budget.reserved),
          "status": "COMPLETE_PILOT_NOT_GENERALIZATION"})
    client.close()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("prepare", "live"):
        raise SystemExit("usage: stage1_live_01.py prepare|live OUTPUT_DIRECTORY")
    try:
        (prepare if sys.argv[1] == "prepare" else live)(Path(sys.argv[2]))
    except Exception as exc:
        # Do not print provider exception messages containing request metadata.
        if sys.argv[1] == "live":
            status = getattr(exc, "code", None)
            print("INCONCLUSIVE:", type(exc).__name__, "http_code:", status if isinstance(status, int) else None, flush=True)
        else:
            print("PREPARE FAILED:", str(exc), flush=True)
        raise SystemExit(1)

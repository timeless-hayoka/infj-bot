"""Matched-history RCCE experiment. See docs/RCCE_BUDGET_PROTOCOL.md."""

import hashlib
import itertools
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from rcce_live_ab_exploratory import failure_details

SEED = 11621
CONTEXTS = ("copper", "indigo", "quartz")
ARMS = ("organized", "replay")
PROFILES = tuple(f"P{i}" for i in range(8))
PROMPT_BYTE_LIMIT = 5000
PROMPT_TOKEN_LIMIT = 1600
SCHEMA = {
    "type": "object",
    "properties": {"choice": {"type": "string", "enum": ["A", "B"]}},
    "required": ["choice"],
    "additionalProperties": False,
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def latest_rule(profile, context):
    return ("fast", "cheap")[(int(profile[1:]) >> CONTEXTS.index(context)) & 1]


def prepare(folder):
    """Generate reproducible synthetic feedback, then close the training process."""
    folder.mkdir(parents=True, exist_ok=False)
    rng = random.Random(SEED)
    histories = {}
    for profile in PROFILES:
        rows = []
        for context in CONTEXTS:
            current = latest_rule(profile, context)
            previous = "cheap" if current == "fast" else "fast"
            rows.extend(
                [
                    (rng.randint(1, 15), profile, context, current, True),
                    (rng.randint(21, 35), profile, context, previous, True),
                    (rng.randint(41, 55), profile, context, previous, True),
                    (rng.randint(61, 75), profile, context, current, True),
                    (rng.randint(81, 95), profile, context, previous, False),
                ]
            )
        for _ in range(36):
            # Some distractors are verified and more recent than the actual change.
            other = rng.choice([p for p in PROFILES if p != profile])
            subject, context = rng.choice(
                [(profile, "amber"), (other, rng.choice(CONTEXTS)), (other, "jade")]
            )
            rows.append(
                (
                    rng.randint(1, 110),
                    subject,
                    context,
                    rng.choice(("fast", "cheap")),
                    True,
                )
            )
        rng.shuffle(rows)
        path = folder / f"{profile}.json"
        text = json.dumps(rows, separators=(",", ":"))
        path.write_text(text)
        histories[profile] = digest(text)
    (folder / "manifest.json").write_text(
        json.dumps({"training_pid": os.getpid(), "histories": histories})
    )


def build_prompt(rows, profile, context, options, arm):
    if arm == "organized":
        rows = [
            max(
                (
                    row
                    for row in rows
                    if row[1] == profile and row[2] == context and row[4]
                ),
                key=lambda row: row[0],
            )
        ]
    history = "\n".join(
        f"Review {day:03d} | {subject} | {label} | prefers {rule} | {'verified' if verified else 'unverified'}"
        for day, subject, label, rule, verified in rows
    )
    question = (
        f"Make a choice for {profile} in context {context}. "
        "Find that profile's latest verified preference for that context by review number. "
        "Ignore unverified feedback, other profiles and other contexts. "
        "Fast means minimize total minutes. Cheap means minimize total credits. "
        "For each option compute total minutes as setup minutes plus jobs times minutes per job. "
        "Compute total credits as fixed credits plus jobs times credits per job.\n"
        f"{options}\nFeedback records (unordered):\n{history}"
    )
    if len(question.encode()) > PROMPT_BYTE_LIMIT:
        raise ValueError("prompt exceeds common preflight byte limit")
    return question


def make_cases():
    rng = random.Random(SEED + 1)
    cases = []
    for profile, context, index in itertools.product(PROFILES, CONTEXTS, range(3)):
        jobs = rng.randint(3, 9)
        floor = rng.randint(2, 5)
        upper = floor + rng.randint(3, 6)
        # Setup and fixed fees vary, but per-job margins guarantee opposed winners.
        fast = (rng.randint(2, 7), floor, rng.randint(2, 7), upper)
        cheap = (rng.randint(2, 7), upper, rng.randint(2, 7), floor)
        pair = [fast, cheap]
        rng.shuffle(pair)
        statements = [f"Jobs: {jobs}"]
        for label, (setup, minutes, fee, credits) in zip(("A", "B"), pair, strict=True):
            statements.append(
                f"Option {label}: {setup} setup minutes, {minutes} minutes/job, "
                f"{fee} fixed credits, {credits} credits/job."
            )
        rule = latest_rule(profile, context)
        metric = 0 if rule == "fast" else 2
        totals = [option[metric] + jobs * option[metric + 1] for option in pair]
        expected = "A" if totals[0] < totals[1] else "B"
        arms = list(ARMS)
        rng.shuffle(arms)
        cases.append((profile, context, index, "\n".join(statements), expected, arms))
    rng.shuffle(cases)
    return cases


def decode_choice(text):
    try:
        fields = json.loads(text, object_pairs_hook=list)
    except ValueError:
        return None
    for choice in ("A", "B"):
        if fields == [("choice", choice)]:
            return choice
    return None


def tail_sign(successes, n):
    return sum(math.comb(n, k) for k in range(successes, n + 1)) / 2**n


def analyze(trials):
    pairs = defaultdict(dict)
    for row in trials:
        key = (row["profile"], row["context"], row["instance"])
        if row["arm"] not in ARMS or row["arm"] in pairs[key]:
            raise ValueError("invalid or duplicate arm")
        pairs[key][row["arm"]] = row
    required = set(itertools.product(PROFILES, CONTEXTS, range(3)))
    if set(pairs) != required or any(set(pair) != set(ARMS) for pair in pairs.values()):
        raise ValueError("incomplete paired experiment")
    totals = {
        arm: {
            "correct": sum(pair[arm]["correct"] for pair in pairs.values()),
            "valid": sum(pair[arm]["choice"] is not None for pair in pairs.values()),
            "prompt_tokens": sum(pair[arm]["prompt_tokens"] for pair in pairs.values()),
        }
        for arm in ARMS
    }
    deltas = [
        sum(
            int(pair["organized"]["correct"]) - int(pair["replay"]["correct"])
            for key, pair in pairs.items()
            if key[0] == profile
        )
        / 9
        for profile in PROFILES
    ]
    gain = sum(deltas) / len(deltas)
    savings = (
        1 - totals["organized"]["prompt_tokens"] / totals["replay"]["prompt_tokens"]
    )
    p_advantage = tail_sign(sum(delta > 0 for delta in deltas), len(deltas))
    p_noninferior = tail_sign(sum(delta > -0.05 for delta in deltas), len(deltas))
    verdict = "inconclusive"
    if any(totals[arm]["valid"] != len(pairs) for arm in ARMS):
        verdict = "measurement_failed"
    elif gain >= 0.10 and p_advantage <= 0.05:
        verdict = "organized_accuracy_advantage"
    elif p_noninferior <= 0.05 and savings >= 0.25:
        verdict = "organized_token_efficiency"
    elif p_noninferior <= 0.05 and abs(gain) <= 0.05 and abs(savings) <= 0.05:
        verdict = "use_replay_matched"
    elif (
        gain <= -0.10
        and tail_sign(sum(delta < 0 for delta in deltas), len(deltas)) <= 0.05
    ):
        verdict = "use_replay_accuracy"
    return {
        "pairs": len(pairs),
        "arms": totals,
        "profile_accuracy_deltas": deltas,
        "accuracy_gain": gain,
        "prompt_token_savings": savings,
        "p_advantage": p_advantage,
        "p_noninferiority": p_noninferior,
        "verdict": verdict,
    }


def execute(folder, output):
    from google import genai
    from google.genai import types

    run = {"status": "started", "trials": [], "seed": SEED}
    output.write_text(json.dumps(run))
    try:
        subprocess.run([sys.executable, __file__, "prepare", str(folder)], check=True)
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest["training_pid"] == os.getpid() or set(manifest["histories"]) != set(
            PROFILES
        ):
            raise RuntimeError("invalid training manifest or process boundary")
        histories = {}
        for profile, checksum in manifest["histories"].items():
            text = (folder / f"{profile}.json").read_text()
            if digest(text) != checksum:
                raise RuntimeError("training history hash mismatch")
            histories[profile] = json.loads(text)

        model = os.environ["DRIFT_PRIMARY_MODEL"]
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=SCHEMA,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=5,
                    initial_delay=8,
                    max_delay=60,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                )
            ),
        )
        run.update(
            status="in_progress",
            training=manifest,
            evaluation_pid=os.getpid(),
            model=model,
            commit=os.environ.get("GITHUB_SHA"),
            shared_prompt_token_cap=PROMPT_TOKEN_LIMIT,
        )
        with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
            for profile, context, instance, options, expected, arms in make_cases():
                for arm in arms:
                    prompt = build_prompt(
                        histories[profile], profile, context, options, arm
                    )
                    run["active_trial"] = {
                        "profile": profile,
                        "context": context,
                        "instance": instance,
                        "arm": arm,
                    }
                    response = client.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    raw = response.text or ""
                    tokens = getattr(
                        response.usage_metadata, "prompt_token_count", None
                    )
                    rid = response.response_id
                    if (
                        not rid
                        or not isinstance(tokens, int)
                        or not 0 < tokens <= PROMPT_TOKEN_LIMIT
                    ):
                        raise RuntimeError(
                            "missing provider receipt or shared prompt cap exceeded"
                        )
                    choice = decode_choice(raw)
                    run["trials"].append(
                        {
                            **run.pop("active_trial"),
                            "history_sha256": manifest["histories"][profile],
                            "prompt_sha256": digest(prompt),
                            "prompt_tokens": tokens,
                            "prompt": prompt,
                            "provider_response_id": rid,
                            "raw": raw,
                            "raw_sha256": digest(raw),
                            "model_version": response.model_version,
                            "choice": choice,
                            "expected": expected,
                            "correct": choice == expected,
                        }
                    )
                    output.write_text(json.dumps(run, indent=2))
        if len({row["provider_response_id"] for row in run["trials"]}) != len(
            run["trials"]
        ):
            raise RuntimeError("duplicate provider response ID")
        if (
            len({row["model_version"] for row in run["trials"]}) != 1
            or not run["trials"][0]["model_version"]
        ):
            raise RuntimeError("missing or inconsistent provider model version")
        run.update(status="complete", summary=analyze(run["trials"]))
        print(json.dumps(run["summary"], sort_keys=True))
        return 0
    except Exception as exc:
        run.update(status="failed", **failure_details(exc))
        print(json.dumps(failure_details(exc), sort_keys=True), file=sys.stderr)
        return 1
    finally:
        output.write_text(json.dumps(run, indent=2))


if __name__ == "__main__":
    mode, destination, *rest = sys.argv[1:]
    if mode == "prepare":
        prepare(Path(destination))
    elif mode == "evaluate":
        raise SystemExit(execute(Path(destination), Path(rest[0])))
    else:
        raise SystemExit("expected prepare or evaluate")

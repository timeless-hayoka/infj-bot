"""Three-way RCCE test with corrections, exceptions and structured choices."""

import itertools
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from drift.core.rcce_feedback import Feedback, relevant_feedback, resolve_feedback
from rcce_budget_study import (
    CONTEXTS,
    PROFILES,
    PROMPT_BYTE_LIMIT,
    PROMPT_TOKEN_LIMIT,
    SCHEMA,
    decode_choice,
    digest,
    tail_sign,
)
from rcce_live_ab_exploratory import failure_details

ARMS = ("full", "filtered", "organized")
SCOPES = ("rush", "fragile", "standard")
SEED = 80421


def preference(profile, context):
    return ("fast", "cheap")[(int(profile[1:]) >> CONTEXTS.index(context)) & 1]


def inverse(rule):
    return "cheap" if rule == "fast" else "fast"


def tasks():
    """Draw two held-out decisions per context, including a live exception."""
    rng = random.Random(SEED + 1)
    cases = []
    for profile, context in itertools.product(PROFILES, CONTEXTS):
        other_scope = SCOPES[1 + (int(profile[1:]) + CONTEXTS.index(context)) % 2]
        for scope in ("rush", other_scope):
            jobs, gap = rng.randint(4, 11), rng.randint(3, 5)
            slow = rng.randint(2, 6) + gap
            expensive = rng.randint(4, 9) + gap
            fast = (rng.randint(1, 6), slow - gap, rng.randint(1, 6), expensive)
            cheap = (rng.randint(1, 6), slow, rng.randint(1, 6), expensive - gap)
            options = [fast, cheap]
            rng.shuffle(options)
            rule = preference(profile, context)
            if scope == "rush":
                rule = inverse(rule)
            index = 0 if rule == "fast" else 2
            amounts = [option[index] + jobs * option[index + 1] for option in options]
            expected = "A" if amounts[0] < amounts[1] else "B"
            arms = list(ARMS)
            rng.shuffle(arms)
            cases.append((profile, context, scope, jobs, options, expected, arms))
    rng.shuffle(cases)
    return cases


def histories():
    rng = random.Random(SEED)
    for profile in PROFILES:
        rows = []
        for index, context in enumerate(CONTEXTS):
            base = index * 100
            current = preference(profile, context)
            opposite = inverse(current)
            rows.extend(
                [
                    Feedback(base + 9, profile, context, "default", opposite),
                    Feedback(base + 21, profile, context, "default", current),
                    Feedback(base + 31, profile, context, "rush", opposite),
                    Feedback(base + 42, profile, context, "fragile", opposite),
                    Feedback(base + 54, profile, context, "rush", current),
                    Feedback(base + 63, profile, context, "default", opposite),
                    Feedback(
                        base + 71, profile, context, "fragile", retracts=base + 42
                    ),
                    Feedback(base + 75, profile, context, "rush", retracts=base + 54),
                    Feedback(
                        base + 82, profile, context, "default", retracts=base + 63
                    ),
                    Feedback(
                        base + 93, profile, context, "rush", current, verified=False
                    ),
                ]
            )
        for review in range(300, 321):
            other = rng.choice([person for person in PROFILES if person != profile])
            subject, context = rng.choice(
                [(profile, "amber"), (other, rng.choice(CONTEXTS))]
            )
            rows.append(
                Feedback(
                    review,
                    subject,
                    context,
                    rng.choice(SCOPES),
                    rng.choice(("fast", "cheap")),
                )
            )
        rng.shuffle(rows)
        yield profile, rows


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for profile, rows in histories():
        text = json.dumps(
            [asdict(row) for row in rows], sort_keys=True, separators=(",", ":")
        )
        (folder / f"{profile}.json").write_text(text)
        hashes[profile] = digest(text)
    (folder / "manifest.json").write_text(
        json.dumps({"pid": os.getpid(), "histories": hashes})
    )


def build_prompt(rows, profile, context, scope, jobs, options, arm):
    if arm == "filtered":
        rows = relevant_feedback(rows, profile, context, scope)
    elif arm == "organized":
        selected = resolve_feedback(rows, profile, context, scope)
        if selected is None:
            raise ValueError("missing verified applicable decision rule")
        rows = [selected]
    choice_lines = [
        f"{label}: setup {setup} minutes, {minutes} minutes/job, fixed {fee} credits, {credits} credits/job."
        for label, (setup, minutes, fee, credits) in zip("AB", options, strict=True)
    ]
    # Keep the record representation and all task instructions identical across arms.
    feedback = "\n".join(
        f"{row.review:03d} {row.profile} {row.context} {row.scope} "
        f"{'verified' if row.verified else 'unverified'} "
        + (
            f"retracts {row.retracts:03d}"
            if row.retracts is not None
            else f"prefers {row.preference}"
        )
        for row in rows
    )
    task = (
        f"Choose for {profile} in context {context}, task scope {scope}. "
        "Apply verified records for this profile and context only. A verified retraction removes its "
        "target review. The newest active exact-scope preference overrides the newest active default. "
        "Fast means minimize setup minutes plus jobs times minutes/job. Cheap means minimize fixed "
        f"credits plus jobs times credits/job. Jobs: {jobs}.\n"
        + "\n".join(choice_lines)
        + f"\nFeedback:\n{feedback}"
    )
    if len(task.encode()) > PROMPT_BYTE_LIMIT:
        raise ValueError("shared prompt byte cap exceeded")
    return task


def summarize(rows):
    blocks = defaultdict(dict)
    for row in rows:
        key = row["profile"], row["context"], row["scope"]
        if row["arm"] not in ARMS or row["arm"] in blocks[key]:
            raise ValueError("invalid or duplicate arm")
        blocks[key][row["arm"]] = row
    expected = {case[:3] for case in tasks()}
    if set(blocks) != expected or any(
        set(block) != set(ARMS) for block in blocks.values()
    ):
        raise ValueError("incomplete paired cases")
    total = {
        arm: {
            "correct": sum(block[arm]["correct"] for block in blocks.values()),
            "valid": sum(block[arm]["choice"] is not None for block in blocks.values()),
            "prompt_tokens": sum(
                block[arm]["prompt_tokens"] for block in blocks.values()
            ),
        }
        for arm in ARMS
    }
    deltas = [
        sum(
            int(block["organized"]["correct"]) - int(block["filtered"]["correct"])
            for key, block in blocks.items()
            if key[0] == profile
        )
        / 6
        for profile in PROFILES
    ]
    gain = sum(deltas) / len(deltas)
    savings = (
        1 - total["organized"]["prompt_tokens"] / total["filtered"]["prompt_tokens"]
    )
    p_adv = tail_sign(sum(delta > 0 for delta in deltas), len(deltas))
    p_noninf = tail_sign(sum(delta > -0.05 for delta in deltas), len(deltas))
    p_reverse_noninf = tail_sign(sum(delta < 0.05 for delta in deltas), len(deltas))
    verdict = "inconclusive"
    if any(total[arm]["valid"] != len(blocks) for arm in ARMS):
        verdict = "measurement_failed"
    elif gain >= 0.10 and p_adv <= 0.05:
        verdict = "organizer_accuracy"
    elif gain >= -0.05 and p_noninf <= 0.05 and savings >= 0.25:
        verdict = "organizer_efficiency"
    elif (
        max(p_noninf, p_reverse_noninf) <= 0.05
        and abs(gain) <= 0.05
        and abs(savings) <= 0.05
    ):
        verdict = "use_filtered_equivalent"
    elif (
        gain <= -0.10
        and tail_sign(sum(delta < 0 for delta in deltas), len(deltas)) <= 0.05
    ):
        verdict = "use_filtered_accuracy"
    return {
        "pairs": len(blocks),
        "arms": total,
        "profile_deltas": deltas,
        "accuracy_gain": gain,
        "token_savings": savings,
        "p_advantage": p_adv,
        "p_noninferiority": p_noninf,
        "p_reverse_noninferiority": p_reverse_noninf,
        "verdict": verdict,
    }


def evaluate(folder, output):
    from google import genai
    from google.genai import types

    run = {"status": "started", "trials": [], "seed": SEED}
    output.write_text(json.dumps(run))
    try:
        subprocess.run([sys.executable, __file__, "prepare", str(folder)], check=True)
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest["pid"] == os.getpid() or set(manifest["histories"]) != set(
            PROFILES
        ):
            raise RuntimeError("invalid training manifest or process boundary")
        banks = {}
        for profile, checksum in manifest["histories"].items():
            content = (folder / f"{profile}.json").read_text()
            if digest(content) != checksum:
                raise RuntimeError("history checksum mismatch")
            banks[profile] = [Feedback(**row) for row in json.loads(content)]
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
            for profile, context, scope, jobs, options, expected, arms in tasks():
                for arm in arms:
                    run["active_trial"] = dict(
                        profile=profile, context=context, scope=scope, arm=arm
                    )
                    prompt = build_prompt(
                        banks[profile], profile, context, scope, jobs, options, arm
                    )
                    response = client.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    raw = response.text or ""
                    tokens = getattr(
                        response.usage_metadata, "prompt_token_count", None
                    )
                    if (
                        not response.response_id
                        or not isinstance(tokens, int)
                        or not 0 < tokens <= PROMPT_TOKEN_LIMIT
                    ):
                        raise RuntimeError(
                            "missing provider evidence or shared token cap exceeded"
                        )
                    choice = decode_choice(raw)
                    run["trials"].append(
                        {
                            **run.pop("active_trial"),
                            "history_sha256": manifest["histories"][profile],
                            "prompt": prompt,
                            "prompt_sha256": digest(prompt),
                            "prompt_tokens": tokens,
                            "raw": raw,
                            "raw_sha256": digest(raw),
                            "choice": choice,
                            "expected": expected,
                            "correct": choice == expected,
                            "provider_response_id": response.response_id,
                            "model_version": response.model_version,
                        }
                    )
                    output.write_text(json.dumps(run, indent=2))
        if len({row["provider_response_id"] for row in run["trials"]}) != len(
            run["trials"]
        ):
            raise RuntimeError("duplicate provider response")
        versions = {row["model_version"] for row in run["trials"]}
        if len(versions) != 1 or not next(iter(versions)):
            raise RuntimeError("missing or inconsistent provider model version")
        summary = summarize(run["trials"])
        run.update(status="complete", summary=summary)
        print(json.dumps(summary, sort_keys=True))
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
        raise SystemExit(evaluate(Path(destination), Path(rest[0])))
    else:
        raise SystemExit("expected prepare or evaluate")

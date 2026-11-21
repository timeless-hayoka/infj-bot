"""Paired live diagnostic of arithmetic versus preference selection in RCCE."""

import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

from drift.core.rcce_feedback import Feedback, resolve_feedback
from rcce_budget_study import (
    PROFILES,
    PROMPT_BYTE_LIMIT,
    PROMPT_TOKEN_LIMIT,
    digest,
    tail_sign,
)
from rcce_filtered_replay_study import build_prompt, preference, prepare, tasks
from rcce_live_ab_exploratory import failure_details

SEED = 644411
ARMS = ("raw_inputs", "computed_totals")
SCHEMA = {
    "type": "object",
    "properties": {
        "criterion": {"type": "string", "enum": ["fast", "cheap"]},
        "a_total": {"type": "integer"},
        "b_total": {"type": "integer"},
        "choice": {"type": "string", "enum": ["A", "B"]},
    },
    "required": ["criterion", "a_total", "b_total", "choice"],
    "additionalProperties": False,
}


def make_cases():
    rng = random.Random(SEED)
    old = tasks()
    results = []
    for profile in PROFILES:
        sample = sorted(item[:3] for item in old if item[0] == profile)
        urgent = [item for item in sample if item[2] == "rush"]
        normal = [item for item in sample if item[2] != "rush"]
        for _, context, scope in rng.sample(urgent, 2) + rng.sample(normal, 2):
            jobs = rng.randint(11, 29)
            low_time, low_cost = rng.randint(2, 11), rng.randint(3, 13)
            options = [
                (rng.randint(1, 9), low_time, rng.randint(1, 9), low_cost + 1),
                (rng.randint(1, 9), low_time + 1, rng.randint(1, 9), low_cost),
            ]
            rng.shuffle(options)
            arms = list(ARMS)
            rng.shuffle(arms)
            results.append((profile, context, scope, jobs, options, arms))
    rng.shuffle(results)
    return results


def exact_totals(jobs, options):
    return {
        "fast": [setup + jobs * minutes for setup, minutes, _, _ in options],
        "cheap": [fixed + jobs * credits for _, _, fixed, credits in options],
    }


def classify(raw, rule, totals):
    try:
        pairs = json.loads(raw, object_pairs_hook=list)
        if not isinstance(pairs, list) or not all(
            isinstance(item, tuple) for item in pairs
        ):
            return None, "invalid"
        parsed = dict(pairs)
    except (ValueError, TypeError):
        return None, "invalid"
    if (
        len(pairs) != 4
        or parsed.keys() != SCHEMA["properties"].keys()
        or parsed["choice"] not in ("A", "B")
        or parsed["criterion"] not in ("fast", "cheap")
        or any(type(parsed[key]) is not int for key in ("a_total", "b_total"))
    ):
        return None, "invalid"
    diagnostic = "consistent"
    if parsed["criterion"] != rule:
        diagnostic = "wrong_reported_criterion"
    elif [parsed["a_total"], parsed["b_total"]] != totals:
        diagnostic = "wrong_reported_totals"
    elif parsed["choice"] != ("A" if totals[0] < totals[1] else "B"):
        diagnostic = "choice_disagrees_with_correct_totals"
    return parsed, diagnostic


def summarize(rows):
    keys = {
        (profile, context, scope, arm)
        for profile, context, scope, *_ in make_cases()
        for arm in ARMS
    }
    if (
        len(rows) != len(keys)
        or {(r["profile"], r["context"], r["scope"], r["arm"]) for r in rows} != keys
    ):
        raise ValueError("incomplete or duplicate study cases")
    stats = {}
    for arm in ARMS:
        trials = [r for r in rows if r["arm"] == arm]
        stats[arm] = {
            "correct": sum(r["correct"] for r in trials),
            "total": len(trials),
            "tokens": sum(r["prompt_tokens"] for r in trials),
            "diagnostics": dict(Counter(r["diagnostic"] for r in trials)),
            "miss_diagnostics": dict(
                Counter(r["diagnostic"] for r in trials if not r["correct"])
            ),
        }
    deltas = []
    for profile in PROFILES:
        totals = Counter(
            r["arm"] for r in rows if r["profile"] == profile and r["correct"]
        )
        deltas.append((totals["computed_totals"] - totals["raw_inputs"]) / 4)
    gain = sum(deltas) / len(deltas)
    p_value = tail_sign(sum(delta > 0 for delta in deltas), len(deltas))
    verdict = "no_reliable_gain"
    if any(r["diagnostic"] == "invalid" for r in rows):
        verdict = "measurement_failed"
    elif gain >= 0.10 and p_value <= 0.05:
        verdict = "arithmetic_grounding_improves_choice"
    return {
        "arms": stats,
        "profile_deltas": deltas,
        "gain": gain,
        "p_advantage": p_value,
        "verdict": verdict,
    }


def evaluate(folder, output):
    from google import genai
    from google.genai import types

    run = {
        "status": "started",
        "commit": os.environ.get("GITHUB_SHA"),
        "seed": SEED,
        "trials": [],
    }
    output.write_text(json.dumps(run))
    try:
        subprocess.run([sys.executable, __file__, "prepare", str(folder)], check=True)
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest["pid"] == os.getpid() or set(manifest["histories"]) != set(
            PROFILES
        ):
            raise ValueError("invalid training manifest or process boundary")
        histories = {}
        for profile, checksum in manifest["histories"].items():
            data = (folder / f"{profile}.json").read_text()
            if digest(data) != checksum:
                raise ValueError("history checksum mismatch")
            histories[profile] = [Feedback(**row) for row in json.loads(data)]

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
            model=model,
            evaluation_pid=os.getpid(),
            training=manifest,
        )
        with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
            for profile, context, scope, jobs, options, arms in make_cases():
                history = histories[profile]
                selected = resolve_feedback(history, profile, context, scope)
                rule = preference(profile, context)
                if scope == "rush":
                    rule = "fast" if rule == "cheap" else "cheap"
                if not selected or selected.preference != rule:
                    raise ValueError(
                        "resolved preference does not match independent scenario rule"
                    )
                totals = exact_totals(jobs, options)
                expected = "A" if totals[rule][0] < totals[rule][1] else "B"
                base = build_prompt(
                    history, profile, context, scope, jobs, options, "organized"
                )
                base += "\nReport your criterion, each option's total under that criterion, and your choice."
                for arm in arms:
                    prompt = base
                    if arm == "computed_totals":
                        prompt += (
                            f"\nVerified arithmetic: A totals {totals['fast'][0]} minutes and {totals['cheap'][0]} credits. "
                            f"B totals {totals['fast'][1]} minutes and {totals['cheap'][1]} credits."
                        )
                    if len(prompt.encode()) > PROMPT_BYTE_LIMIT:
                        raise ValueError("shared prompt byte cap exceeded")
                    run["active_trial"] = dict(
                        profile=profile, context=context, scope=scope, arm=arm
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
                        raise ValueError(
                            "missing provider evidence or shared token cap exceeded"
                        )
                    answer, diagnostic = classify(raw, rule, totals[rule])
                    run["trials"].append(
                        {
                            **run.pop("active_trial"),
                            "history_sha256": manifest["histories"][profile],
                            "prompt": prompt,
                            "prompt_sha256": digest(prompt),
                            "prompt_tokens": tokens,
                            "raw": raw,
                            "raw_sha256": digest(raw),
                            "provider_response_id": response.response_id,
                            "model_version": response.model_version,
                            "jobs": jobs,
                            "options": options,
                            "rule": rule,
                            "totals": totals,
                            "expected": expected,
                            "answer": answer,
                            "diagnostic": diagnostic,
                            "correct": answer is not None
                            and answer["choice"] == expected,
                        }
                    )
                    output.write_text(json.dumps(run, indent=2))

        rows = run["trials"]
        if len({r["provider_response_id"] for r in rows}) != len(rows):
            raise ValueError("duplicate provider response ID")
        versions = {r["model_version"] for r in rows}
        if len(versions) != 1 or not next(iter(versions)):
            raise ValueError("missing or inconsistent provider model version")
        summary = summarize(rows)
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

"""Matched live DRIFT CLI readers with independent request and reply scoring."""

import argparse
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pilot import child_env, sha, turn
from provider import MODEL, initialize, sha256, write_json
from replay_context import FAST_CONTEXT_LIMIT, SEPARATOR, pack_whole_records
from verify import check, lines, raw_sql, read, request_text

SOURCE_COMMIT = "a71ff3333e4b2b8da6bf9d38e86ea98509435139"
SOURCE_RUN = "45499819075"
BRANCH = "refs/heads/validation/drift-memory-packing"
ARMS = ("A", "B")
EXPECTED = {
    "trial-3": (False, True),
    "short-a": (False, True),
    "short-b": (False, True),
    "long-early": (True, False),
    "long-late": (False, False),
}


def observe_packing(arm, output):
    from drift.core.causal_wiring import retrieved_memory_keys_var
    from drift.core.memory import DriftMemory

    check(arm in ARMS, "Unknown reader arm")
    retrieve = DriftMemory.retrieve_context_ranked

    def observed(self, query, n_results=5):
        retrieved_memory_keys_var.set([])
        context = retrieve(self, query, n_results=n_results)
        ids = retrieved_memory_keys_var.get()
        contents = self.unified_manager.get_contents_by_id(ids)
        records = [f"Memory: {contents[key]}" for key in ids]
        check(
            ids and SEPARATOR.join(records) == context,
            "Canonical ranked retrieval unavailable",
        )
        selected = (
            context[:FAST_CONTEXT_LIMIT] if arm == "A" else pack_whole_records(records)
        )
        write_json(
            output / "packing.json",
            {
                "arm": arm,
                "query": query,
                "ranked_ids": ids,
                "ranked_record_characters": [len(record) for record in records],
                "memory_context": selected,
                "memory_section": format_memory(selected),
            },
        )
        return context if arm == "A" else selected

    DriftMemory.retrieve_context_ranked = observed


def format_memory(context):
    from drift.core.context_optimizer import compress_prompt
    from drift.core.guardrails import memory_context_block

    return compress_prompt(memory_context_block(context))


def store_manifest(store):
    return {
        path.relative_to(store).as_posix(): sha256(path.read_bytes())
        for path in sorted(store.rglob("*"))
        if path.is_file()
    }


def original_case(source):
    check(
        read(source / "pilot.json")["commit"] == SOURCE_COMMIT,
        "Unexpected source commit",
    )
    trial = source / "3"
    fact = read(trial / "fact.json")
    question = read(trial / "reader" / "process.json")["prompt"]
    return {
        "question": question,
        "code": fact["code"],
        "target_id": "a3b0dd76-bea4-4529-aeba-cab8b1c85443",
        "historical_rank": [
            "6417ca46-2387-465d-b7fc-ed68beb03aae",
            "a3b0dd76-bea4-4529-aeba-cab8b1c85443",
        ],
    }, trial / "writer-store"


def seed_fresh(case, output):
    from drift.core.memory import DriftMemory
    from drift.core.unified_memory import Event

    output.mkdir()
    specimen = f"orchid-{secrets.token_hex(5)}"
    code = f"violet-{secrets.token_hex(8)}"
    question = (
        f"What field sample color code did I give you for specimen {specimen}? "
        "Reply with just the code if you remember it."
    )
    fact = f"Field sample color code for specimen {specimen} is {code}."
    notes = (
        "The field team logged sample weight, soil texture, air temperature, "
        "and equipment calibration in the daily notebook. "
    ) * 17
    store = output / "store"
    memory = DriftMemory(persist_directory=str(store))
    manager = memory.unified_manager
    embed = memory.embedding_function.embed_one
    query_vector = embed(question)
    contents = {
        "long-early": f"{notes[:650]}\n{fact}\n{notes}",
        "long-late": notes + fact,
    }
    short = case.startswith("short-")
    target = contents.get(case, fact)

    def distance(record):
        return math.dist(query_vector, embed(record))

    # Select text variants that exercise the real hash-based retrieval ranking.
    # Freeze the resulting records before either reader opens the stores.
    if short:
        for variant in range(10_000):
            candidate = f"{fact} Recorded on sample card {variant}."
            if 1.10 < distance(candidate) < 1.30:
                target = candidate
                break
        else:
            raise RuntimeError("Could not seed a retrievable short fact")
        for variant in range(10_000):
            distractor = f"Specimen {specimen}, field note batch {variant}.\n{notes}"
            if distance(distractor) < 0.99:
                distractor_id = manager.remember_sync(
                    Event("interaction", distractor), {"category": "field_notes"}
                )
                break
        else:
            raise RuntimeError("Could not seed a higher-ranked long distraction")
    target_id = manager.remember_sync(Event("interaction", target), {})
    rank = [distractor_id, target_id] if short else [target_id]
    write_json(
        output / "fact.json",
        {
            "question": question,
            "code": code,
            "target_id": target_id,
            "historical_rank": rank,
        },
    )


def preflight(arm, root, question, output):
    from drift.core.cognitive_orchestrator import CognitiveOrchestrator
    from drift.core.commands import BotState
    from drift.core.memory import DriftMemory
    from drift.core.security_defense import _security_logger

    _security_logger.path = root / "security_audit.jsonl"
    observe_packing(arm, output)
    memory = DriftMemory()
    prompt, _, _ = CognitiveOrchestrator().assemble_prompt(question, BotState(), memory)
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")


def check_rank(folder, arm, fact):
    packing = read(folder / "packing.json")
    context = packing["memory_context"]
    check(
        packing["arm"] == arm and packing["query"] == fact["question"],
        "Packing trace mismatch",
    )
    check(packing["ranked_ids"] == fact["historical_rank"], "Retrieval rank changed")
    check(
        len(context) <= FAST_CONTEXT_LIMIT, "Memory section exceeded 1,500 characters"
    )
    return context, packing


def contains_code(text, code):
    return bool(re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text))


def verify_arm(folder, arm, fact, process, ledger, case, store):
    rows = raw_sql(
        ledger,
        "SELECT id, turn, pid, started_ns, reservation FROM attempts WHERE turn IN (?, ?)",
        (f"{case}/{arm}/answer", f"{case}/{arm}/critic"),
    )
    check(len(rows) == 2, "Expected one answer and one critic attempt")
    check(
        not (folder / "provider-block.json").exists(),
        "Unexpected transport request blocked",
    )
    runtime = read(folder / "runtime.json")
    check(runtime["pid"] == process["pid"], "Runtime PID mismatch")
    check(
        runtime["sdk"] == "google.genai" and runtime["model"] == MODEL, "Wrong provider"
    )
    check(runtime["embedding"] == "LocalEmbeddingFunction", "Wrong embedding backend")
    check(
        Path(runtime["sqlite"]) == store / "unified_memory.db", "Incorrect SQLite path"
    )
    check(Path(runtime["chroma"]) == store, "Incorrect Chroma path")
    check(
        Path(runtime["history"]) == store.parent / "sqlite" / "history.db",
        "Wrong chat history",
    )
    check(
        process["exit_code"] == 0 and not process["alive_after_wait"],
        "Reader did not exit normally",
    )
    question = fact["question"]
    history = lines(folder / "history.jsonl")
    check(
        len(history) == 1 and history[0]["user"] == question,
        "Unexpected conversation history",
    )
    code = fact["code"]
    responses = {}
    for attempt, label, pid, started_ns, reservation in rows:
        kind = label.rsplit("/", 1)[-1]
        request = (folder / f"request-{attempt}.json").read_bytes()
        response = (folder / f"response-{attempt}.json").read_bytes()
        receipt = read(folder / f"receipt-{attempt}.json")
        check(pid == receipt["pid"] == process["pid"], "Provider PID mismatch")
        check(
            process["started_ns"] <= started_ns <= process["ended_ns"],
            "Attempt outside turn",
        )
        check(sha256(request) == receipt["request_sha256"], "Request hash mismatch")
        check(sha256(response) == receipt["response_sha256"], "Response hash mismatch")
        payload = json.loads(request)
        raw = json.loads(response)
        receipt = {
            "attempt": attempt,
            "status": receipt["status"],
            "response_id": raw.get("responseId"),
            "generation_config": payload["generationConfig"],
            "reserved_microdollars": reservation,
        }
        text = None
        if receipt["status"] == 200:
            check(
                raw["modelVersion"] == MODEL and receipt["response_id"],
                "Wrong Gemini model or receipt",
            )
            (candidate,) = raw["candidates"]
            if candidate["finishReason"] == "STOP":
                text = "".join(
                    part.get("text", "")
                    for part in candidate["content"]["parts"]
                    if not part.get("thought")
                )
        responses[kind] = (payload, text, receipt)

    payload, answer, _ = responses["answer"]
    context, packing = check_rank(folder, arm, fact)
    wire_prompt = request_text(payload)
    check(
        f"User: {question}" in wire_prompt, "Original user question absent on the wire"
    )
    before, actual_section, after = wire_prompt.partition(packing["memory_section"])
    check(
        bool(actual_section), "Packed memory section absent or altered on Gemini wire"
    )
    check(
        not contains_code(before + after, code),
        "Code leaked outside the memory section",
    )
    check(
        not contains_code(json.dumps(payload.get("systemInstruction", {})), code),
        "Code leaked in model system instructions",
    )
    return {
        "pid": process["pid"],
        "fact_in_gemini_prompt": contains_code(actual_section, code),
        "exact_code_in_gemini_reply": contains_code(answer, code) if answer else None,
        "exact_code_in_cli_reply": contains_code(history[0]["bot"], code),
        "reply": answer,
        "ranked_ids": packing["ranked_ids"],
        "packed_characters": len(context),
        "generation_config": payload["generationConfig"],
        "system_instruction_sha256": sha256(
            json.dumps(payload.get("systemInstruction")).encode()
        ),
        "receipts": {kind: record[2] for kind, record in responses.items()},
    }


def run_case(case, fact, source, output, key, limit, ledger):
    check(
        not contains_code(fact["question"], fact["code"]),
        "Answer leaked in user question",
    )
    check(
        {"chroma.sqlite3", "unified_memory.db"} <= set(store_manifest(source)),
        "Stores missing",
    )
    expected_manifest = store_manifest(source)
    write_json(output / "fact.json", fact)
    write_json(output / "snapshot-sha256.json", expected_manifest)
    result = {}
    with tempfile.TemporaryDirectory(prefix="drift-packing-") as folder:
        for arm in ARMS:
            root = Path(folder) / arm
            (root / "home").mkdir(parents=True)
            store = root / "drift" / "memory" / "chroma"
            shutil.copytree(source, store)
            check(
                store_manifest(store) == expected_manifest,
                "Store copy differs from frozen source",
            )
            history = store.parent / "sqlite" / "history.db"
            check(not history.exists(), "Reader would inherit chat history")
            evidence = output / arm
            if key:
                process = turn(
                    root,
                    evidence,
                    ledger,
                    key,
                    case,
                    arm,
                    fact["question"],
                    extra_env={
                        "DRIFT_AB_PACKING": arm,
                        "DRIFT_AB_CALL_LIMIT": str(limit),
                    },
                )
                check(history.is_file(), "Reader did not produce a fresh transcript")
                shutil.copyfile(history, evidence / "history.jsonl")
                write_json(evidence / "starting-state.json", {"history_present": False})
                try:
                    result[arm] = verify_arm(
                        evidence, arm, fact, process, ledger, case, store
                    )
                except (ValueError, KeyError, OSError) as exc:
                    result[arm] = {"error": str(exc)}
            else:
                evidence.mkdir()
                subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "_preflight",
                        arm,
                        str(root),
                        fact["question"],
                        str(evidence),
                    ],
                    cwd=root,
                    env=child_env(root, ""),
                    check=True,
                )
                context, packing = check_rank(evidence, arm, fact)
                prompt = (evidence / "prompt.txt").read_text(encoding="utf-8")
                before, actual_section, after = prompt.partition(
                    packing["memory_section"]
                )
                check(
                    bool(actual_section), "Application assembler dropped packed context"
                )
                check(
                    not contains_code(before + after, fact["code"]),
                    "Unexpected fact source in assembled prompt",
                )
                result[arm] = {
                    "fact_in_assembled_prompt": contains_code(prompt, fact["code"]),
                    "packed_characters": len(context),
                    "ranked_ids": packing["ranked_ids"],
                }
    if key and all("error" not in result[arm] for arm in ARMS):
        a, b = (result[arm] for arm in ARMS)
        check(a["pid"] != b["pid"], "Reader processes were not distinct")
        for name in ("generation_config", "system_instruction_sha256", "ranked_ids"):
            check(a[name] == b[name], f"Readers differ on {name}")
        for kind in ("answer", "critic"):
            check(
                a["receipts"][kind]["generation_config"]
                == b["receipts"][kind]["generation_config"],
                f"Readers differ on {kind} settings",
            )
        ids = [
            r["response_id"]
            for arm in ARMS
            for r in result[arm]["receipts"].values()
            if r["response_id"]
        ]
        check(len(set(ids)) == len(ids), "Repeated provider receipt ID")
    return result


def run(source, output, cohort, live):
    cases = ["trial-3"] if cohort == "trial3" else list(EXPECTED)[1:]
    limit = 4 * len(cases)
    key = ""
    if live:
        check(
            os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("GITHUB_REF") == BRANCH
            and os.getenv("GITHUB_RUN_ATTEMPT") == "1"
            and os.getenv("GITHUB_SHA") == sha()
            and os.getenv("GITHUB_RUN_ID")
            and os.getenv("DRIFT_AB_APPROVED_LIMIT") == str(limit),
            "Live test requires the first Actions attempt and the explicitly approved budget",
        )
        key = os.getenv("GEMINI_API_KEY", "").strip()
        check(
            re.fullmatch(
                r"(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_.=-]{20,4096})", key
            ),
            "Actions Gemini secret is missing or malformed",
        )
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / "attempts.sqlite"
    initialize(ledger)
    summary = {
        "commit": sha(),
        "model": MODEL,
        "live": live,
        "attempt_limit": limit if live else 0,
        "source_run": SOURCE_RUN,
        "source_commit": SOURCE_COMMIT,
        "cases": {},
    }
    try:
        for case in cases:
            report = summary["cases"][case] = {}
            evidence = output / case
            evidence.mkdir()
            with tempfile.TemporaryDirectory(prefix="drift-packing-source-") as folder:
                staging = Path(folder)
                if case == "trial-3":
                    fact, original = original_case(source)
                else:
                    subprocess.run(
                        [
                            sys.executable,
                            __file__,
                            "_seed",
                            case,
                            str(staging / "seed"),
                        ],
                        cwd=staging,
                        env=child_env(staging, ""),
                        check=True,
                    )
                    fact = read(staging / "seed" / "fact.json")
                    original = staging / "seed" / "store"
                if live:
                    offline = evidence / "preflight"
                    offline.mkdir()
                    planned = run_case(case, fact, original, offline, "", limit, ledger)
                    check(
                        tuple(planned[arm]["fact_in_assembled_prompt"] for arm in ARMS)
                        == EXPECTED[case],
                        f"Frozen case failed preflight for {case}",
                    )
                report.update(
                    run_case(case, fact, original, evidence, key, limit, ledger)
                )
            if any("error" in report[arm] for arm in ARMS):
                continue
            metric = "fact_in_gemini_prompt" if live else "fact_in_assembled_prompt"
            actual = tuple(report[arm][metric] for arm in ARMS)
            report["matches_expected_delivery"] = actual == EXPECTED[case]
            if case == "trial-3" and live:
                a, b = (report[arm] for arm in ARMS)
                report["clean_trial3_result"] = (
                    not a[metric]
                    and a["exact_code_in_gemini_reply"] is False
                    and b[metric]
                    and b["exact_code_in_gemini_reply"] is True
                )
            if not live:
                check(
                    report["matches_expected_delivery"],
                    f"Unexpected offline delivery for {case}",
                )
        if live:
            check(
                all(
                    report[arm].get("exact_code_in_gemini_reply") is not None
                    and report[arm]["receipts"]["critic"]["status"] == 200
                    for report in summary["cases"].values()
                    for arm in ARMS
                ),
                "One or more readers failed to produce a complete live result",
            )
    except Exception as exc:
        summary["error"] = str(exc)
        raise
    finally:
        summary["attempted_calls"] = raw_sql(ledger, "SELECT count(*) FROM attempts")[
            0
        ][0]
        write_json(output / "summary.json", summary)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "_seed":
        seed_fresh(sys.argv[2], Path(sys.argv[3]))
    elif sys.argv[1] == "_preflight":
        preflight(sys.argv[2], Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("source", type=Path)
        parser.add_argument("output", type=Path)
        parser.add_argument("--cohort", choices=("trial3", "fresh"), default="trial3")
        parser.add_argument("--live", action="store_true")
        args = parser.parse_args()
        run(args.source.resolve(), args.output.resolve(), args.cohort, args.live)

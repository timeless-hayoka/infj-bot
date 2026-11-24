"""Verify raw evidence without importing DRIFT or making provider requests."""

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from provider import (
    MAX_BODY_BYTES,
    MAX_CALLS,
    MAX_MICRODOLLARS,
    MAX_OUTPUT_TOKENS,
    MODEL,
    RESERVATION,
    sha256,
    write_json,
)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def raw_sql(path, query, parameters=()):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        check(conn.execute("PRAGMA quick_check").fetchone() == ("ok",), f"Corrupt {path.name}")
        return conn.execute(query, parameters).fetchall()


def verify_store(store, user_input, assistant):
    import chromadb

    expected = f"user: {user_input}\nBot: {assistant}"
    rows = raw_sql(
        store / "unified_memory.db",
        "SELECT unified_id FROM episodic WHERE event_type = 'interaction' AND content = ?",
        (expected,),
    )
    check(len(rows) == 1, "SQLite lacks the exact writer interaction or contains duplicates")
    memory_id = rows[0][0]
    # Verify against a copy because the Chroma API may open its DB for writes.
    with tempfile.TemporaryDirectory() as folder:
        snapshot = Path(folder) / "chroma"
        shutil.copytree(store, snapshot)
        check((snapshot / "chroma.sqlite3").is_file(), "Chroma database is absent")
        client = chromadb.PersistentClient(path=str(snapshot))
        collection = client.get_collection("infj_unified_memory_v2", embedding_function=None)
        fact = collection.get(ids=[memory_id], include=["documents", "embeddings", "metadatas"])
        check(fact["ids"] == [memory_id], "Missing corresponding Chroma record ID")
        check(fact["documents"] == [expected], "Chroma document differs from SQLite")
        check(fact["metadatas"][0]["unified_id"] == memory_id, "Chroma metadata ID mismatch")
        check(fact["embeddings"] is not None and len(fact["embeddings"][0]) > 0,
              "Chroma document has no persisted embedding")
    return {"memory_id": memory_id, "embedding_dimensions": len(fact["embeddings"][0])}


def request_text(payload):
    return "\n".join(
        part["text"] for item in payload["contents"] for part in item["parts"]
    )


def verify_turn(folder, attempts, process, prompt):
    runtime = read(folder / "runtime.json")
    check(runtime["pid"] == process["pid"], "Runtime PID does not match supervisor")
    check(runtime["sdk"] == "google.genai" and runtime["model"] == MODEL, "Wrong provider")
    check(runtime["embedding"] == "LocalEmbeddingFunction", "Wrong embedding backend")
    check(not (folder / "provider-block.json").exists(), "Provider guard blocked a request")
    check(
        process["exit_code"] == 0 and process["signal"] is None
        and not process["alive_after_wait"] and "driver_error" not in process,
        "Process did not exit normally",
    )
    check("Goodbye" in (folder / "console.txt").read_text(encoding="utf-8"),
          "CLI graceful shutdown message absent")
    trace = lines(folder / "memory.jsonl")
    check(any(e["event"] == "cli_returned" and e["pid"] == process["pid"] for e in trace),
          "CLI return was not observed")
    history = lines(folder / "history.jsonl")
    check(len(history) == 1 and history[0]["user"] == prompt, "Unexpected conversation history")
    response = history[0]["bot"]
    receipts = []
    primary_requests = []
    for attempt, pid, started_ns, reservation in attempts:
        req = (folder / f"request-{attempt}.json").read_bytes()
        raw = (folder / f"response-{attempt}.json").read_bytes()
        receipt = read(folder / f"receipt-{attempt}.json")
        payload = json.loads(req)
        provider = json.loads(raw)
        check(pid == receipt["pid"] == process["pid"], "Provider PID mismatch")
        check(process["started_ns"] <= started_ns <= process["ended_ns"], "Attempt outside turn")
        check(receipt["status"] == 200, "Gemini response was not successful")
        check(reservation == RESERVATION, "Incorrect reservation")
        check(sha256(req) == receipt["request_sha256"] and sha256(raw) == receipt["response_sha256"],
              "Request or response digest mismatch")
        check(len(req) <= MAX_BODY_BYTES and len(req) == receipt["request_bytes"],
              "Request size exceeds bound")
        check(0 < payload["generationConfig"]["maxOutputTokens"] <= MAX_OUTPUT_TOKENS,
              "Missing output cap")
        check(payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "MINIMAL"},
              "Unexpected thinking budget")
        check(not payload.get("tools"), "Unexpected provider-side grounding")
        check(provider["modelVersion"] == MODEL, "Provider returned an unexpected model")
        usage = provider["usageMetadata"]
        input_tokens = usage["promptTokenCount"]
        output_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        check(input_tokens <= MAX_BODY_BYTES and output_tokens <= MAX_OUTPUT_TOKENS,
              "Provider-reported usage exceeds the reserved envelope")
        candidates = provider.get("candidates", [])
        check(len(candidates) == 1, "Expected one Gemini candidate")
        candidate = candidates[0]
        text = "".join(
            part.get("text", "") for part in candidate["content"]["parts"]
            if not part.get("thought")
        )
        check(bool(text.strip()) and candidate["finishReason"] == "STOP", "Incomplete response")
        if prompt in request_text(payload) and response.strip() == text.strip():
            primary_requests.append(payload)
        receipts.append({
            "response_id": provider["responseId"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "grounded": bool(candidate.get("groundingMetadata", {}).get("webSearchQueries")),
        })
    check(bool(receipts) and len(primary_requests) == 1, "CLI response lacks one exact live match")
    return runtime, response, primary_requests[0], trace, receipts


def verify_trial(folder, attempts):
    fact = read(folder / "fact.json")
    writer = read(folder / "writer" / "process.json")
    reader = read(folder / "reader" / "process.json")
    restart = read(folder / "restart.json")
    code, specimen = fact["code"], fact["specimen"]
    check(writer["pid"] != reader["pid"], "PID reused")
    check(writer["ended_ns"] <= restart["time_ns"] <= reader["started_ns"], "Restart order invalid")
    check(not restart["history_present_before_reader"], "Writer's transcript remained accessible")
    check(code in writer["prompt"] and code not in reader["prompt"]
          and specimen in writer["prompt"] and specimen in reader["prompt"], "Fact leakage or mismatch")
    w, answer, _, writer_trace, sent = verify_turn(
        folder / "writer", attempts.get("writer", []), writer, writer["prompt"]
    )
    evidence = verify_store(folder / "writer-store", writer["prompt"], answer)
    r, recalled, request, reader_trace, received = verify_turn(
        folder / "reader", attempts.get("reader", []), reader, reader["prompt"]
    )
    check(w["sqlite"] == r["sqlite"] and w["chroma"] == r["chroma"] == restart["storage"],
          "Writer and reader used different spine stores")
    check(restart["storage_inode_before_reader"] is not None, "No persisted spine at restart")
    check(re.fullmatch(re.escape(code) + r"[.!]?", recalled.strip(), re.I), "Incorrect recall")
    memory_id = evidence["memory_id"]
    check(any(e["event"] == "recall_returned" and e["query"] == reader["prompt"]
              and memory_id in e["ids"] for e in reader_trace), "Reader did not retrieve writer ID")
    context = request_text(request)
    check("Memory context below" in context and f"user: {writer['prompt']}" in context,
          "Writer interaction absent from the Gemini recall prompt")
    completed = [e["time_ns"] for e in writer_trace
                 if e["event"] == "write_returned" and e["id"] == memory_id]
    check(len(completed) == 1 and completed[0] <= writer["ended_ns"], "No completed write observed")
    evidence.update(
        writer_pid=writer["pid"], reader_pid=reader["pid"], recalled=recalled,
        code=code, writer_receipts=sent, reader_receipts=received,
        write_completed_before_exit_sent=completed[0] <= writer["exit_sent_ns"],
    )
    return evidence


def verify(root, commit, run_id, output):
    result = {"commit": commit, "run_id": run_id, "status": "failed", "trials": []}
    try:
        manifest = read(root / "pilot.json")
        check(manifest == {"commit": commit, "run_id": run_id, "trials": 5}, "Manifest mismatch")
        rows = raw_sql(root / "budget.sqlite", "SELECT id, turn, pid, started_ns, reservation FROM attempts")
        reserved = sum(row[-1] for row in rows)
        result.update(attempted_calls=len(rows), reserved_microdollars=reserved)
        check(len(rows) <= MAX_CALLS and reserved <= MAX_MICRODOLLARS, "Budget exceeded")
        attempts = {}
        for attempt, turn, pid, start, reservation in rows:
            trial, _, role = turn.partition("/")
            check(trial in "12345" and len(trial) == 1 and role in ("writer", "reader"),
                  "Unrecognized provider attempt")
            attempts.setdefault(trial, {}).setdefault(role, []).append(
                (attempt, pid, start, reservation)
            )
        codes = set()
        specimens = set()
        response_ids = set()
        for number in range(1, 6):
            trial = {"trial": number}
            result["trials"].append(trial)
            try:
                folder = root / str(number)
                fact = read(folder / "fact.json")
                check(fact["code"] not in codes and fact["specimen"] not in specimens,
                      "Repeated fact or specimen")
                codes.add(fact["code"])
                specimens.add(fact["specimen"])
                trial.update(verify_trial(folder, attempts.get(str(number), {})))
                for receipt in trial["writer_receipts"] + trial["reader_receipts"]:
                    response_id = receipt["response_id"]
                    check(response_id and response_id not in response_ids, "Non-unique response ID")
                    response_ids.add(response_id)
                trial["passed"] = True
            except Exception as exc:
                trial.update(passed=False, failure=str(exc))
        result["passed"] = sum(trial["passed"] for trial in result["trials"])
        check(result["passed"] == 5, "Five trials did not pass")
        check(len(rows) == len(response_ids), "Unaccounted provider attempts")
        result["status"] = "passed"
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        result["failure"] = str(exc)
    finally:
        write_json(output, result)
        print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(verify(args.root, args.commit, args.run_id, args.output))

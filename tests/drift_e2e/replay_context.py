"""Compare prompt packing on real DRIFT-E2E-01 writer snapshots, without a model."""

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from provider import write_json
from verify import lines, read, request_text

FAST_CONTEXT_LIMIT = 1500
RECORD_EXCERPT_LIMIT = 600
SEPARATOR = "\n---\n"
REPO = Path(__file__).resolve().parents[2]


def pack_whole_records(records, limit=FAST_CONTEXT_LIMIT):
    """Fit complete records in ranked order, skipping entries that do not fit."""
    chosen = []
    remaining = limit
    for record in records:
        cost = len(record) + (len(SEPARATOR) if chosen else 0)
        if cost <= remaining:
            chosen.append(record)
            remaining -= cost
    return SEPARATOR.join(chosen)


def pack_record_excerpts(records):
    suffix = "\n[record excerpt]"
    return pack_whole_records(
        record[:RECORD_EXCERPT_LIMIT - len(suffix)] + suffix
        if len(record) > RECORD_EXCERPT_LIMIT else record
        for record in records
    )


def boundary_cases():
    marker = "FROZEN-EVIDENCE-42"
    long = "Memory: " + "distractor " * 300
    short = f"Memory: {marker}"
    fixtures = {
        "short_fact_after_long_distractor": ([long, short], [False, True, True]),
        "fact_near_start_of_long_record": ([short + " " + long], [True, False, True]),
        "fact_near_end_of_long_record": ([long + short], [False, False, False]),
        "fact_after_excerpt_within_global_budget": ([long[:900] + short],
                                                    [True, True, False]),
        "fact_absent": ([long, "Memory: unrelated"], [False, False, False]),
    }
    results = {}
    for name, (records, expected) in fixtures.items():
        results[name] = {
            "legacy": marker in SEPARATOR.join(records)[:FAST_CONTEXT_LIMIT],
            "whole_records": marker in pack_whole_records(records),
            "record_excerpts": marker in pack_record_excerpts(records),
        }
        if list(results[name].values()) != expected:
            raise RuntimeError(f"Unexpected result for boundary case {name}")
    return results


def original_request(trial, expected, prompt):
    for path in sorted((trial / "reader").glob("request-*.json")):
        text = request_text(read(path))
        if prompt in text and "Memory context below" in text:
            section = text.partition("Memory context below")[2].rpartition(prompt)[0]
            return {"recorded": True, "fact_in_memory_context": expected in section}
    return {"recorded": False, "fact_in_memory_context": None}


def replay_trial(trial, store):
    from drift.core.causal_wiring import retrieved_memory_keys_var
    from drift.core.cognitive_orchestrator import CognitiveOrchestrator
    from drift.core.commands import BotState
    from drift.core.memory import DriftMemory

    fact = read(trial / "fact.json")["code"]
    reader = read(trial / "reader" / "process.json")["prompt"]
    writer = lines(trial / "writer" / "history.jsonl")[0]
    expected = f"user: {writer['user']}\nBot: {writer['bot']}"
    with closing(sqlite3.connect(store / "unified_memory.db")) as conn:
        target_id, = conn.execute(
            "SELECT unified_id FROM episodic WHERE event_type = 'interaction' AND content = ?",
            (expected,),
        ).fetchone()

    class ReplayMemory(DriftMemory):
        pack = None

        def retrieve_context_ranked(self, query, n_results=5):
            context = super().retrieve_context_ranked(query, n_results=n_results)
            self.ranked_ids = retrieved_memory_keys_var.get()
            contents = self.unified_manager.get_contents_by_id(self.ranked_ids)
            self.records = [f"Memory: {contents[key]}" for key in self.ranked_ids]
            if SEPARATOR.join(self.records) != context:
                raise RuntimeError("Replay requires canonical ranked records")
            return self.pack(self.records) if self.pack is not None else context

    memory = ReplayMemory(persist_directory=str(store))
    if not memory.unified_manager.collection.get(ids=[target_id])["ids"]:
        raise RuntimeError("Writer record absent from Chroma")
    assembler = CognitiveOrchestrator()
    baseline_prompt, _, _ = assembler.assemble_prompt(reader, BotState(), memory)
    ranked_ids = list(memory.ranked_ids)
    ranked_chars = [len(record) for record in memory.records]
    original_slice = SEPARATOR.join(memory.records)[:FAST_CONTEXT_LIMIT]
    prompts = {}
    for pack in (pack_whole_records, pack_record_excerpts):
        memory.pack = pack
        prompts[pack] = assembler.assemble_prompt(reader, BotState(), memory)[0]
        if list(memory.ranked_ids) != ranked_ids:
            raise RuntimeError("Ranking changed between replay arms")

    def included(prompt):
        section = prompt.partition("Memory context below")[2].rpartition(reader)[0]
        return fact in section

    return {
        "trial": int(trial.name),
        "source": original_request(trial, fact, reader),
        "target_id": target_id,
        "ranked_ids": ranked_ids,
        "ranked_record_characters": ranked_chars,
        "fact_in_legacy_slice": fact in original_slice,
        "fact_in_legacy_prompt": included(baseline_prompt),
        "fact_in_whole_record_prompt": included(prompts[pack_whole_records]),
        "fact_in_excerpt_prompt": included(prompts[pack_record_excerpts]),
        "whole_record_characters": len(pack_whole_records(memory.records)),
    }


def run(root):
    reports = []
    for trial in sorted(path for path in root.iterdir() if path.is_dir()):
        with tempfile.TemporaryDirectory(prefix="drift-context-replay-") as folder:
            isolated = Path(folder)
            store = isolated / "store"
            shutil.copytree(trial / "writer-store", store)
            child_report = isolated / "report.json"
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(trial), str(child_report),
                 "--snapshot", str(store)],
                check=True,
                cwd=isolated,
                env={
                    "PATH": os.environ["PATH"], "HOME": str(isolated),
                    "PYTHONPATH": str(REPO), "DRIFT_OS_ROOT": str(isolated / "drift"),
                    "DRIFT_FAST_MODE": "true", "DRIFT_USE_LOCAL_EMBEDDINGS": "true",
                    "ANONYMIZED_TELEMETRY": "false", "HF_HUB_OFFLINE": "1",
                },
            )
            reports.append(read(child_report))
    if [report["trial"] for report in reports] != list(range(1, 6)):
        raise RuntimeError("Expected all five original trial snapshots")
    return {
        "baseline_commit": read(root / "pilot.json")["commit"],
        "provider_calls": 0,
        "fast_context_limit_characters": FAST_CONTEXT_LIMIT,
        "excerpt_limit_characters": RECORD_EXCERPT_LIMIT,
        "trials": reports,
        "synthetic_boundary_cases": boundary_cases(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path, help="Extracted Actions raw evidence")
    parser.add_argument("report", type=Path)
    parser.add_argument("--snapshot", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    result = (
        replay_trial(args.evidence, args.snapshot) if args.snapshot else run(args.evidence.resolve())
    )
    write_json(args.report, result)


if __name__ == "__main__":
    main()

import argparse
import concurrent.futures
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from memory import InfjMemory, LocalEmbeddingFunction


PROMPTS = [
    "I feel pulled between discipline and imagination.",
    "How should I think about building a private AI companion?",
    "Challenge my assumptions about productivity.",
    "What makes a memory useful instead of just stored?",
    "Help me reason through a hard engineering tradeoff.",
    "What pattern am I missing in my own behavior?",
]


@dataclass
class Timing:
    operation: str
    seconds: float
    ok: bool
    error: str = ""


class FakeBrain:
    def think(self, user_input: str) -> str:
        digest = abs(hash(user_input)) % 100_000
        return (
            "I hear the pattern beneath the surface: "
            f"{user_input[:80]} [reflection:{digest}]"
        )


def percentile(values, pct):
    if not values:
        return 0.0
    index = min(len(values) - 1, round((pct / 100) * (len(values) - 1)))
    return sorted(values)[index]


def time_call(operation, func, *args):
    start = time.perf_counter()
    try:
        func(*args)
        return Timing(operation, time.perf_counter() - start, True)
    except Exception as exc:
        return Timing(operation, time.perf_counter() - start, False, repr(exc))


def timed_result(operation, func, *args):
    start = time.perf_counter()
    try:
        return func(*args), Timing(operation, time.perf_counter() - start, True)
    except Exception as exc:
        return None, Timing(operation, time.perf_counter() - start, False, repr(exc))


def run_interaction(memory, brain, index):
    prompt = f"{PROMPTS[index % len(PROMPTS)]} Case #{index}"

    context, context_timing = timed_result("retrieve", memory.retrieve_context, prompt)
    if not context_timing.ok:
        return [context_timing]

    output, think_timing = timed_result(
        "think",
        brain.think,
        f"Previous context:\n{context}\n\nUser: {prompt}",
    )
    if not think_timing.ok:
        return [context_timing, think_timing]

    save_timing = time_call("save", memory.save_interaction, prompt, output)
    return [context_timing, think_timing, save_timing]


def summarize(timings, total_seconds):
    by_operation = {}
    for timing in timings:
        by_operation.setdefault(timing.operation, []).append(timing)

    print("\nINFJ bot stress test")
    print(f"Total runtime: {total_seconds:.2f}s")
    print(f"Operations: {len(timings)}")
    print(f"Failures: {sum(not timing.ok for timing in timings)}")

    for operation, items in sorted(by_operation.items()):
        seconds = [item.seconds for item in items]
        failures = [item for item in items if not item.ok]
        print(
            f"{operation:>8}: count={len(items):4d} "
            f"avg={statistics.mean(seconds):.4f}s "
            f"p95={percentile(seconds, 95):.4f}s "
            f"max={max(seconds):.4f}s "
            f"failures={len(failures)}"
        )
        for failure in failures[:3]:
            print(f"          error: {failure.error}")


def main():
    parser = argparse.ArgumentParser(description="Stress test the INFJ bot pipeline.")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--persist-directory",
        type=Path,
        default=None,
        help="Chroma persistence directory. Defaults to a temporary directory.",
    )
    args = parser.parse_args()

    temp_dir = None
    persist_directory = args.persist_directory
    if persist_directory is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="infj-bot-stress-"))
        persist_directory = temp_dir

    memory = InfjMemory(
        persist_directory=str(persist_directory),
        embedding_function=LocalEmbeddingFunction(),
    )
    brain = FakeBrain()
    for index, prompt in enumerate(PROMPTS):
        memory.save_interaction(f"Seed #{index}: {prompt}", brain.think(prompt))

    start = time.perf_counter()
    timings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(run_interaction, memory, brain, index)
            for index in range(args.requests)
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                timings.extend(future.result())
            except Exception as exc:
                timings.append(Timing("worker", 0.0, False, repr(exc)))

    total_seconds = time.perf_counter() - start
    summarize(timings, total_seconds)

    if temp_dir is not None:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if any(not timing.ok for timing in timings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

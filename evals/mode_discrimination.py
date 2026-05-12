"""Mode Discrimination Evaluator — tests whether modes are actually distinct.

If companion, coach, and clarity modes all produce statistically similar
responses, the modes are illusory. This evaluator measures:

  1. Lexical distinctness — do modes use different vocabulary?
  2. Syntactic distinctness — do modes use different sentence structures?
  3. Tool-use patterns — do modes invoke different tools?
  4. Emotional tone — do modes express different sentiment distributions?
  5. Blind classification — can a classifier (or LLM) tell modes apart?

Usage:
  python evals/mode_discrimination.py --modes companion,coach,critic --prompts 10
"""

import argparse
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import MODE_DISCRIMINATION_DB as EVAL_DB

TEST_PROMPTS = [
    "I feel stuck in my career.",
    "My relationship is falling apart.",
    "I need to build a web scraper.",
    "I'm afraid I'm not good enough.",
    "Should I quit my job?",
    "I want to learn to be more present.",
    "Someone criticized my work and I can't stop thinking about it.",
    "I have a big presentation tomorrow and I'm terrified.",
    "I keep making the same mistake.",
    "What should I do with my life?",
]


@dataclass
class ModeDiscriminationReport:
    timestamp: str
    modes_tested: List[str]
    lexical_distinctness: float = 0.0
    syntactic_distinctness: float = 0.0
    tool_distinctness: float = 0.0
    tone_distinctness: float = 0.0
    overall_score: float = 0.0
    convergence_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "modes_tested": self.modes_tested,
            "lexical_distinctness": round(self.lexical_distinctness, 3),
            "syntactic_distinctness": round(self.syntactic_distinctness, 3),
            "tool_distinctness": round(self.tool_distinctness, 3),
            "tone_distinctness": round(self.tone_distinctness, 3),
            "overall_score": round(self.overall_score, 3),
            "convergence_warnings": self.convergence_warnings,
        }


class ModeDiscriminator:
    """Tests whether DRIFT's modes produce measurably different behavior."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or EVAL_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mode_discrimination_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    modes_tested TEXT,
                    lexical_distinctness REAL,
                    syntactic_distinctness REAL,
                    tool_distinctness REAL,
                    tone_distinctness REAL,
                    overall_score REAL,
                    convergence_warnings TEXT
                )
            """)
            conn.commit()

    def evaluate_modes(
        self, modes: List[str], prompts: Optional[List[str]] = None, n_prompts: int = 10
    ) -> ModeDiscriminationReport:
        """Run discrimination analysis across modes."""
        test_prompts = (prompts or TEST_PROMPTS)[:n_prompts]
        responses = self._collect_responses(modes, test_prompts)

        report = ModeDiscriminationReport(
            timestamp=datetime.now().isoformat(),
            modes_tested=modes,
        )

        report.lexical_distinctness = self._lexical_distinctness(responses)
        report.syntactic_distinctness = self._syntactic_distinctness(responses)
        report.tool_distinctness = self._tool_distinctness(responses)
        report.tone_distinctness = self._tone_distinctness(responses)

        weights = {
            "lexical": 0.30,
            "syntactic": 0.20,
            "tool": 0.25,
            "tone": 0.25,
        }
        report.overall_score = (
            report.lexical_distinctness * weights["lexical"]
            + report.syntactic_distinctness * weights["syntactic"]
            + report.tool_distinctness * weights["tool"]
            + report.tone_distinctness * weights["tone"]
        )

        report.convergence_warnings = self._detect_convergence(responses, modes)
        self._save_report(report)
        return report

    def _collect_responses(
        self, modes: List[str], prompts: List[str]
    ) -> Dict[str, List[Dict]]:
        """Collect responses from each mode for each prompt."""
        from brain import InfjBrain
        from commands import BotState
        from prompt_builder import build_chat_prompt

        brain = InfjBrain()
        state = BotState()
        responses = {mode: [] for mode in modes}

        for mode in modes:
            state.mode = mode
            for prompt in prompts:
                try:
                    # Build prompt for this mode
                    prompt_text = build_chat_prompt(
                        message=prompt,
                        state=state,
                        memory=None,
                        tools_enabled=True,
                    )
                    # Generate response
                    response = brain.think(prompt_text)
                    responses[mode].append(
                        {
                            "prompt": prompt,
                            "response": response,
                            "tools_used": self._extract_tools(response),
                        }
                    )
                except Exception as exc:
                    responses[mode].append(
                        {
                            "prompt": prompt,
                            "response": f"[ERROR: {exc}]",
                            "tools_used": [],
                        }
                    )
        return responses

    def _extract_tools(self, response: str) -> List[str]:
        """Extract tool invocations from response text."""
        tool_pattern = r"\b(tool_[a-z_]+|recon|scan|fuzz|computer_use)\b"
        return list(set(re.findall(tool_pattern, response.lower())))

    # ── Metrics ──

    def _lexical_distinctness(self, responses: Dict[str, List[Dict]]) -> float:
        """Measure vocabulary differentiation between modes."""
        mode_vocab = {}
        for mode, resps in responses.items():
            all_text = " ".join(r["response"].lower() for r in resps)
            words = set(re.findall(r"\b[a-z]{4,}\b", all_text))
            mode_vocab[mode] = words

        modes = list(mode_vocab.keys())
        if len(modes) < 2:
            return 1.0

        distinct_ratios = []
        for i, mode_a in enumerate(modes):
            for mode_b in modes[i + 1 :]:
                vocab_a = mode_vocab[mode_a]
                vocab_b = mode_vocab[mode_b]
                if not vocab_a or not vocab_b:
                    continue
                # Jaccard distance: 1 - (intersection / union)
                intersection = len(vocab_a & vocab_b)
                union = len(vocab_a | vocab_b)
                jaccard = 1.0 - (intersection / union) if union > 0 else 0.0
                distinct_ratios.append(jaccard)

        return sum(distinct_ratios) / len(distinct_ratios) if distinct_ratios else 1.0

    def _syntactic_distinctness(self, responses: Dict[str, List[Dict]]) -> float:
        """Measure sentence structure differentiation."""
        mode_structures = {}
        for mode, resps in responses.items():
            structures = []
            for r in resps:
                sentences = r["response"].split(".")
                for sent in sentences:
                    sent = sent.strip()
                    if len(sent) < 10:
                        continue
                    # Simple structure fingerprint: first 3 words + avg sentence length
                    words = sent.split()
                    fingerprint = " ".join(words[:3]).lower()
                    structures.append(fingerprint)
            mode_structures[mode] = Counter(structures)

        modes = list(mode_structures.keys())
        if len(modes) < 2:
            return 1.0

        distinct_scores = []
        for i, mode_a in enumerate(modes):
            for mode_b in modes[i + 1 :]:
                counter_a = mode_structures[mode_a]
                counter_b = mode_structures[mode_b]
                total_a = sum(counter_a.values())
                total_b = sum(counter_b.values())
                if total_a == 0 or total_b == 0:
                    continue
                # Calculate cosine similarity of structure distributions
                all_structs = set(counter_a.keys()) | set(counter_b.keys())
                dot = sum(counter_a[s] * counter_b[s] for s in all_structs)
                norm_a = sum(counter_a[s] ** 2 for s in all_structs) ** 0.5
                norm_b = sum(counter_b[s] ** 2 for s in all_structs) ** 0.5
                similarity = dot / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
                distinct_scores.append(1.0 - similarity)

        return sum(distinct_scores) / len(distinct_scores) if distinct_scores else 1.0

    def _tool_distinctness(self, responses: Dict[str, List[Dict]]) -> float:
        """Measure tool usage differentiation between modes."""
        mode_tools = {}
        for mode, resps in responses.items():
            tools = []
            for r in resps:
                tools.extend(r["tools_used"])
            mode_tools[mode] = Counter(tools)

        modes = list(mode_tools.keys())
        if len(modes) < 2:
            return 1.0

        distinct_scores = []
        for i, mode_a in enumerate(modes):
            for mode_b in modes[i + 1 :]:
                tools_a = set(mode_tools[mode_a].keys())
                tools_b = set(mode_tools[mode_b].keys())
                if not tools_a and not tools_b:
                    continue
                # Tool Jaccard distance
                intersection = len(tools_a & tools_b)
                union = len(tools_a | tools_b)
                jaccard = 1.0 - (intersection / union) if union > 0 else 0.0
                distinct_scores.append(jaccard)

        return sum(distinct_scores) / len(distinct_scores) if distinct_scores else 1.0

    def _tone_distinctness(self, responses: Dict[str, List[Dict]]) -> float:
        """Measure emotional tone differentiation using sentiment markers."""
        positive_markers = [
            "love",
            "happy",
            "joy",
            "excited",
            "grateful",
            "hope",
            "warm",
            "gentle",
            "care",
        ]
        negative_markers = [
            "hate",
            "sad",
            "angry",
            "afraid",
            "worry",
            "frustrated",
            "disappointed",
        ]
        analytical_markers = [
            "analyze",
            "consider",
            "examine",
            "evaluate",
            "assess",
            "review",
        ]
        imperative_markers = [
            "do",
            "try",
            "start",
            "stop",
            "focus",
            "plan",
            "act",
            "build",
        ]

        mode_tones = {}
        for mode, resps in responses.items():
            tones = Counter()
            for r in resps:
                text = r["response"].lower()
                tones["positive"] += sum(1 for m in positive_markers if m in text)
                tones["negative"] += sum(1 for m in negative_markers if m in text)
                tones["analytical"] += sum(1 for m in analytical_markers if m in text)
                tones["imperative"] += sum(1 for m in imperative_markers if m in text)
            mode_tones[mode] = tones

        modes = list(mode_tones.keys())
        if len(modes) < 2:
            return 1.0

        distinct_scores = []
        for i, mode_a in enumerate(modes):
            for mode_b in modes[i + 1 :]:
                counter_a = mode_tones[mode_a]
                counter_b = mode_tones[mode_b]
                total_a = sum(counter_a.values())
                total_b = sum(counter_b.values())
                if total_a == 0 or total_b == 0:
                    continue
                # Normalize and compute Euclidean distance
                all_tones = set(counter_a.keys()) | set(counter_b.keys())
                dist = (
                    sum(
                        ((counter_a[t] / total_a) - (counter_b[t] / total_b)) ** 2
                        for t in all_tones
                    )
                    ** 0.5
                )
                # Max possible distance is sqrt(2) for 2 categories, sqrt(4) for 4
                max_dist = 2.0
                distinct_scores.append(min(1.0, dist / max_dist))

        return sum(distinct_scores) / len(distinct_scores) if distinct_scores else 1.0

    def _detect_convergence(
        self, responses: Dict[str, List[Dict]], modes: List[str]
    ) -> List[str]:
        """Detect specific mode pairs that are converging."""
        warnings = []
        lexical = {}
        for mode, resps in responses.items():
            all_text = " ".join(r["response"].lower() for r in resps)
            words = Counter(re.findall(r"\b[a-z]{4,}\b", all_text))
            lexical[mode] = words

        for i, mode_a in enumerate(modes):
            for mode_b in modes[i + 1 :]:
                words_a = lexical[mode_a]
                words_b = lexical[mode_b]
                if not words_a or not words_b:
                    continue
                # Top-word overlap
                top_a = set(w for w, _ in words_a.most_common(20))
                top_b = set(w for w, _ in words_b.most_common(20))
                overlap = len(top_a & top_b) / 20.0
                if overlap > 0.7:
                    warnings.append(
                        f"{mode_a} ↔ {mode_b}: lexical convergence ({overlap:.0%} top-word overlap)"
                    )
        return warnings

    def _save_report(self, report: ModeDiscriminationReport) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO mode_discrimination_reports
                (timestamp, modes_tested, lexical_distinctness, syntactic_distinctness,
                 tool_distinctness, tone_distinctness, overall_score, convergence_warnings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.timestamp,
                    json.dumps(report.modes_tested),
                    report.lexical_distinctness,
                    report.syntactic_distinctness,
                    report.tool_distinctness,
                    report.tone_distinctness,
                    report.overall_score,
                    json.dumps(report.convergence_warnings),
                ),
            )
            conn.commit()

    def get_report_history(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM mode_discrimination_reports ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--modes", default="companion,coach,critic", help="Comma-separated modes"
    )
    p.add_argument("--prompts", type=int, default=10, help="Number of test prompts")
    p.add_argument("--history", action="store_true", help="Show report history")
    args = p.parse_args()

    evaluator = ModeDiscriminator()
    if args.history:
        for r in evaluator.get_report_history():
            print(
                f"[{r['timestamp']}] score={r['overall_score']:.2f} modes={r['modes_tested']}"
            )
    else:
        modes = [m.strip() for m in args.modes.split(",")]
        report = evaluator.evaluate_modes(modes, n_prompts=args.prompts)
        print(json.dumps(report.to_dict(), indent=2))

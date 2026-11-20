import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_continuity as local
import restart_continuity as harness
from drift.core.prompt_budget import PromptBudget

from core.memory_facts import format_memory_facts


class LocalContinuityTests(unittest.TestCase):
    def test_single_complete_json_fence_preserves_facts_but_fails_format(self):
        answer = "```json\n" + json.dumps(harness.EXPECTED) + "\n```"
        result = local.grade(answer, harness.EXPECTED)
        self.assertEqual(result["points"], 7)
        self.assertTrue(result["valid_json"])
        self.assertFalse(result["format_compliant"])
        self.assertEqual(harness.score(answer)["supersession"], [1, 1])

    def test_parser_never_repairs_partial_json_or_extracts_it_from_prose(self):
        for answer in (
            '```json\n{"day": "thursday"',
            "Here is my answer: " + json.dumps(harness.EXPECTED),
            json.dumps(harness.EXPECTED) + "\nextra text",
        ):
            self.assertFalse(local.grade(answer, harness.EXPECTED)["valid_json"])

    def test_semantically_equivalent_alder_labels_are_correct(self):
        answer = dict(
            harness.EXPECTED,
            preference="bullet points",
            format="CSV export",
            day="Thu",
            completed="collection",
            next="deduplication",
            reviewer="unknown",
        )
        result = local.grade(json.dumps(answer), harness.EXPECTED)
        self.assertEqual(result["points"], 7)
        self.assertFalse(result["unsupported_reviewer"])
        self.assertEqual(harness.score(json.dumps(answer))["continuation"], [2, 2])

    def test_label_equivalence_does_not_accept_wrong_actions_or_deadlines(self):
        answer = dict(
            harness.EXPECTED,
            day="Tue",
            completed="collection",
            next="export",
            reviewer="Alex",
        )
        result = local.grade(json.dumps(answer), harness.EXPECTED)
        self.assertEqual(result["points"], 4)
        self.assertEqual(result["contradictions"], 2)
        self.assertTrue(result["unsupported_reviewer"])

    def test_real_prompt_budget_keeps_oversized_memory_with_explicit_capacity(self):
        text = "remembered record " * 300
        default = PromptBudget(max_total_chars=12000, context_budget=2500)
        self.assertFalse(default.add("context", text, label="memory"))
        expanded = PromptBudget(max_total_chars=24000, context_budget=16000)
        self.assertTrue(expanded.add("context", text, label="memory"))
        self.assertIn(text.strip(), expanded.assemble())

    def test_prompt_budget_environment_is_opt_in(self):
        names = ("DRIFT_PROMPT_TOTAL_CHARS", "DRIFT_PROMPT_CONTEXT_CHARS")
        previous = {name: os.environ.get(name) for name in names}
        try:
            for name in names:
                os.environ.pop(name, None)
            default = PromptBudget()
            self.assertEqual(default.max_total_chars, 12000)
            self.assertEqual(default.tiers["context"].max_chars, 2500)
            os.environ.update(dict(zip(names, ("24000", "16000"))))
            expanded = PromptBudget()
            self.assertEqual(expanded.max_total_chars, 24000)
            self.assertEqual(expanded.tiers["context"].max_chars, 16000)
            explicit = PromptBudget(max_total_chars=12000, context_budget=2500)
            self.assertEqual(explicit.max_total_chars, 12000)
            self.assertEqual(explicit.tiers["context"].max_chars, 2500)
            os.environ[names[0]] = "0"
            with self.assertRaises(ValueError):
                PromptBudget()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_twenty_scenarios_cover_updates_and_unknowns(self):
        scenarios = list(local.scenarios(harness))
        self.assertEqual(len(scenarios), 20)
        self.assertEqual(len({s["name"] for s in scenarios}), 20)
        self.assertGreater(len({s["expected"]["next"] for s in scenarios}), 15)
        for scenario in scenarios:
            self.assertIsNone(scenario["expected"]["reviewer"])
            self.assertIn(
                scenario["expected"]["day"],
                dict(scenario["setup"])["update"].casefold(),
            )
            self.assertEqual(
                local.grade(json.dumps(scenario["expected"]), scenario["expected"])[
                    "points"
                ],
                7,
            )

    def test_wrong_old_day_next_and_reviewer_lose_points(self):
        answer = dict(harness.EXPECTED, day="tuesday", next="export", reviewer="Alex")
        graded = local.grade(json.dumps(answer), harness.EXPECTED)
        self.assertEqual(graded["points"], 4)
        self.assertEqual(graded["contradictions"], 2)
        self.assertTrue(graded["unsupported_reviewer"])

    def test_invalid_answers_are_counted_without_aborting_batch(self):
        for answer in ("not JSON", "[]", "null", "{}", "```json\n{}\n```"):
            graded = local.grade(answer, harness.EXPECTED)
            self.assertEqual(graded["points"], 0)
            self.assertFalse(graded["valid_json"])

    def test_legacy_score_still_works(self):
        score = harness.score(json.dumps(harness.EXPECTED))
        self.assertEqual(score["retained"], [2, 2])
        self.assertEqual(score["unsupported_claims"], [0, 1])

    def test_summary_uses_paired_differences(self):
        expected = harness.EXPECTED
        good = local.grade(json.dumps(expected), expected)
        bad = local.grade("{}", expected)
        pairs = [
            {"scenario": {"expected": expected}, "scores": {"on": a, "off": b}}
            for a, b in ((good, bad), (good, good), (bad, good))
        ]
        summary = local.summarize(pairs)
        self.assertEqual(summary["points"], {"on": 14, "off": 14})
        self.assertEqual(summary["paired_on_minus_off"], 0)
        self.assertEqual(
            (summary["improved"], summary["tied"], summary["regressed"]), (1, 1, 1)
        )

    def test_pair_verification_rejects_leaked_off_memory_and_changed_settings(self):
        scenario = next(local.scenarios(harness))
        labels = dict(scenario["setup"])
        old_day = "Tuesday"
        expected = scenario["expected"]
        evidence = (
            f"PROJECT: {scenario['name']}\n[PREFERENCE] {expected['preference']}\n"
            f"[WORKSPACE] {expected['workspace']}\n"
            f"[DECISION: EXPORT FORMAT] {expected['format']}\n"
            f"[TASK PROGRESSION] completed: Collection; next unfinished: Deduplication\n"
            f"[DECISION: SUPERSEDED DELIVERY DAY] {old_day}\n"
            f"[DECISION: CURRENT DELIVERY DAY] {expected['day']}"
        )
        results = {}
        for condition in ("on", "off"):
            on = condition == "on"
            results[condition] = {
                "memory_context": list(labels) if on else [],
                "stored_labels": {k: k for k in labels} if on else {},
                "retrieved_ids": list(labels) if on else [],
                "stores": {
                    "sqlite": 5 if on else 0,
                    "vectors": 5 if on else 0,
                    "archive": 5 if on else 0,
                    "snapshots": int(on),
                    "structured_interactions": int(on),
                    "generation_cache_entries": 0,
                },
                "focus_context": on,
                "heartbeat_context": on,
                "need_context": on,
                "history_at_start": 0,
                "core_prompt_available": True,
                "response": "answer",
                "live_calls": [
                    {
                        "response": "answer",
                        "system_sha256": "same",
                        "digest": "same",
                        "request": {
                            "options": dict(local.OPTIONS),
                            "messages": [
                                {
                                    "role": "user",
                                    "content": "<retrieved_memory_evidence>"
                                    + (
                                        evidence
                                        if on
                                        else "No project facts were retrieved."
                                    )
                                    + "</retrieved_memory_evidence>",
                                }
                            ],
                        },
                    }
                ],
            }
        for result in results.values():
            result["live_calls"].append(copy.deepcopy(result["live_calls"][0]))
        local.verify_pair(results, scenario)
        leaked = copy.deepcopy(results)
        leaked["off"]["memory_context"] = ["update"]
        with self.assertRaises(AssertionError):
            local.verify_pair(leaked, scenario)
        changed = copy.deepcopy(results)
        changed["on"]["live_calls"][0]["request"]["options"]["num_predict"] = 123
        with self.assertRaises(AssertionError):
            local.verify_pair(changed, scenario)

    def test_rescore_reads_raw_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            trial = Path(folder) / "01-Alder"
            trial.mkdir()
            local.write_json(trial / "scenario.json", {"expected": harness.EXPECTED})
            for condition in ("on", "off"):
                (trial / condition).mkdir()
                (trial / condition / "response.txt").write_text(
                    json.dumps(harness.EXPECTED) if condition == "on" else "{}"
                )
            summary = local.rescore(folder)
            self.assertEqual(summary["paired_on_minus_off"], 7)
            self.assertEqual(summary["improved"], 1)

    def test_rescore_comparison_reports_each_arm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for variant in local.VARIANTS:
                trial = root / variant / "01-Alder"
                trial.mkdir(parents=True)
                local.write_json(
                    trial / "scenario.json", {"expected": harness.EXPECTED}
                )
                for condition, answer in (("on", harness.EXPECTED), ("off", {})):
                    (trial / condition).mkdir()
                    (trial / condition / "response.txt").write_text(json.dumps(answer))
            result = local.rescore_comparison(root)
            self.assertEqual(set(result), set(local.VARIANTS))
            self.assertEqual(result["current"]["paired_on_minus_off"], 7)
            self.assertEqual(result["evidence-focused"]["paired_on_minus_off"], 7)
            self.assertEqual(result["evidence-critic"]["paired_on_minus_off"], 7)

    def test_memory_facts_are_project_scoped_and_mark_supersession_and_progress(self):
        context = "\n---\n".join(  # noqa: FLY002 - records are intentionally distinct
            (
                "Memory: user: For Project Alder I prefer bullet lists. My workspace is Birch Studio.\nBot: invented preference",
                "Memory: user: Project Alder will ship as a CSV export. The delivery day is Tuesday.\nBot: invented deadline",
                "user: For Project Alder, collect, deduplicate, then export. Collection is complete. Deduplication is the next unfinished step.\nBot: unrelated answer",
                "user: Project Alder delivery moved to Thursday. This supersedes Tuesday.\nBot: claim",
                "user: Project Willow uses a PDF export and ships on Friday.\nBot: claim",
            )
        )
        facts = format_memory_facts(context)
        self.assertIn("PROJECT: Alder", facts)
        self.assertIn("PROJECT: Willow", facts)
        self.assertIn("[PREFERENCE]", facts)
        self.assertIn("Preferred response style: bullet lists", facts)
        self.assertIn("[DECISION: SUPERSEDED DELIVERY DAY]", facts)
        self.assertIn("Tuesday (superseded by Thursday", facts)
        self.assertIn("[DECISION: CURRENT DELIVERY DAY]", facts)
        self.assertIn("Thursday (record", facts)
        self.assertIn("[TASK PROGRESSION]", facts)
        self.assertIn("completed: Collection; next unfinished: Deduplication", facts)
        self.assertNotIn("invented", facts)
        self.assertNotIn("unrelated answer", facts)

    def test_prompt_and_critic_variants_change_only_the_selected_input(self):
        scenario = {"question": "For Project Alder, what is next?"}
        original = (
            "PERSONALITY AND INTERNAL STATE\nDistracting guidance\n"
            "<retrieved_memory_evidence>PROJECT: Alder\n[TASK PROGRESSION]\n- next: deduplicate"
            "</retrieved_memory_evidence>\nQUESTION\nFor Project Alder, what is next?"
        )
        system, prompt = local.variant_messages(
            "evidence-focused", "primary", scenario, original
        )
        self.assertIn("only the retrieved", system)
        self.assertIn("deduplicate", prompt)
        self.assertNotIn("PERSONALITY", prompt)
        self.assertNotIn("Distracting guidance", prompt)
        critic_system, critic_prompt = local.variant_messages(
            "evidence-critic", "critic", scenario, original, '{"next":"export"}'
        )
        self.assertIn("Compare every requested field", critic_system)
        self.assertIn("PROJECT: Alder", critic_prompt)
        self.assertIn("For Project Alder, what is next?", critic_prompt)
        self.assertIn('{"next":"export"}', critic_prompt)
        baseline_system, baseline_prompt = local.variant_messages(
            "current", "critic", scenario, original, '{"next":"export"}'
        )
        self.assertIn("Internal Critic", baseline_system)
        self.assertNotIn("PROJECT: Alder", baseline_prompt)

    def test_production_critic_receives_question_retrieved_evidence_and_draft(self):
        from drift.core.brain import DriftBrain

        prompt = DriftBrain._evidence_critic_prompt(
            "What is next?",
            "state noise\n<retrieved_memory_evidence>PROJECT: Alder\n[TASK PROGRESSION] next: deduplicate</retrieved_memory_evidence>",
            '{"next":"export"}',
        )
        self.assertIn("USER REQUEST\nWhat is next?", prompt)
        self.assertIn("PROJECT: Alder", prompt)
        self.assertIn('{"next":"export"}', prompt)
        self.assertNotIn("state noise", prompt)


if __name__ == "__main__":
    unittest.main()

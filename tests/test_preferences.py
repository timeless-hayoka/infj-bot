"""Tests for the persistent user preferences system."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from preferences import PreferenceStore


class TestPreferenceStore(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.store = PreferenceStore(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_get_set(self):
        self.store.set("timezone", "UTC-4")
        self.assertEqual(self.store.get("timezone"), "UTC-4")

    def test_delete(self):
        self.store.set("temp", "value")
        self.assertTrue(self.store.delete("temp"))
        self.assertIsNone(self.store.get("temp"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("nope"))

    def test_default_values_exist(self):
        self.assertIsNotNone(self.store.get("communication_style"))
        self.assertIsNotNone(self.store.get("response_length"))

    def test_list_operations(self):
        self.store.add_to_list("interests", "cybersecurity")
        self.store.add_to_list("interests", "AI")
        self.assertEqual(self.store.get("interests"), ["cybersecurity", "AI"])
        self.store.remove_from_list("interests", "AI")
        self.assertEqual(self.store.get("interests"), ["cybersecurity"])

    def test_add_correction(self):
        self.store.add_correction("Don't use metaphors")
        corrections = self.store.get("corrections")
        self.assertIn("Don't use metaphors", corrections)

    def test_add_known_fact(self):
        self.store.add_known_fact("profession", "security researcher")
        facts = self.store.get("known_facts")
        self.assertEqual(facts["profession"], "security researcher")

    def test_format_prompt_snippet(self):
        self.store.set("communication_style", "direct")
        self.store.add_to_list("interests", "hacking")
        snippet = self.store.format_prompt_snippet()
        self.assertIn("direct", snippet)
        self.assertIn("hacking", snippet)

    def test_suggest_from_memory(self):
        suggestions = self.store.suggest_from_memory("I hate long explanations")
        self.assertTrue(any("shorter" in s or "avoid" in s for s in suggestions))

        suggestions = self.store.suggest_from_memory("I love quantum computing")
        self.assertTrue(any("interest" in s for s in suggestions))


if __name__ == "__main__":
    unittest.main()

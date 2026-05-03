"""Tests for the Relationship Model module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from relationship import RelationshipModel


class TestRelationshipModel(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.rel = RelationshipModel(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_initial_stage(self):
        self.assertEqual(self.rel.stats["current_stage"], "stranger")

    def test_record_interaction(self):
        self.rel.record_interaction("normal", "hello", "hi there")
        self.assertEqual(self.rel.stats["total_interactions"], 1)

    def test_stage_advancement(self):
        for i in range(12):
            self.rel.record_interaction("deep", f"msg {i}", f"resp {i}")
        self.assertEqual(self.rel.stats["current_stage"], "acquaintance")

    def test_detect_themes(self):
        self.rel.record_interaction("normal", "I love writing code", "me too")
        themes = self.rel.get_shared_themes()
        self.assertTrue(any(t["theme"] == "technology" for t in themes))

    def test_inside_joke(self):
        self.rel.add_inside_joke("the great router incident", "from networking discussion")
        jokes = self.rel.get_inside_jokes()
        self.assertEqual(len(jokes), 1)

    def test_format_prompt(self):
        self.rel.record_interaction("normal", "hi", "hello")
        prompt = self.rel.format_relationship_prompt()
        self.assertIn("stranger", prompt)
        self.assertIn("interactions", prompt)

    def test_anniversary(self):
        self.rel.record_interaction("normal", "first", "hello")
        # Should not have anniversary immediately
        self.assertIsNone(self.rel.recognize_anniversary())


if __name__ == "__main__":
    unittest.main()

"""Tests for the task scheduler and duration parser."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import TaskScheduler, parse_duration


class TestParseDuration(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(parse_duration("30m"), timedelta(minutes=30))

    def test_hours(self):
        self.assertEqual(parse_duration("2h"), timedelta(hours=2))

    def test_days(self):
        self.assertEqual(parse_duration("1d"), timedelta(days=1))

    def test_weeks(self):
        self.assertEqual(parse_duration("1w"), timedelta(weeks=1))

    def test_numeric_default_minutes(self):
        self.assertEqual(parse_duration("45"), timedelta(minutes=45))

    def test_unknown_returns_none(self):
        self.assertIsNone(parse_duration("xyz"))

    def test_with_spaces(self):
        self.assertEqual(parse_duration("2 hours"), timedelta(hours=2))


class TestTaskScheduler(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.sched = TaskScheduler(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_add_and_get(self):
        run_at = datetime.now() + timedelta(hours=1)
        tid = self.sched.add_task("Test task", "reminder", "payload", run_at)
        task = self.sched.get_task(tid)
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "Test task")
        self.assertEqual(task.status, "pending")

    def test_list_pending(self):
        now = datetime.now()
        self.sched.add_task("Soon", "reminder", "a", now + timedelta(minutes=5))
        self.sched.add_task("Later", "reminder", "b", now + timedelta(hours=2))
        pending = self.sched.list_pending()
        self.assertEqual(len(pending), 2)

    def test_list_due(self):
        now = datetime.now()
        self.sched.add_task("Overdue", "reminder", "a", now - timedelta(minutes=5))
        self.sched.add_task("Future", "reminder", "b", now + timedelta(hours=2))
        due = self.sched.list_due()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].title, "Overdue")

    def test_cancel_task(self):
        tid = self.sched.add_task("Cancel me", "reminder", "x", datetime.now())
        self.assertTrue(self.sched.cancel_task(tid))
        task = self.sched.get_task(tid)
        self.assertEqual(task.status, "cancelled")

    def test_cancel_nonexistent(self):
        self.assertFalse(self.sched.cancel_task("nope"))

    def test_mark_done(self):
        tid = self.sched.add_task("Done", "reminder", "x", datetime.now())
        self.assertTrue(self.sched.mark_done(tid))
        task = self.sched.get_task(tid)
        self.assertEqual(task.status, "done")

    def test_clear_old(self):
        old = datetime.now() - timedelta(days=60)
        tid = self.sched.add_task("Old", "reminder", "x", old)
        self.sched.mark_done(tid)
        removed = self.sched.clear_old(max_age_days=30)
        self.assertEqual(removed, 1)

    def test_reschedule_recurring(self):
        run_at = datetime.now()
        tid = self.sched.add_task("Daily", "reminder", "x", run_at, recurring="daily")
        task = self.sched.get_task(tid)
        next_tid = self.sched.reschedule_recurring(task)
        self.assertIsNotNone(next_tid)
        next_task = self.sched.get_task(next_tid)
        self.assertGreater(next_task.run_at, task.run_at)

    def test_reschedule_non_recurring(self):
        tid = self.sched.add_task("Once", "reminder", "x", datetime.now())
        task = self.sched.get_task(tid)
        next_tid = self.sched.reschedule_recurring(task)
        self.assertIsNone(next_tid)


if __name__ == "__main__":
    unittest.main()

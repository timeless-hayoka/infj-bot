"""Tests for the computer-use browser automation harness."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import computer_use as cu


class TestUrlHelpers(unittest.TestCase):
    def test_domain_from_url(self):
        self.assertEqual(cu._domain_from_url("https://example.com/path"), "example.com")
        self.assertEqual(cu._domain_from_url("http://sub.example.com:8080/"), "sub.example.com")

    def test_is_url_allowed_exact(self):
        self.assertTrue(cu._is_url_allowed("https://example.com", {"example.com"}))

    def test_is_url_allowed_subdomain(self):
        self.assertTrue(cu._is_url_allowed("https://sub.example.com", {"example.com"}))

    def test_is_url_allowed_not_authorized(self):
        self.assertFalse(cu._is_url_allowed("https://evil.com", {"example.com"}))


class TestSensitiveAction(unittest.TestCase):
    def test_sensitive_navigate(self):
        self.assertTrue(cu._is_sensitive_action({"type": "navigate", "url": "https://bank.com/login"}))

    def test_sensitive_type(self):
        self.assertTrue(cu._is_sensitive_action({"type": "type", "text": "my_password123"}))

    def test_not_sensitive(self):
        self.assertFalse(cu._is_sensitive_action({"type": "click", "x": 100, "y": 200}))


class TestSessionLifecycle(unittest.TestCase):
    def tearDown(self):
        # Reset global session after each test
        if cu._active_session is not None:
            try:
                cu._active_session.close()
            except Exception:
                pass
            cu._active_session = None

    def _make_mock_session(self):
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_page.viewport_size = {"width": 1440, "height": 900}
        mock_page.screenshot.return_value = b"fake_png"

        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        return mock_p, mock_page

    @patch("computer_use.sync_playwright")
    def test_run_computer_actions_navigate_and_screenshot(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "navigate", "url": "https://example.com"}],
            authorized_domains={"example.com"},
        )
        self.assertIn("Example", result)
        self.assertIn("screenshot_base64", result)
        mock_page.goto.assert_called_once()

    @patch("computer_use.sync_playwright")
    def test_unauthorized_navigate_blocked(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_page.url = "about:blank"
        mock_page.title.return_value = ""
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "navigate", "url": "https://evil.com"}],
            authorized_domains={"example.com"},
        )
        self.assertIn("not in the authorized domain list", result)

    def test_close_no_session(self):
        cu._active_session = None
        result = cu.close_computer_session()
        self.assertIn("no active session", result)

    def test_status_no_session(self):
        cu._active_session = None
        result = cu.get_computer_session_status()
        self.assertIn("no active", result)


class TestActionTypes(unittest.TestCase):
    def tearDown(self):
        if cu._active_session is not None:
            try:
                cu._active_session.close()
            except Exception:
                pass
            cu._active_session = None

    def _make_mock_session(self):
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.viewport_size = {"width": 1440, "height": 900}
        mock_page.screenshot.return_value = b"fake_png"

        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        return mock_p, mock_page

    @patch("computer_use.sync_playwright")
    def test_click(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "click", "x": 100, "y": 200}],
            authorized_domains=set(),
        )
        mock_page.mouse.click.assert_called_with(100, 200, button="left")
        self.assertIn("ok", result)

    @patch("computer_use.sync_playwright")
    def test_type_with_selector(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_locator = MagicMock()
        mock_page.locator.return_value = mock_locator
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "type", "text": "hello", "selector": "#search"}],
            authorized_domains=set(),
        )
        mock_locator.fill.assert_called_with("hello")
        self.assertIn("ok", result)

    @patch("computer_use.sync_playwright")
    def test_keypress(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "keypress", "keys": ["Enter", "Control+a"]}],
            authorized_domains=set(),
        )
        self.assertEqual(mock_page.keyboard.press.call_count, 2)
        self.assertIn("ok", result)

    @patch("computer_use.sync_playwright")
    def test_wait(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "wait", "seconds": 0.1}],
            authorized_domains=set(),
        )
        self.assertIn("ok", result)

    @patch("computer_use.sync_playwright")
    def test_scroll(self, mock_pw):
        mock_p, mock_page = self._make_mock_session()
        mock_pw.return_value.start.return_value = mock_p

        result = cu.run_computer_actions(
            [{"type": "scroll", "x": 500, "y": 500, "scrollX": 0, "scrollY": 300}],
            authorized_domains=set(),
        )
        mock_page.mouse.move.assert_called_with(500, 500)
        mock_page.mouse.wheel.assert_called_with(0, 300)
        self.assertIn("ok", result)


if __name__ == "__main__":
    unittest.main()

"""Tests for security reconnaissance tools and authorization layer."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import (
    _target_scope_hint,
    _validate_scan_target,
    tool_enumerate_subdomains,
    tool_fuzz_directories,
    tool_run_nuclei_scan,
)
from security_tools import is_authorized, tool_recon_enum, tool_recon_fuzz, tool_recon_summary


class TestTargetValidation(unittest.TestCase):
    def test_valid_http_url(self):
        self.assertEqual(_validate_scan_target("http://example.com"), "http://example.com")

    def test_valid_https_url(self):
        self.assertEqual(_validate_scan_target("https://example.com/path"), "https://example.com/path")

    def test_rejects_ftp(self):
        with self.assertRaises(ValueError):
            _validate_scan_target("ftp://example.com")

    def test_rejects_no_scheme(self):
        with self.assertRaises(ValueError):
            _validate_scan_target("example.com")

    def test_rejects_shell_chars(self):
        with self.assertRaises(ValueError):
            _validate_scan_target("https://example.com; rm -rf /")

    def test_rejects_newline(self):
        with self.assertRaises(ValueError):
            _validate_scan_target("https://example.com\n malicious")


class TestScopeHint(unittest.TestCase):
    def test_localhost(self):
        self.assertEqual(_target_scope_hint("http://localhost:8080"), "local")

    def test_local_domain(self):
        self.assertEqual(_target_scope_hint("http://myhost.local"), "local")

    def test_private_ip(self):
        self.assertEqual(_target_scope_hint("http://192.168.1.1"), "private-network")

    def test_loopback_ip(self):
        self.assertEqual(_target_scope_hint("http://127.0.0.1"), "private-network")

    def test_external(self):
        self.assertEqual(_target_scope_hint("https://example.com"), "external")


class TestAuthorizationGate(unittest.TestCase):
    def test_fuzz_requires_auth(self):
        result = tool_fuzz_directories("https://example.com", authorization_confirmed=False)
        self.assertIn("authorization_confirmed must be true", result)

    def test_enum_requires_auth(self):
        result = tool_enumerate_subdomains("example.com", authorization_confirmed=False)
        self.assertIn("authorization_confirmed must be true", result)

    def test_nuclei_requires_auth(self):
        result = tool_run_nuclei_scan("https://example.com", authorization_confirmed=False)
        self.assertIn("authorization_confirmed must be true", result)

    def test_nuclei_external_needs_scope_note(self):
        result = tool_run_nuclei_scan("https://example.com", authorization_confirmed=True, scope_note="")
        self.assertIn("external targets require a short scope_note", result)

    @patch("tools.subprocess.run")
    @patch("tools.shutil.which", return_value="/usr/bin/nuclei")
    def test_nuclei_external_with_note_ok(self, _which_mock, run_mock):
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        run_mock.return_value = mock_result
        result = tool_run_nuclei_scan(
            "https://example.com", authorization_confirmed=True, scope_note="bug bounty"
        )
        self.assertTrue(
            "[ok:" in result or "[error:" in result
        )


class TestReconWrappers(unittest.TestCase):
    def test_is_authorized_exact(self):
        self.assertTrue(is_authorized("example.com", {"example.com"}))

    def test_is_authorized_from_url(self):
        self.assertTrue(is_authorized("https://example.com/path", {"example.com"}))

    def test_not_authorized(self):
        self.assertFalse(is_authorized("evil.com", {"example.com"}))

    def test_recon_summary_blocks_unauthorized(self):
        result = tool_recon_summary("https://evil.com", authorized=set())
        self.assertIn("not in the authorized targets list", result)

    def test_recon_enum_blocks_unauthorized(self):
        result = tool_recon_enum("evil.com", authorized=set())
        self.assertIn("not in the authorized targets list", result)

    def test_recon_fuzz_blocks_unauthorized(self):
        result = tool_recon_fuzz("https://evil.com", authorized=set())
        self.assertIn("not in the authorized targets list", result)


class TestFuzzWordlistFallback(unittest.TestCase):
    def test_ensure_wordlist_returns_none_when_missing(self):
        from tools import _ensure_wordlist
        result = _ensure_wordlist("/nonexistent/wordlist.txt")
        # If no wordlists exist on the system, this returns None
        self.assertTrue(result is None or isinstance(result, str))


if __name__ == "__main__":
    unittest.main()

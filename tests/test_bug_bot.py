"""Tests for the Bug Bot — findings DB, report builder, BugBot, and commands.

Uses tmp_path fixtures for isolated DBs.
Mocks BugcrowdClient and DriftMemory so no real API calls or torch/chromadb needed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out torch / chromadb / sentence_transformers BEFORE any infj_bot import
# ---------------------------------------------------------------------------

_torch_stub = types.ModuleType("torch")
_torch_stub.set_default_device = lambda *a, **kw: None  # type: ignore[assignment]
_torch_stub.float32 = None
_torch_stub.no_grad = MagicMock(
    return_value=MagicMock(
        __enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)
    )
)
sys.modules.setdefault("torch", _torch_stub)

_chroma_stub = types.ModuleType("chromadb")
_chroma_api = types.ModuleType("chromadb.api")
_chroma_types = types.ModuleType("chromadb.api.types")
_chroma_types.Documents = list  # type: ignore[assignment]
_chroma_types.Embeddings = list  # type: ignore[assignment]
_chroma_stub.api = _chroma_api
_chroma_api.types = _chroma_types
sys.modules.setdefault("chromadb", _chroma_stub)
sys.modules.setdefault("chromadb.api", _chroma_api)
sys.modules.setdefault("chromadb.api.types", _chroma_types)

_st_stub = types.ModuleType("sentence_transformers")
sys.modules.setdefault("sentence_transformers", _st_stub)

_np_stub = types.ModuleType("numpy")
sys.modules.setdefault("numpy", _np_stub)

# Stub DriftMemory so bug_bot.py doesn't blow up on import
_memory_stub = types.ModuleType("infj_bot.core.memory")
_memory_stub.DriftMemory = type("DriftMemory", (), {})  # type: ignore[assignment]
sys.modules["infj_bot.core.memory"] = _memory_stub

# ---------------------------------------------------------------------------
# Now safe to import the modules under test
# ---------------------------------------------------------------------------

from infj_bot.core.plugins.findings_db import Finding, FindingsDB  # noqa: E402
from infj_bot.core.plugins.report_builder import ReportBuilder  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> FindingsDB:
    return FindingsDB(db_path=tmp_path / "test_findings.db")


@pytest.fixture()
def bot(tmp_path: Path):
    """Return a BugBot backed by a temporary DB with BugcrowdClient mocked."""
    with patch("infj_bot.core.bug_bot.BugcrowdClient") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        from infj_bot.core.bug_bot import BugBot

        b = BugBot.__new__(BugBot)
        from infj_bot.core.plugins.target_manager import TargetManager

        b.client = mock_client_cls.return_value
        b.findings = FindingsDB(db_path=tmp_path / "bot_findings.db")
        b.targets = TargetManager(db_path=tmp_path / "targets.db")
        b.reports = ReportBuilder()
        b.memory = None
        (tmp_path / "recon").mkdir(parents=True, exist_ok=True)
        return b


# ---------------------------------------------------------------------------
# FindingsDB tests
# ---------------------------------------------------------------------------


class TestFindingsDB:
    def test_add_and_get(self, db: FindingsDB) -> None:
        f = Finding(title="XSS via search", severity="P3", asset="example.com")
        fid = db.add(f)
        result = db.get(fid)
        assert result is not None
        assert result.title == "XSS via search"
        assert result.severity == "P3"

    def test_update(self, db: FindingsDB) -> None:
        f = Finding(title="Test", severity="P5")
        fid = db.add(f)
        db.update(fid, status="triaged")
        result = db.get(fid)
        assert result is not None
        assert result.status == "triaged"

    def test_delete(self, db: FindingsDB) -> None:
        f = Finding(title="Temp finding")
        fid = db.add(f)
        assert db.get(fid) is not None
        db.delete(fid)
        assert db.get(fid) is None

    def test_list(self, db: FindingsDB) -> None:
        for i in range(3):
            db.add(Finding(title=f"Finding {i}", severity="P4"))
        items = db.list(limit=10)
        assert len(items) == 3

    def test_add_and_get_evidence(self, db: FindingsDB) -> None:
        f = Finding(title="SSRF")
        fid = db.add(f)
        db.add_evidence(fid, "screenshot", "/tmp/screen.png", "PoC screenshot")
        ev = db.get_evidence(fid)
        assert len(ev) == 1
        assert ev[0]["path"] == "/tmp/screen.png"
        assert ev[0]["type"] == "screenshot"
        assert ev[0]["description"] == "PoC screenshot"

    def test_stats(self, db: FindingsDB) -> None:
        db.add(Finding(title="A", severity="P1", status="new"))
        db.add(Finding(title="B", severity="P2", status="new"))
        db.add(Finding(title="C", severity="P2", status="triaged"))
        s = db.stats()
        assert s["total"] == 3
        assert s["by_severity"].get("P1") == 1
        assert s["by_severity"].get("P2") == 2
        assert s["by_status"].get("new") == 2
        assert s["by_status"].get("triaged") == 1


# ---------------------------------------------------------------------------
# ReportBuilder tests
# ---------------------------------------------------------------------------


class TestReportBuilder:
    def test_build_sections_present(self) -> None:
        rb = ReportBuilder()
        f = Finding(
            title="SQL Injection",
            severity="P2",
            asset="api.example.com",
            description="Input not sanitised.",
            impact="Data exfiltration.",
            reproduction="1. Login\n2. Inject payload",
            fix="Use parameterised queries.",
        )
        report = rb.build(f, [])
        assert "## Summary" in report
        assert "## Impact" in report
        assert "## Steps to Reproduce" in report
        assert "## Evidence" in report
        assert "## Suggested Fix" in report

    def test_build_with_evidence(self) -> None:
        rb = ReportBuilder()
        f = Finding(title="IDOR", severity="P3")
        ev = [{"type": "screenshot", "path": "/tmp/poc.png", "description": "Proof"}]
        report = rb.build(f, ev)
        assert "/tmp/poc.png" in report
        assert "screenshot" in report

    def test_build_summary_table(self) -> None:
        rb = ReportBuilder()
        findings = [
            Finding(title="XSS", severity="P3", status="new", asset="x.com"),
            Finding(title="CSRF", severity="P4", status="triaged", asset="y.com"),
        ]
        summary = rb.build_summary(findings)
        assert "| ID |" in summary
        assert "XSS" in summary
        assert "CSRF" in summary

    def test_build_summary_empty(self) -> None:
        rb = ReportBuilder()
        result = rb.build_summary([])
        assert "No findings" in result


# ---------------------------------------------------------------------------
# BugBot tests
# ---------------------------------------------------------------------------


class TestBugBotAddFinding:
    def test_add_finding_returns_string_with_id(self, bot) -> None:
        result = bot.add_finding(title="XSS", severity="P3", asset="app.example.com")
        assert isinstance(result, str)
        assert "P3" in result
        # The returned string contains the finding ID — verify it ends up in DB
        fid = result.split()[3]  # "🐛 Finding <id> —"
        assert bot.findings.get(fid) is not None

    def test_add_finding_stored_in_db(self, bot) -> None:
        bot.add_finding(title="RCE", severity="P1", asset="backend.example.com")
        items = bot.findings.list()
        assert len(items) == 1
        assert items[0].title == "RCE"


class TestBugBotListFinding:
    def test_list_findings_shows_added(self, bot) -> None:
        bot.add_finding(title="SSRF", severity="P2")
        bot.add_finding(title="IDOR", severity="P3")
        result = bot.list_findings()
        assert "SSRF" in result
        assert "IDOR" in result

    def test_list_findings_empty(self, bot) -> None:
        result = bot.list_findings()
        assert "No findings" in result


class TestBugBotGetFinding:
    def test_get_finding_detail(self, bot) -> None:
        bot.add_finding(
            title="Path Traversal",
            severity="P2",
            asset="files.example.com",
            description="Directory traversal via ../",
        )
        fid = bot.findings.list()[0].id
        result = bot.get_finding(fid)
        assert "Path Traversal" in result
        assert "P2" in result
        assert "files.example.com" in result

    def test_get_finding_not_found(self, bot) -> None:
        result = bot.get_finding("nonexistent")
        assert "not found" in result.lower()


class TestBugBotStats:
    def test_stats_counts(self, bot) -> None:
        bot.add_finding(title="A", severity="P1")
        bot.add_finding(title="B", severity="P2")
        bot.add_finding(title="C", severity="P2")
        result = bot.stats()
        assert "P1" in result
        assert "P2" in result
        assert "3" in result


class TestBugBotGenerateReport:
    def test_generate_report_writes_file(self, bot) -> None:
        from infj_bot.core.bug_bot import RECON_DIR

        RECON_DIR.mkdir(parents=True, exist_ok=True)
        bot.add_finding(title="LFI", severity="P2", asset="cdn.example.com")
        fid = bot.findings.list()[0].id
        result = bot.generate_report(fid)
        assert "LFI" in result
        # Check file was created
        report_file = RECON_DIR / f"report_{fid}.md"
        assert report_file.exists()
        content = report_file.read_text()
        assert "LFI" in content

    def test_generate_report_not_found(self, bot) -> None:
        result = bot.generate_report("bad_id")
        assert "not found" in result.lower()


class TestBugBotAttachEvidence:
    def test_attach_evidence_success(self, bot) -> None:
        bot.add_finding(title="XXE", severity="P2")
        fid = bot.findings.list()[0].id
        result = bot.attach_evidence(fid, "/tmp/req.txt", description="HTTP request")
        assert fid in result
        assert "/tmp/req.txt" in result

    def test_attach_evidence_shown_in_get(self, bot) -> None:
        bot.add_finding(title="SSTI", severity="P3")
        fid = bot.findings.list()[0].id
        bot.attach_evidence(fid, "/tmp/poc.png", ev_type="screenshot")
        detail = bot.get_finding(fid)
        assert "1" in detail  # Evidence count should be 1

    def test_attach_evidence_not_found(self, bot) -> None:
        result = bot.attach_evidence("bad_id", "/tmp/x.png")
        assert "not found" in result.lower()


class TestBugBotDashboard:
    def test_dashboard_header(self, bot) -> None:
        result = bot.dashboard()
        assert "Dashboard" in result

    def test_dashboard_severity_breakdown(self, bot) -> None:
        bot.add_finding(title="Crit", severity="P1")
        bot.add_finding(title="High", severity="P2")
        result = bot.dashboard()
        assert "P1" in result
        assert "P2" in result

    def test_dashboard_total_count(self, bot) -> None:
        for i in range(3):
            bot.add_finding(title=f"Finding {i}", severity="P3")
        result = bot.dashboard()
        assert "3" in result

    def test_dashboard_recent_findings_table(self, bot) -> None:
        bot.add_finding(title="Auth Bypass", severity="P1")
        result = bot.dashboard()
        assert "Auth Bypass" in result

    def test_dashboard_db_path(self, bot) -> None:
        result = bot.dashboard()
        assert "DB" in result or str(bot.findings.db_path) in result


class TestBugBotDraftWithAI:
    def test_draft_without_brain_returns_standard(self, bot) -> None:
        bot.add_finding(title="Open Redirect", severity="P4", asset="sso.example.com")
        fid = bot.findings.list()[0].id
        result = bot.draft_with_ai(fid, brain=None)
        # Should contain standard report sections
        assert "## Summary" in result or "Open Redirect" in result
        # Should contain the note about AI unavailability
        assert "AI enhancement was unavailable" in result or "standard report" in result

    def test_draft_with_brain_returns_enhanced(self, bot) -> None:
        bot.add_finding(title="CORS Misconfiguration", severity="P3")
        fid = bot.findings.list()[0].id
        mock_brain = MagicMock()
        mock_brain.agent_turn.return_value = "Enhanced report content from AI."
        result = bot.draft_with_ai(fid, brain=mock_brain)
        assert result == "Enhanced report content from AI."
        mock_brain.agent_turn.assert_called_once()

    def test_draft_with_brain_failure_falls_back(self, bot) -> None:
        bot.add_finding(title="Info Leak", severity="P4")
        fid = bot.findings.list()[0].id
        mock_brain = MagicMock()
        mock_brain.agent_turn.side_effect = RuntimeError("API error")
        result = bot.draft_with_ai(fid, brain=mock_brain)
        # Should fall back to standard report with note
        assert "Info Leak" in result or "## Summary" in result

    def test_draft_not_found(self, bot) -> None:
        result = bot.draft_with_ai("nonexistent")
        assert "not found" in result.lower()


class TestNucleiDeduplication:
    def _make_nuclei_item(
        self, host: str, template_id: str, severity: str = "critical"
    ):
        return {
            "host": host,
            "template-id": template_id,
            "info": {"name": f"Test {template_id}", "severity": severity},
        }

    def test_dedup_skips_duplicate_asset_and_vuln_type(
        self, bot, tmp_path: Path
    ) -> None:
        import json

        out_dir = tmp_path / "recon_run"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "nuclei.json"

        # Two items with same host+template-id (duplicate)
        items = [
            self._make_nuclei_item("target.example.com", "cve-2021-12345"),
            self._make_nuclei_item("target.example.com", "cve-2021-12345"),
        ]
        output.write_text(json.dumps(items))

        # Patch subprocess so nuclei "runs" and produces our fixture output
        with patch("infj_bot.core.bug_bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # _run_nuclei reads the output file directly — it was created above
            result = bot._run_nuclei(["target.example.com"], out_dir)

        # Only one finding should be in the DB (second was skipped)
        findings = bot.findings.list()
        assert len(findings) == 1
        assert "skipped" in result or "dedup" in result

    def test_dedup_different_assets_both_added(self, bot, tmp_path: Path) -> None:
        import json

        out_dir = tmp_path / "recon_run2"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "nuclei.json"

        items = [
            self._make_nuclei_item("host1.example.com", "cve-2021-99999"),
            self._make_nuclei_item("host2.example.com", "cve-2021-99999"),
        ]
        output.write_text(json.dumps(items))

        with patch("infj_bot.core.bug_bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            bot._run_nuclei(["host1.example.com", "host2.example.com"], out_dir)

        findings = bot.findings.list()
        assert len(findings) == 2


# ---------------------------------------------------------------------------
# /bug add key=value parsing test
# ---------------------------------------------------------------------------


class TestBugAddKeyValueParsing:
    def test_parse_kv_all_keys(self) -> None:
        from infj_bot.core.commands import _parse_kv_bug_add

        text = (
            "title=SQL Injection via search severity=P2 asset=api.example.com "
            "desc=Input not sanitised type=Injection impact=Data leak "
            "repro=1. Inject fix=Use params"
        )
        result = _parse_kv_bug_add(text)
        assert result.get("title") == "SQL Injection via search"
        assert result.get("severity") == "P2"
        assert result.get("asset") == "api.example.com"
        assert result.get("desc") == "Input not sanitised"
        assert result.get("type") == "Injection"
        assert result.get("impact") == "Data leak"
        assert result.get("repro") == "1. Inject"
        assert result.get("fix") == "Use params"

    def test_parse_kv_minimal(self) -> None:
        from infj_bot.core.commands import _parse_kv_bug_add

        result = _parse_kv_bug_add("title=XSS Bug")
        assert result.get("title") == "XSS Bug"

    def test_parse_kv_values_with_spaces(self) -> None:
        from infj_bot.core.commands import _parse_kv_bug_add

        result = _parse_kv_bug_add("title=My Finding With Spaces severity=P1")
        assert result.get("title") == "My Finding With Spaces"
        assert result.get("severity") == "P1"


# ---------------------------------------------------------------------------
# BugBot.health() with no API key
# ---------------------------------------------------------------------------


class TestBugBotHealth:
    def test_health_no_api_key_returns_error_string(self, bot) -> None:
        # Configure the mock client's health() to return an error string
        bot.client.health.return_value = "❌ BUGCROWD_API_KEY not set"
        result = bot.health()
        assert isinstance(result, str)
        assert "BUGCROWD_API_KEY" in result or "❌" in result

"""DRIFT Bug Bot — the beast.

Orchestrates recon, findings tracking, report generation, and
Bugcrowd submission for bug bounty hunting.

Safe by design:
- Rate-limited API calls (1 req/sec default)
- Scanner rate limits (nuclei -rl 10, ffuf -rate 10)
- Scope enforcement before any active recon
- No destructive actions
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from drift.core.config import PROJECT_ROOT
from drift.core.memory import DriftMemory
from drift.core.plugins.bugcrowd_client import BugcrowdClient
from drift.core.plugins.findings_db import Finding, FindingsDB
from drift.core.plugins.report_builder import ReportBuilder
from drift.core.plugins.target_manager import TargetManager


RECON_DIR = Path(PROJECT_ROOT) / "recon"
BUGBOT_LOG = Path(PROJECT_ROOT) / "logs" / "bugbot.log"


class BugBot:
    """
    The main Bug Bounty engine.

    Usage:
        bot = BugBot()
        bot.sync_programs()          # Pull from Bugcrowd
        bot.recon(program_id)        # Run scoped recon
        bot.add_finding(...)         # Log a finding
        bot.generate_report(fid)     # Draft a report
        bot.submit(finding_id)       # Submit to Bugcrowd
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        memory: Optional[DriftMemory] = None,
    ):
        self.client = BugcrowdClient(api_key=api_key)
        self.findings = FindingsDB()
        self.targets = TargetManager()
        self.reports = ReportBuilder()
        self.memory = memory
        RECON_DIR.mkdir(parents=True, exist_ok=True)
        BUGBOT_LOG.parent.mkdir(parents=True, exist_ok=True)

    # ── Program Sync ──────────────────────────────────────────────

    def sync_programs(self) -> str:
        """Fetch Bugcrowd programs and sync scope to local target DB."""
        try:
            programs = self.client.list_programs()
        except Exception as exc:
            return f"❌ Failed to fetch programs: {exc}"

        if not programs:
            return "⚠️ No Bugcrowd programs found. Check your API key."

        for prog in programs:
            try:
                full = self.client.get_program(prog.uuid)
                self.targets.delete_program(prog.uuid)
                self.targets.bulk_add(prog.uuid, prog.name, full.scope, scope="in")
                self.targets.bulk_add(prog.uuid, prog.name, full.oos, scope="out")
                self._log(
                    f"Synced program: {prog.name} ({len(full.scope)} in / {len(full.oos)} out)"
                )
            except Exception as exc:
                self._log(f"⚠️ Failed to sync {prog.name}: {exc}")

        return f"✅ Synced {len(programs)} program(s). Targets: {self.targets.count(scope='in')} in / {self.targets.count(scope='out')} out."

    def list_programs(self) -> str:
        """Pretty-print enrolled programs."""
        try:
            programs = self.client.list_programs()
        except Exception as exc:
            return f"❌ {exc}"
        if not programs:
            return "No programs found."
        lines = ["🎯 Bugcrowd Programs"]
        for p in programs:
            lines.append(
                f"  • {p.name} — {p.status} ({p.rewards or 'no rewards info'})"
            )
        return "\n".join(lines)

    # ── Recon ─────────────────────────────────────────────────────

    def recon(self, program_id: str, tool: str = "all") -> str:
        """
        Run scoped recon for a program.

        tool: all | subdomains | nuclei | fuzz
        """
        targets = self.targets.list_targets(program_id=program_id, scope="in")
        if not targets:
            return (
                f"❌ No in-scope targets for program {program_id}. Run /bug sync first."
            )

        domains = [t.asset for t in targets if t.asset_type in ("domain", "wildcard")]
        urls = [t.asset for t in targets if t.asset_type == "url"]

        results: List[str] = []
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = RECON_DIR / program_id / stamp
        out_dir.mkdir(parents=True, exist_ok=True)

        # Subdomain enumeration
        if tool in ("all", "subdomains") and domains:
            results.append(self._run_subfinder(domains, out_dir))

        # Nuclei scan
        if tool in ("all", "nuclei"):
            scan_targets = domains + urls
            if scan_targets:
                results.append(self._run_nuclei(scan_targets, out_dir))

        # Directory fuzzing
        if tool in ("all", "fuzz") and (domains or urls):
            results.append(self._run_ffuf(domains + urls, out_dir))

        summary = "\n".join(results)
        self._log(f"Recon {program_id}/{tool}: {summary[:200]}")
        return f"🛰️ Recon complete for {program_id}\n{summary}\n📁 Artifacts: {out_dir}"

    def _run_subfinder(self, domains: List[str], out_dir: Path) -> str:
        domain_file = out_dir / "domains.txt"
        domain_file.write_text("\n".join(domains))
        output = out_dir / "subdomains.txt"
        try:
            subprocess.run(
                ["subfinder", "-dL", str(domain_file), "-o", str(output), "-silent"],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            count = len(output.read_text().splitlines()) if output.exists() else 0
            return f"  🔍 subfinder: {count} subdomains → {output.name}"
        except FileNotFoundError:
            return "  ⚠️ subfinder not installed"
        except Exception as exc:
            return f"  ❌ subfinder error: {exc}"

    def _run_nuclei(self, targets: List[str], out_dir: Path) -> str:
        target_file = out_dir / "nuclei_targets.txt"
        target_file.write_text("\n".join(targets))
        output = out_dir / "nuclei.json"
        try:
            subprocess.run(
                [
                    "nuclei",
                    "-l",
                    str(target_file),
                    "-severity",
                    "critical,high,medium",
                    "-rate-limit",
                    "10",
                    "-json-export",
                    str(output),
                    "-silent",
                ],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if output.exists():
                data = (
                    json.loads(output.read_text()) if output.stat().st_size > 0 else []
                )
                # Auto-ingest critical/high findings with deduplication
                skipped = 0
                seen_this_run: set = set()
                for item in data:
                    sev = item.get("info", {}).get("severity", "").lower()
                    if sev in ("critical", "high"):
                        asset = item.get("host", "")
                        vuln_type = f"Nuclei: {item.get('template-id', 'unknown')}"
                        dedup_key = (asset, vuln_type)
                        # DB-level dedup check — no arbitrary limit
                        duplicate = dedup_key in seen_this_run or self.findings.exists_by_asset_and_vuln_type(asset, vuln_type)
                        if duplicate:
                            skipped += 1
                            continue
                        seen_this_run.add(dedup_key)
                        self.add_finding(
                            program_id="auto",
                            title=item.get("info", {}).get("name", "Nuclei finding"),
                            vuln_type=vuln_type,
                            severity="P2" if sev == "critical" else "P3",
                            asset=asset,
                            description=json.dumps(item.get("info", {}), indent=2),
                            confidence="medium",
                        )
                ch_count = len(
                    [
                        d
                        for d in data
                        if d.get("info", {}).get("severity", "").lower() in ("critical", "high")
                    ]
                )
                skip_note = f", {skipped} skipped (dedup)" if skipped else ""
                return f"  🎯 nuclei: {len(data)} findings → {output.name} ({ch_count} critical/high{skip_note})"
            return "  🎯 nuclei: no output"
        except FileNotFoundError:
            return "  ⚠️ nuclei not installed"
        except Exception as exc:
            return f"  ❌ nuclei error: {exc}"

    def _run_ffuf(self, targets: List[str], out_dir: Path) -> str:
        # Run ffuf on first domain only (safety)
        domain = targets[0].replace("https://", "").replace("http://", "").split("/")[0]
        output = out_dir / "ffuf.json"
        try:
            subprocess.run(
                [
                    "ffuf",
                    "-u",
                    f"https://{domain}/FUZZ",
                    "-w",
                    "/usr/share/wordlists/dirb/common.txt",
                    "-rate",
                    "10",
                    "-o",
                    str(output),
                    "-of",
                    "json",
                    "-s",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if output.exists():
                data = (
                    json.loads(output.read_text()) if output.stat().st_size > 0 else {}
                )
                results = data.get("results", [])
                return f"  🌪️ ffuf: {len(results)} hits on {domain} → {output.name}"
            return "  🌪️ ffuf: no output"
        except FileNotFoundError:
            return "  ⚠️ ffuf not installed"
        except Exception as exc:
            return f"  ❌ ffuf error: {exc}"

    # ── Findings ──────────────────────────────────────────────────

    def add_finding(
        self,
        program_id: str = "",
        program_name: str = "",
        title: str = "",
        vuln_type: str = "",
        severity: str = "P5",
        cvss: float = 0.0,
        asset: str = "",
        description: str = "",
        reproduction: str = "",
        impact: str = "",
        fix: str = "",
        confidence: str = "low",
        notes: str = "",
    ) -> str:
        finding = Finding(
            program_id=program_id,
            program_name=program_name,
            title=title,
            vuln_type=vuln_type,
            severity=severity,
            cvss=cvss,
            asset=asset,
            description=description,
            reproduction=reproduction,
            impact=impact,
            fix=fix,
            confidence=confidence,
            notes=notes,
        )
        fid = self.findings.add(finding)
        if self.memory:
            self.memory.learn_concept(
                f"Finding {fid}: {title}",
                f"{description}\n\nAsset: {asset}\nSeverity: {severity}\nConfidence: {confidence}",
                tags=["bug", "finding", program_id],
                importance=0.9 if severity in ("P1", "P2") else 0.7,
            )
        return f"🐛 Finding logged: {fid} — {title} ({severity})"

    def get_finding(self, fid: str) -> str:
        f = self.findings.get(fid)
        if not f:
            return f"❌ Finding {fid} not found."
        ev = self.findings.get_evidence(fid)
        lines = [
            f"🐛 Finding {f.id}",
            f"  Title: {f.title}",
            f"  Severity: {f.severity} | Confidence: {f.confidence} | Status: {f.status}",
            f"  Asset: {f.asset or 'N/A'}",
            f"  Type: {f.vuln_type or 'N/A'}",
            f"  Description: {f.description[:200]}..."
            if len(f.description) > 200
            else f"  Description: {f.description}",
            f"  Evidence: {len(ev)} item(s)",
        ]
        return "\n".join(lines)

    def list_findings(
        self, program_id: Optional[str] = None, status: Optional[str] = None
    ) -> str:
        items = self.findings.list(program_id=program_id, status=status, limit=100)
        if not items:
            return "No findings."
        lines = [f"{'ID':<10} {'Severity':<10} {'Status':<12} {'Title'}"]
        lines.append("-" * 60)
        for f in items:
            title = (f.title[:35] + "...") if len(f.title) > 35 else f.title
            lines.append(f"{f.id:<10} {f.severity:<10} {f.status:<12} {title}")
        return "\n".join(lines)

    def stats(self) -> str:
        s = self.findings.stats()
        lines = [
            "📊 Bug Bot Stats",
            f"  Total findings: {s['total']}",
            "  By severity:",
        ]
        for sev, count in sorted(s.get("by_severity", {}).items()):
            lines.append(f"    {sev}: {count}")
        lines.append("  By status:")
        for st, count in sorted(s.get("by_status", {}).items()):
            lines.append(f"    {st}: {count}")
        return "\n".join(lines)

    # ── Reports ───────────────────────────────────────────────────

    def generate_report(self, finding_id: str) -> str:
        f = self.findings.get(finding_id)
        if not f:
            return f"❌ Finding {finding_id} not found."
        ev = self.findings.get_evidence(finding_id)
        report = self.reports.build(f, ev)
        out_path = RECON_DIR / f"report_{finding_id}.md"
        out_path.write_text(report)
        return f"📝 Report drafted: {out_path}\n\n{report[:500]}..."

    def preview_report(self, finding_id: str) -> str:
        f = self.findings.get(finding_id)
        if not f:
            return f"❌ Finding {finding_id} not found."
        ev = self.findings.get_evidence(finding_id)
        return self.reports.build(f, ev)

    # ── Bugcrowd Submission ───────────────────────────────────────

    def submit(self, finding_id: str) -> str:
        f = self.findings.get(finding_id)
        if not f:
            return f"❌ Finding {finding_id} not found."
        if not f.program_id or f.program_id == "auto":
            return "❌ Finding has no Bugcrowd program ID. Set it with /bug update."
        try:
            sub_id = self.client.create_submission(
                program_uuid=f.program_id,
                title=f.title,
                vulnerability_type=f.vuln_type or "Other",
                severity=f.severity,
                description=f.description,
                reproduction=f.reproduction,
                impact=f.impact,
                asset=f.asset,
            )
            self.findings.update(
                finding_id,
                status="submitted",
                bugcrowd_submission_id=sub_id,
                submitted_at=datetime.now().isoformat(timespec="seconds"),
            )
            return f"✅ Submitted to Bugcrowd! Submission ID: {sub_id}"
        except Exception as exc:
            return f"❌ Submission failed: {exc}"

    def attach_evidence(
        self,
        finding_id: str,
        path: str,
        ev_type: str = "file",
        description: str = "",
    ) -> str:
        """Attach evidence to a finding."""
        f = self.findings.get(finding_id)
        if not f:
            return f"❌ Finding {finding_id} not found."
        self.findings.add_evidence(finding_id, ev_type, path, description)
        return f"📎 Evidence attached to {finding_id}: [{ev_type}] {path}"

    def dashboard(self) -> str:
        """Return a rich text dashboard summary."""
        s = self.findings.stats()
        total = s["total"]
        by_sev = s.get("by_severity", {})
        by_status = s.get("by_status", {})
        by_program = s.get("by_program", {})

        lines = [
            "═══ Bug Bot Dashboard ═══",
            f"Total findings: {total}",
            "",
            "By Severity:",
        ]
        for sev in ("P1", "P2", "P3", "P4", "P5"):
            count = by_sev.get(sev, 0)
            if count:
                lines.append(f"  {sev}: {count}")

        lines.append("")
        lines.append("By Status:")
        for st, count in sorted(by_status.items()):
            lines.append(f"  {st}: {count}")

        # Recent 5 findings table
        recent = self.findings.list(limit=5)
        if recent:
            lines.extend(
                [
                    "",
                    "Recent Findings:",
                    f"{'ID':<10} {'Sev':<5} {'Status':<14} {'Title'}",
                    "-" * 60,
                ]
            )
            for f in recent:
                title = (f.title[:40] + "...") if len(f.title) > 40 else f.title
                lines.append(f"{f.id:<10} {f.severity:<5} {f.status:<14} {title}")

        # Top program by finding count
        if by_program:
            top_prog = max(by_program, key=lambda k: by_program[k])
            if top_prog:
                lines.append(
                    f"\nTop program: {top_prog} ({by_program[top_prog]} finding(s))"
                )

        lines.append(f"\nDB: {self.findings.db_path}")
        return "\n".join(lines)

    def draft_with_ai(self, finding_id: str, brain=None) -> str:
        """Generate an AI-enhanced report for a finding."""
        f = self.findings.get(finding_id)
        if not f:
            return f"❌ Finding {finding_id} not found."
        ev = self.findings.get_evidence(finding_id)
        standard_report = self.reports.build(f, ev)

        if brain is not None:
            prompt = (
                f"You are a professional bug bounty report writer. "
                f"Please improve the following vulnerability report for clarity and impact. "
                f"Make it compelling, well-structured, and persuasive for a triage team. "
                f"Preserve all technical details.\n\n{standard_report}"
            )
            try:
                enhanced = brain.agent_turn(prompt, tools_enabled=False)
                if enhanced:
                    return enhanced
            except Exception:
                pass

        return (
            standard_report
            + "\n\n---\n*Note: AI enhancement was unavailable. Showing standard report.*"
        )

    # ── Utility ───────────────────────────────────────────────────

    def health(self) -> str:
        api = self.client.health()
        return f"{api}\n📁 Findings DB: {self.findings.stats()['total']} finding(s)\n🎯 Targets DB: {self.targets.count(scope='in')} in-scope / {self.targets.count(scope='out')} out-of-scope"

    def _log(self, msg: str):
        from drift.core.jsonl_logger import HardenedJsonlLogger
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        HardenedJsonlLogger(BUGBOT_LOG).write_raw(line)

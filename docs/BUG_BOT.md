# Bug Bot — Bugcrowd-Aware Vulnerability Workflow

`core/bug_bot.py` ("the beast") is a self-contained workflow for hunting, tracking, and submitting bug-bounty findings. It is exposed through the `/bug` slash command, an internal SQLite store, and an optional Bugcrowd API integration.

It is deliberately **scope-aware and rate-limited by design**:

- Bugcrowd API calls default to **1 req/sec**.
- Scanner rate-limits are pinned: `nuclei -rate-limit 10`, `ffuf -rate 10`.
- Recon only runs against assets already confirmed `scope="in"` in the local target DB.
- No destructive actions — Bug Bot writes findings and reports, it does not weaponize them.

---

## Files at a glance

| File | Role |
|------|------|
| `core/bug_bot.py`                 | `BugBot` orchestrator: recon, findings, reports, submit |
| `core/plugins/bugcrowd_client.py` | Bugcrowd API v4 client (`BugcrowdClient`, polite rate limiting) |
| `core/plugins/findings_db.py`     | SQLite findings store (`FindingsDB`, `Finding` dataclass) |
| `core/plugins/target_manager.py`  | Scope DB (`TargetManager`, `Target`) — in/out/pending assets |
| `core/plugins/report_builder.py`  | Markdown report builder for triage submissions |
| `core/commands.py` → `handle_bug_command` | Slash-command dispatch |
| `tests/test_bug_bot.py`           | Unit + flow coverage |

Data lives under `INFJ_DATA_DIR` (or `data/` next to the package) in two SQLite databases:

- `data/bugbot_findings.db` — `findings` and `evidence` tables.
- `data/bugbot_targets.db` — scope per program.

Recon artifacts (subdomain lists, nuclei JSON, ffuf JSON, generated reports) go to `recon/<program_id>/<timestamp>/` at the project root. Logs append to `logs/bugbot.log`.

---

## Configuration

The only required secret is `BUGCROWD_API_KEY` for live submission. Recon will run without it as long as the local target DB has scope rows.

```bash
# .env
BUGCROWD_API_KEY=your_bugcrowd_key_here
# Optional: which domains the broader bughunter mode is allowed to touch
INFJ_AUTHORIZED_TARGETS=example.com,localhost
```

`INFJ_AUTHORIZED_TARGETS` is a separate `bughunter` mode allowlist (see `commands.py`). Bug Bot itself relies on the per-program `scope` table for authorization.

External binaries that Bug Bot will shell out to if present (none are bundled):

| Tool | Used for | If missing |
|------|----------|-----------|
| `subfinder` | Subdomain enumeration | Skipped with a warning |
| `nuclei`    | Template-based vuln scan, severity ≥ medium | Skipped with a warning |
| `ffuf`      | Directory fuzzing (first domain only, for safety) | Skipped with a warning |

---

## `/bug` command surface

Sub-commands are dispatched by `handle_bug_command(args, state, brain, memory)`:

| Command | Description |
|---------|-------------|
| `/bug sync`                                 | Pull Bugcrowd programs and refresh the local scope DB |
| `/bug programs`                             | List enrolled programs |
| `/bug recon <program_id> [all\|subdomains\|nuclei\|fuzz]` | Run scoped recon; auto-ingests critical/high nuclei findings |
| `/bug add <title> \| <severity> \| <asset> \| <description>` | Pipe-form finding |
| `/bug add title=... severity=... asset=... desc=... [type=... impact=... repro=... fix=...]` | Key=value finding |
| `/bug list`                                 | All findings (latest 100) |
| `/bug get <id>`                             | Single-finding detail + evidence count |
| `/bug evidence <id> <path> [description]`   | Attach a file or note to a finding |
| `/bug dashboard`                            | Severity/status rollup + top program + recent 5 |
| `/bug report <id>`                          | Render standard markdown report to `recon/report_<id>.md` |
| `/bug preview <id>`                         | Print the would-be report inline |
| `/bug ai <id>`                              | Improve report tone via the active `DriftBrain` (no tools) |
| `/bug submit <id>`                          | POST to Bugcrowd, store submission id, set status `submitted` |
| `/bug stats`                                | Counts by severity / status |
| `/bug health`                               | Bugcrowd API + findings DB sanity check |

Severities use the Bugcrowd **P1–P5** scale. Status moves through `new → triaged → confirmed → submitted → accepted | rejected | false_positive`.

---

## Programmatic usage

`BugBot` is fine to use directly from Python; it wires up its own clients on construction.

```python
from infj_bot.core.bug_bot import BugBot
from infj_bot.core.memory import DriftMemory

bot = BugBot(memory=DriftMemory())

bot.sync_programs()
bot.recon("c0ffee-program-uuid", tool="nuclei")

fid = bot.add_finding(
    program_id="c0ffee-program-uuid",
    title="Reflected XSS in /search",
    vuln_type="XSS > Reflected",
    severity="P3",
    asset="https://target.example.com",
    description="...",
    reproduction="curl ...",
    impact="Session hijack via crafted link",
    confidence="medium",
)
bot.attach_evidence(fid, "recon/.../screenshot.png", ev_type="image")
print(bot.preview_report(fid))
bot.submit(fid)
```

Passing `memory=` causes every finding to be mirrored into DRIFT's long-term store via `learn_concept`, tagged `["bug", "finding", <program_id>]`. P1/P2 findings get importance `0.9`, others `0.7` — they will surface during normal chat retrieval whenever the assistant is asked about the affected asset.

---

## Recon details

`bot.recon(program_id, tool)` is the only path that touches the network from a target perspective. The flow:

1. Look up `scope="in"` rows from `TargetManager` filtered by program.
2. Bucket assets as `domain | wildcard | url` for the chosen runners.
3. Write a fresh timestamped artifact directory under `recon/<program_id>/<stamp>/`.
4. Run each enabled runner with hard timeouts (300s subfinder / 600s nuclei / 300s ffuf).
5. **Auto-ingest** any nuclei finding with severity `critical` or `high` as a Bug Bot finding, with dedup against:
   - prior findings sharing `(asset, vuln_type)`, and
   - duplicates encountered earlier in the same run.
6. Append a summary line to `logs/bugbot.log`.

Auto-ingested findings are tagged `program_id="auto"`, `confidence="medium"`, and *must* be retagged with the real program id (via direct DB edit or future `/bug update`) before `submit` will accept them.

---

## Reports

`ReportBuilder.build(finding, evidence)` renders a standard markdown template. `BugBot.draft_with_ai(fid, brain=...)` wraps that text in a critique prompt and runs it through the active `DriftBrain` with tools disabled to avoid side effects. If the LLM call fails for any reason, the standard report is returned with a `*Note: AI enhancement was unavailable*` footer — `draft_with_ai` never raises.

Generated reports are saved to `recon/report_<finding_id>.md`. They are intentionally **not** auto-attached to the finding row — they are a derived artifact, regenerable from the data.

---

## Bugcrowd submission

`bot.submit(fid)` POSTs through `BugcrowdClient.create_submission(...)`. Preconditions:

- `Finding.program_id` must be a real program UUID, **not** `"auto"`.
- `BUGCROWD_API_KEY` must be set in the environment.

On success the row is updated with `status="submitted"`, the returned `bugcrowd_submission_id`, and an ISO timestamp.

---

## Operational pitfalls

- **No CVSS auto-calculation.** `Finding.cvss` defaults to `0.0`. Set it explicitly when you care.
- **`/bug add` with no separators** treats the entire argument as a `title` and stamps a `P5` placeholder. Useful for capture-then-edit workflows; **not** a triage shortcut.
- **`recon` "all"** runs every available tool sequentially against the same target set. For large scopes, prefer running one tool at a time so failures don't stall the others.
- **Auto-ingest dedup is per-(asset, vuln_type).** Variants of the same template against the same host become one row. Re-run with a different template path to widen detection.
- **Evidence paths are stored as strings.** Move the underlying file and the link silently breaks. Keep artifacts inside the matching `recon/<program>/<stamp>/` directory.

---

## Tests

```bash
pytest tests/test_bug_bot.py -v
```

Covers: schema initialization, pipe + key=value parsing, dedup of auto-ingested nuclei output, dashboard formatting, and the AI-fallback path when no brain is supplied.

---

## Related docs

- [SECURITY.md](../SECURITY.md) — secret handling, scope expectations
- [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — where the `/bug` command sits in the request flow
- [.env.example](../.env.example) — `BUGCROWD_API_KEY`, `INFJ_AUTHORIZED_TARGETS`

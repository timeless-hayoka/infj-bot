#!/usr/bin/env python3
"""
Bulk-generate personalized company outreach drafts from AI_COMPANY_OUTREACH.md.

Uses Gemini once per run (reuse one InfjBrain), or `--offline` for instant
deterministic drafts with no API. Writes Markdown + CSV manifest.

Does NOT send email — human review required.

Environment (optional):
  INFJ_OUTREACH_SENDER_NAME
  INFJ_OUTREACH_SENDER_EMAIL
  INFJ_OUTREACH_DEMO_URL
  INFJ_OUTREACH_GITHUB_URL
  INFJ_OUTREACH_VIDEO_URL

Gemini key: API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY, or API_KEY_FILE in .env
(first non-comment line of that file). Override per run with --api-key-file.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DOC = PROJECT_ROOT / "AI_COMPANY_OUTREACH.md"


def _read_api_key_from_path(path: Path) -> str:
    text = path.expanduser().read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    raise ValueError(f"no non-empty key line in {path}")


def infer_tiers(lines: List[str]) -> Dict[int, str]:
    tier_by_line: Dict[int, str] = {}
    current = "unknown"
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("## TIER"):
            m = re.match(r"##\s*(TIER\s*\d+[:\s].*)$", line, re.I)
            current = (m.group(1) if m else line.replace("##", "").strip())[:120]
        if line.startswith("### ") and re.match(r"###\s*\d+\.", line):
            tier_by_line[i] = current
    return tier_by_line


def parse_targets(markdown_text: str, limit: int) -> List[Dict[str, Any]]:
    lines = markdown_text.splitlines()
    tiers = infer_tiers(lines)
    targets: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    hdr = re.compile(r"^###\s*(\d+)\.\s*\*\*(.+?)\*\*")

    def flush():
        nonlocal cur
        if cur and len(cur.get("company", "")) > 0:
            targets.append(cur)

    for idx, raw in enumerate(lines):
        strip = raw.strip()
        mh = hdr.match(strip)
        if mh:
            flush()
            if len(targets) >= limit:
                break
            cur = {
                "num": int(mh.group(1)),
                "company": mh.group(2).strip(),
                "tier": tiers.get(idx, ""),
                "what": "",
                "why_fit": "",
                "target_person": "",
                "pitch_angle": "",
                "contact": "",
                "notes": "",
            }
            continue
        if cur is None:
            continue
        bullet = re.match(r"^-\s*\*\*([^*]+):\*\*\s*(.*)$", strip)
        if bullet:
            key = bullet.group(1).strip().lower()
            val = bullet.group(2).strip()
            mapping = {
                "what": "what",
                "why you fit": "why_fit",
                "target": "target_person",
                "pitch angle": "pitch_angle",
                "contact": "contact",
            }
            field = mapping.get(key.replace(":", ""))
            if field:
                cur[field] = val
            else:
                cur["notes"] = (cur["notes"] + "\n" + strip).strip()

    flush()
    return targets[:limit]


OUTREACH_SYSTEM = """You write short, factual B2B cold outreach email drafts.
Rules:
- Be respectful and specific to the recipient company's product (use provided facts only).
- Do not invent metrics, testimonials, partnerships, awards, or that they personally read emails.
- Do not claim human consciousness or medical/therapeutic ability; cognitive architecture is software design language.
- No manipulation, urgency tricks, or fake mutual connections.
- Keep body under ~180 words unless impossible while keeping structure.
Return ONLY valid JSON with keys: subject, body_plain (use \\n between paragraphs — no Markdown in body).
"""

COMBINED_SYSTEM = OUTREACH_SYSTEM + (
    "\n\n(Stay neutral-professional; do not adopt an INFJ companion persona.)"
)


def first_name_hint(target_person: str) -> str:
    if not target_person or target_person.strip().lower() in ("there", "founder"):
        return "there"
    return target_person.split("(")[0].split(",")[0].strip() or "there"


def render_offline(rec: Dict[str, Any], tpl: str) -> Dict[str, str]:
    """Cheap fills from playbook bullets — uses no AI."""
    sender = os.getenv("INFJ_OUTREACH_SENDER_NAME", "[Your name]")
    email = os.getenv("INFJ_OUTREACH_SENDER_EMAIL", "").strip()
    gh = os.getenv("INFJ_OUTREACH_GITHUB_URL", "[your GitHub URL]").strip()
    demo = os.getenv("INFJ_OUTREACH_DEMO_URL", "[demo or video URL]").strip()
    greet = first_name_hint(rec.get("target_person", ""))

    pitch = (
        rec.get("pitch_angle") or rec.get("why_fit") or "fit notes in outreach doc"
    ).strip()
    tiny_what = (rec.get("what") or "").strip()
    if len(tiny_what) > 220:
        tiny_what = tiny_what[:217] + "…"

    product_bit = tiny_what[:90] + ("…" if len(tiny_what) > 90 else "")
    subject = f"Cognitive architecture + {rec['company']} — {pitch[:62]}"
    if len(subject) > 103:
        subject = subject[:100] + "…"

    if tpl == "b":
        body = (
            f"Hi {greet},\n\n"
            f"I split time between adversarial ML review (HackerOne) and building a hardened "
            f"cognitive stack for assistants (bounded tools, audits, graceful degradation).\n\n"
            f"For {rec['company']}, the overlap is: {pitch}\n\n"
            f"If useful, happy to swap a compact deck or repo walkthrough ({gh}). Short call works too.\n\n"
            f"Best,\n{sender}"
        )
    elif tpl == "c":
        body = (
            f"Hi {greet},\n\n"
            f"I've open-sourced a companion-style cognitive stack (~18k LOC Python) with gated tools, "
            f"persistent memory helpers, and test coverage — may be irrelevant, but aligned with "
            f"your work on long-lived agents ({product_bit}).\n\n"
            f"Angles from my notes: {pitch}\n\n"
            f"Repo: {gh} · Demo/media: {demo}\n\n"
            f"If this is useful for research or OSS cross-pollination, I'd value a quick sanity check "
            f"from your team.\n\n"
            f"Best,\n{sender}"
        )
    else:  # a
        body = (
            f"Hi {greet},\n\n"
            f"I shipped a cognitive-architecture playground in Python — modular agent mind (memory, "
            f"constraints, embodied state metaphors used as scaffolding, regression tests). "
            f"Runs local + cloud hybrid.\n\n"
            f"Why {rec['company']}: {product_bit}. More specifically — {pitch}\n\n"
            f"Happy to grab 10 minutes to show behavior (not slides). Links: repo {gh} · demo/video {demo}.\n\n"
            f"Best,\n{sender}"
        )
    sig = ""
    if email:
        sig = f"\n{email}"
    return {"subject": subject, "body_plain": body + sig}


def _build_user_prompt(rec: Dict[str, Any], template: str) -> str:
    sender = (
        f"Sender name: {os.getenv('INFJ_OUTREACH_SENDER_NAME', '[Your name]')}\n"
        f"Sender email: {os.getenv('INFJ_OUTREACH_SENDER_EMAIL', '')}\n"
        f"Demo URL: {os.getenv('INFJ_OUTREACH_DEMO_URL', '')}\n"
        f"Repo URL: {os.getenv('INFJ_OUTREACH_GITHUB_URL', '')}\n"
        f"Short video URL: {os.getenv('INFJ_OUTREACH_VIDEO_URL', '')}\n"
    )
    tmpl = (
        "Use outreach style Template A from the playbook (consulting/demo offer)."
        if template == "a"
        else (
            "Use Template B tone (security + architecture) sparingly unless notes suggest safety focus."
            if template == "b"
            else "Use Template C (open-source collaboration)."
        )
    )
    ctx = json.dumps(rec, indent=2, ensure_ascii=False)
    return (
        f"{sender}\n"
        f"Template hint: {tmpl}\n\n"
        "Company playbook record:\n"
        f"{ctx}\n\n"
        "Write ONE email. Subject should follow "
        "[Cognitive Architecture] + [their product] + [specific fit]\n"
        "Subject max ~95 chars.\n"
    )


def generate_with_brain(
    brain: Any,
    model_name: str,
    prompt: str,
    timeout_seconds: float,
) -> Dict[str, str]:
    def _call() -> str:
        raw = brain._generate(model_name, COMBINED_SYSTEM, prompt)
        return raw or ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_call)
        try:
            text = fut.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(
                "Gemini did not finish within {:.0f}s — try --offline, check API_KEY / network, "
                "or pass a larger --timeout.".format(timeout_seconds),
            ) from exc

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {
            "subject": "REPLACE — model did not return JSON",
            "body_plain": stripped,
        }
    subject = data.get("subject") or "(no subject)"
    body = data.get("body_plain") or data.get("body") or ""
    return {"subject": subject.strip(), "body_plain": body.strip()}


def slugify(text: str) -> str:
    s = text.lower().replace("/", "-").replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate outreach drafts from AI_COMPANY_OUTREACH.md"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DOC,
        help="Path to AI_COMPANY_OUTREACH.md",
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="How many numbered companies (default 25)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outreach" / "generated",
        help="Output directory root",
    )
    parser.add_argument(
        "--template",
        choices=("a", "b", "c", "mix"),
        default="a",
        help="Template vibe: a=consulting demo, b=security dual, c=OSS collab; mix rotates a/b/c",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse targets only")
    parser.add_argument(
        "--delay", type=float, default=8.0, help="Seconds between API calls"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="No Gemini — fill Template A/B/C from markdown only (instant, always works).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Max seconds per Gemini call (default 120).",
    )
    parser.add_argument(
        "--api-key-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="File whose first non-comment line is the Gemini key (sets API_KEY for this run).",
    )

    args = parser.parse_args()
    if not args.offline and args.api_key_file is not None:
        try:
            os.environ["API_KEY"] = _read_api_key_from_path(args.api_key_file)
        except OSError as exc:
            print("ERROR: cannot read --api-key-file: {}".format(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print("ERROR: {}".format(exc), file=sys.stderr)
            return 2
    text = args.input.read_text(encoding="utf-8")
    targets = parse_targets(text, args.limit)

    if not targets:
        print(f"No targets parsed from {args.input}")
        return 1

    if args.dry_run:
        for t in targets:
            print(f"{t['num']:2d}. {t['company']} — {t.get('tier', '')}")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        print(
            f"[dry-run] Parsed {len(targets)} targets; would write under "
            f"{args.output_dir / stamp}/"
        )
        return 0

    brain = None
    model_name = None
    if not args.offline:
        from config import API_KEY
        from brain import INFJ_PRIMARY_MODEL, InfjBrain

        if not API_KEY:
            print(
                "ERROR: No Gemini API key — set API_KEY (or GEMINI_API_KEY / GOOGLE_API_KEY), "
                "or API_KEY_FILE in .env pointing to a key file, or pass --api-key-file PATH.\n"
                "  Generate drafts without AI:\n"
                "    python scripts/bulk_company_outreach.py --offline --limit 25",
                file=sys.stderr,
            )
            return 2
        print(
            "Bulk outreach — Gemini mode "
            "(timeout {:.0f}s/email, {:.1f}s delay between calls)".format(
                args.timeout, args.delay
            ),
            flush=True,
        )
        print(
            "Starting model client… (first start can sit quietly 15–45s loading SDK / keys)",
            flush=True,
        )
        brain = InfjBrain()
        model_name = INFJ_PRIMARY_MODEL
        print("Ready — generating files.", flush=True)
    else:
        print("Bulk outreach — offline template mode (instant, no Gemini).", flush=True)

    run_dir = args.output_dir.resolve() / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print("Output →", run_dir, flush=True)

    manifest_path = run_dir / "manifest.csv"
    mix_cycle = ["a", "b", "c"]

    def pick_template(idx: int) -> str:
        if args.template in ("a", "b", "c"):
            return args.template
        return mix_cycle[idx % len(mix_cycle)]

    with manifest_path.open("w", newline="", encoding="utf-8") as mf:
        writer = csv.DictWriter(
            mf,
            fieldnames=[
                "num",
                "company",
                "tier",
                "slug",
                "subject_file",
                "status",
                "target_person",
                "contact_note",
            ],
        )
        writer.writeheader()

        for i, rec in enumerate(targets):
            slug = slugify(rec["company"])
            tpl = pick_template(i)
            prompt = _build_user_prompt(rec, tpl)
            fname = f"{rec['num']:02d}_{slug}.md"

            row = {
                "num": rec["num"],
                "company": rec["company"],
                "tier": rec.get("tier", ""),
                "slug": slug,
                "subject_file": fname,
                "status": "pending",
                "target_person": rec.get("target_person", ""),
                "contact_note": rec.get("contact", ""),
            }

            gen_mode = "offline" if args.offline else "gemini"
            print(
                "[{}/{}] {} ({}) → {} …".format(
                    rec["num"],
                    len(targets),
                    gen_mode,
                    tpl,
                    fname,
                ),
                flush=True,
            )
            try:
                if args.offline:
                    out = render_offline(rec, tpl)
                else:
                    assert brain is not None and model_name is not None
                    out = generate_with_brain(brain, model_name, prompt, args.timeout)
                md = (
                    f"---\n"
                    f"company: {rec['company']}\n"
                    f"tier_note: {rec.get('tier', '')}\n"
                    f"target: {rec.get('target_person', '')}\n"
                    f"contact_hint: {rec.get('contact', '')}\n"
                    f"template: {tpl}\n"
                    f"mode: {'offline-template' if args.offline else 'gemini'}\n"
                    f"subject: {out['subject']}\n"
                    "---\n\n"
                    f"{out['body_plain']}\n"
                )
                out_path = run_dir / fname
                out_path.write_text(md, encoding="utf-8")
                row["status"] = "ok"
                print("     wrote {} bytes".format(out_path.stat().st_size), flush=True)
            except Exception as exc:
                row["status"] = f"error: {exc}"
                (run_dir / fname).write_text(
                    f"# ERROR generating {rec['company']}\n\n{exc!s}\n",
                    encoding="utf-8",
                )
                print("     FAILED: {}".format(exc), flush=True)

            writer.writerow(row)
            mf.flush()
            time.sleep(max(0.0, args.delay))

    print(f"\nDone. {len(targets)} drafts under {run_dir}")
    print(f"Manifest: {manifest_path}")
    print("Human review required before sending. No messages were emailed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

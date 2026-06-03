# Hugging Face Space Sync (`scripts/sync_hf.py`)

Operational guide for the incremental Hugging Face Space uploader. Use this whenever you want to push code or asset changes from a local checkout to the public PHI // DRIFT Space without re-uploading the entire tree.

> **Source:** `scripts/sync_hf.py`
> **Target Space:** `crexs/phi-drift` (repo type: `space`) — hard-coded at the top of the script. Edit `REPO_ID` / `REPO_TYPE` if you fork.

---

## 1. Why this exists

`hf upload . .` walks the entire working tree, which on this repo means **50k+ files** (Chroma store, SQLite shards, audit logs, scratch outputs). On large repos it either times out or hits the HF API too hard. `sync_hf.py` does the cheaper thing:

1. Asks git for the `--name-status` diff against a base ref.
2. Filters out anything matching the blocklist (data dirs, secrets, virtualenvs, caches).
3. Uploads only changed / added / renamed files, deletes removed ones.

The net effect is the same as a full sync but typically uploads a handful of files instead of tens of thousands.

---

## 2. Prerequisites

- The Hugging Face CLI (`hf`) installed and authenticated. Verify with `hf whoami`.
- `huggingface_hub` Python package installed (used for deletion via `HfApi.create_commit`).
- `origin/master` (or whichever `--base` you pass) fetched locally — the diff is computed against it.

```bash
pip install huggingface_hub
hf auth login                    # one-time
git fetch origin master           # keep --base ref up to date
```

---

## 3. Common workflows

### Sync the changes on your current branch

```bash
python scripts/sync_hf.py
```

Diffs `HEAD` against `origin/master` and uploads only the modified files.

### Preview without uploading

```bash
python scripts/sync_hf.py --dry-run
```

Prints every file the script *would* upload or delete, prefixed with `UPLOAD (dry-run)` / `DELETE (dry-run)` / `SKIP (blocklist)` / `SKIP (missing)`. Always run this first if you are syncing for the first time on a new branch.

### Diff against a different ref

```bash
python scripts/sync_hf.py --base origin/release-2026-06
python scripts/sync_hf.py --base HEAD~3
```

Any git-resolvable ref works.

### Full reset (re-upload every tracked file)

```bash
python scripts/sync_hf.py --all
```

Uploads `git ls-files` minus the blocklist. Use this when the Space drifted out of sync with master (e.g. after manual edits in the Space UI) or after large refactors. Combine with `--dry-run` first to confirm the file set.

---

## 4. What gets skipped

The blocklist is intentionally aggressive — it errs on the side of **not** publishing things that look like local state, secrets, or generated artefacts.

| Type | Entries |
|---|---|
| **Path components** (any segment matches) | `venv`, `.venv`, `__pycache__`, `.git`, `.pytest_cache`, `.idea`, `.obsidian`, `ABLATION_RESULTS`, `BLKKNIGHT_RECOVERY`, `LIVE_ABLATION_RESULTS`, `.mouse_vanguard`, `.agents`, `outreach`, `chroma_db`, `voices`, `data`, `logs`, `.cache`, `scratch` |
| **Exact file names** | `being.db`, `svalbard_ledger.jsonl` |
| **Suffixes** | `.pyc` |
| **Prefixes** | `.env` (covers `.env`, `.env.local`, `.env.production`, etc.) |

A skipped file is logged as `SKIP (blocklist): <path>` so it is auditable.

> **Adding new blocklist entries:** edit `SKIP_PATHS`, `SKIP_FILES`, `SKIP_SUFFIXES`, or `SKIP_PREFIXES` at the top of the script. Anything under `data/`, `chroma_db/`, or starting with `.env` is already covered — do not duplicate.

---

## 5. How rename / delete are handled

`get_changed_files()` parses `git diff --name-status` codes:

| Git status code | Action |
|---|---|
| `M` (modified), `A` (added) | upload new path |
| `R*` (renamed) | upload new path, delete old path |
| `D` (deleted) | delete path |
| anything else | treated as upload (safe default) |

Deletions go through `huggingface_hub.HfApi.create_commit` with a `CommitOperationDelete` because the `hf` CLI does not expose a clean delete primitive.

---

## 6. Exit codes and error handling

- Returns **0** on success or no-op.
- Returns **1** if any single upload or delete raises:
  - `subprocess.CalledProcessError` for uploads (with `stderr` printed).
  - any other `Exception` for deletes.
- The script aborts on the first failure — it does not "best-effort" the rest of the batch. Re-run after fixing the cause and only the still-pending files will retry.

---

## 7. Pitfalls

- **Don't forget `git fetch`.** Diffing against a stale `origin/master` will either upload too much (rebased commits) or too little (new commits on master you don't have locally).
- **`--all` is destructive in spirit.** It does not delete remote files that no longer exist locally, but it *will* overwrite remote-only edits made via the HF web UI. Use it only when you accept that local state wins.
- **Auth is per-machine.** `hf upload` reads cached credentials from `~/.cache/huggingface/token`. CI jobs need `HF_TOKEN` set in the environment so the CLI picks it up.
- **The script is hard-coded to `crexs/phi-drift`.** If you fork the repo, change `REPO_ID` and `REPO_TYPE` before running — otherwise you'll fail auth against someone else's Space.
- **Skipped-but-tracked files** (e.g. `voices/*` are tracked in git but blocklisted here) will *never* be synced. That's intentional, but be aware when investigating "why is this file out of date on the Space?".

---

## 8. Quick reference

```bash
# Preview a normal incremental sync against master
python scripts/sync_hf.py --dry-run

# Actually push the changes
python scripts/sync_hf.py

# Compare against a different ref (e.g. another branch's tip)
python scripts/sync_hf.py --base origin/some-other-branch

# Nuke-and-pave: re-upload every tracked, non-blocklisted file
python scripts/sync_hf.py --all
```

# Hugging Face Space — Incremental Sync

> Script: `scripts/sync_hf.py`
> Target Space: `crexs/phi-drift` (`repo_type=space`).
> Related: HF Space frontmatter lives in the root [`README.md`](../README.md).

`scripts/sync_hf.py` mirrors only the files that have changed in git to the HF
Space, instead of running `hf upload . .` over the entire working tree. On
large checkouts the naive approach scans tens of thousands of files (notebooks,
caches, vendored data) and either takes minutes or fails outright. The
incremental flow takes seconds for a normal commit.

---

## When to use it

- After merging anything that changes runtime code, templates, static assets,
  `requirements.txt`, or the HF frontmatter at the top of `README.md`.
- After a `git pull` on the deploy host, to push the diff against
  `origin/master` (the default base).
- For a clean re-deploy of every tracked file — use `--all`.

The script is the sanctioned deploy path; do **not** run `hf upload . .` from
the repo root.

---

## Usage

```bash
# Dry run — print what would be uploaded / deleted, change nothing.
python scripts/sync_hf.py --dry-run

# Push the diff between HEAD and origin/master (default).
python scripts/sync_hf.py

# Diff against a different base (e.g. a tag or another branch).
python scripts/sync_hf.py --base v1.4.0

# Full re-upload of every tracked file (skips the blocklist).
python scripts/sync_hf.py --all
```

Exit codes: `0` on success, `1` on the first upload/delete failure (with the
failing path on `stderr`).

---

## What gets sent

The diff is computed with:

```bash
git diff --name-status <base>
```

| Git status     | Action                                                    |
|----------------|-----------------------------------------------------------|
| `A` / `M`      | Upload the new content.                                   |
| `D`            | Delete the path on the Space via `huggingface_hub` API.   |
| `R...` (rename)| Upload the new path **and** delete the old path.          |
| anything else  | Conservatively treated as an upload.                      |

`--all` short-circuits the diff and uploads everything in `git ls-files`
minus the blocklist.

---

## Blocklist (skipped on every code path)

These paths and filenames never leave the local machine, even with `--all`:

**Directories** (any component of the path matches):
`venv`, `.venv`, `__pycache__`, `.git`, `.pytest_cache`, `.idea`,
`.obsidian`, `ABLATION_RESULTS`, `BLKKNIGHT_RECOVERY`,
`LIVE_ABLATION_RESULTS`, `.mouse_vanguard`, `.agents`, `outreach`,
`chroma_db`, `voices`, `data`, `logs`, `.cache`, `scratch`.

**Exact filenames**: `being.db`, `svalbard_ledger.jsonl`.

**Suffixes**: `.pyc`.

**Prefixes**: `.env` (covers `.env`, `.env.local`, `.env.production`, …).

When in doubt, run with `--dry-run` first — the script prints
`SKIP (blocklist): <path>` for anything filtered out.

---

## Prerequisites

1. **Hugging Face CLI authenticated.** Either run `hf auth login` once or
   export `HF_TOKEN` so `hf upload` can authenticate non-interactively.
2. **`huggingface_hub` installed in the active environment.** It is imported
   lazily for the delete path (`HfApi`, `CommitOperationDelete`); pip installs
   it via `requirements.txt`.
3. **Git remote `origin` reachable.** The default `--base origin/master` will
   diff against whatever your local refs show, so `git fetch origin` before a
   sync if you need it to mirror the true remote tip.

---

## Common pitfalls

| Symptom                                                          | Cause / fix                                                                                       |
|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| `No changes to sync.`                                            | `git diff origin/master` is empty. Fetch the remote or pass `--base HEAD~1` to test the script.   |
| `SKIP (missing): <path>`                                         | The file was renamed or removed locally after the diff. Re-run after committing the cleanup.      |
| Upload succeeds but Space build fails on HF                      | HF builds only on commits — each file uploads as its own commit (`sync: update <path>`). Look at the latest build log for the failing path.|
| `ERROR uploading ...: ...`                                       | `hf upload` non-zero exit. The script aborts immediately so you do not leave a half-synced Space. |
| Frontmatter at the top of `README.md` not picked up              | Re-upload `README.md` explicitly with `python scripts/sync_hf.py --all` if HF cached the previous build manifest. |

---

## Why not use `git push` to a HF Space remote?

The Space repo would happily accept a push, but it would carry along everything
in the blocklist — Chroma indexes, vault ledger, the venv if it ever slipped
into git, and the SQLite "state brains" the bot writes at runtime. The
blocklist in this script is the explicit contract about what leaves the host;
git remotes do not enforce it.

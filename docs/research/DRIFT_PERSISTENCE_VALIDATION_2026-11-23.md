# DRIFT persistent-memory validation — 2026-11-23

Status: **manual cross-process recovery PASS; automated regression, exact-ID cross-store readback and authentication tests PENDING**.

## Environment and evidence
- Project: `timeless-hayoka/infj-bot`; local checkout `~/infj-bot` (Kali Linux).
- Active source import: `core/memory.py:15` imports `Event, MemoryManager` from `drift.core.unified_memory`.
- `DriftMemory.save_interaction_sync` constructs `user: ...\nBot: ...` and calls `unified_manager.remember_sync(event, metadata)`.
- `MemoryManager` uses SQLite `episodic` and a persistent Chroma collection `infj_unified_memory_v2`; `remember_sync` generates a UUID, inserts the SQLite row, calls Chroma `collection.add` with that UUID, then returns it.
- Isolated test storage: `/tmp/drift-restart-ceaHMY/memory/chroma`.
- Writer PID: `1394425`; returned UUID: `746278a2-ece5-484e-9d80-c3732b23f99c`.
- Marker: `DRIFT restart validation cobalt-heron-427`.
- Exact saved text: `user: DRIFT restart validation cobalt-heron-427\nBot: This memory must survive a complete process restart.`
- Independent reader PIDs: `1396695`, `1406363`; both returned the exact text and printed `PASS: Cross-process memory recovery`.
- Hugging Face unauthenticated-request warning did not prevent the cached model from loading or the reads from completing.

## What the observations establish
A saved interaction was recovered in separately launched Python processes using the same persistent storage path. The two observed reader executions demonstrate repeatable retrieval of the original content. These are user-supplied terminal outputs, not independently captured CI artifacts.

## Limitations / unverified gates
1. The reader's `search()` returns document and metadata, not UUID. Exact returned UUID equality has **not** been tested.
2. SQLite and Chroma readback by the same UUID in a new process has **not** been demonstrated.
3. Writer exit code and process termination ordering were not captured in a machine-readable test artifact.
4. An automated `pytest` regression test has not been demonstrated running or passing.
5. Authentication-before-retrieval and full application/service restart remain untested.
6. `remember_sync` commits the SQLite insert before Chroma `add`. If the latter fails, a partial write may remain. The claimed cross-store atomicity needs failure-injection validation; this is a code-review concern, not a reproduced failure.

## Proposed reproducible validation
Use a fresh temporary directory; spawn a writer subprocess through the real `DriftMemory` API; capture UUID and successful exit; then spawn a reader subprocess to check SQLite `episodic` by UUID and Chroma `collection.get(ids=[uuid])` for identical content, metadata, and cardinality. Assert distinct PIDs and failure on missing or inconsistent data. Do not touch the user's real vault. Separately inject Chroma write failure to characterize rollback behavior, and test the service's authentication boundary.

## Evidence provenance
The writer and reader logs and source excerpts were provided interactively by the repository owner on 2026-11-23. No CI run or verified GitHub commit is claimed for the experiment prior to this report.

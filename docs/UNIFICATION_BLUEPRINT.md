# UNIFICATION BLUEPRINT: PROJECT DRIFT
**Target:** Consolidate `drift`, `DRIFT`, and `hive_mind` into a single, cohesive 5-layer organism.
**Date Initiated:** May 2026

## 1. The Executive Mandate
We are moving from three isolated, overlapping codebases into a single robust product. 
- `drift` owns the Interface and Tools. It is the destination shell.
- `DRIFT` (`/core/*`) owns canonical Cognition. It is the subconscious.
- `hive_mind` owns Coordination. It is the distributed frontal lobe.

## 2. The 5-Layer Target Architecture
1. **Interface Layer:** cli.py, api.py, web_app.py, mcp_server.py
2. **Cognition Layer:** DRIFT core (being, embodiment, homeostasis, global workspace)
3. **Coordination Layer:** Hive threads, consensus, multi-role review, planning
4. **Memory Layer:** Unified hierarchy (Working, Episodic, Semantic/ChromaDB, Shared Hive)
5. **Tool / Safety Layer:** One permission model, one audit log, one rollback story

## 3. Module Ownership & Cut Lines
| Module / Capability | Target Owner | Action Plan |
| :--- | :--- | :--- |
| **Interface (CLI/API/Web)** | `drift` | Keep in place. Stabilize public routes. |
| **User Commands** | `drift` | Keep in place. Route internal calls to adapters. |
| **Cognition (Being/Emotion)** | `DRIFT` | Import to `drift`. Wrap duplicate modules as facades, then retire. |
| **Embodiment & Homeostasis** | `DRIFT` | Import to `drift` as canonical source of truth. |
| **Coordination (Hive/DCP)**| `hive_mind`| Keep `hive_mind/` inside `drift`. Wire to planning. |
| **Memory (Semantic/Episodic)**| **UNIFIED** | Merge `drift` memory + `DRIFT` memory into one ChromaDB/SQLite spine. |
| **Tools (Nuclei/ffuf etc.)** | **UNIFIED** | Create one unified tool registry in `drift`. |

## 4. The Surgical Phases
* **Phase 0 (Freeze):** `drift` declared destination. No simultaneous feature development.
* **Phase 1 (Compatibility Spine):** Introduce adapter modules. No immediate rewrites.
* **Phase 2 (Unify State):** Choose ONE config contract and ONE data root policy. Prevent dual-write database corruption.
* **Phase 3 (Pick Canonical):** `drift/core/` overrides duplicate `drift` cognition modules.
* **Phase 4 (Unify Memory):** Merge ChromaDB and SQLite paths into a single hierarchical memory system.
* **Phase 5 (First-Class Hive):** Route all high-risk or planning actions through Propose -> Critique -> Integrate -> Resolve.
* **Phase 6 (Unify Tools/Safety):** One audit log, one rollback system.
* **Phase 7 (Consolidate API):** Expose all 5 layers through `drift/api.py`.
* **Phase 8 (Retire):** Delete the shadow copies/facades after runtime test parity.

## 5. Absolute Safety Rules
1. **No destructive data migration without snapshots.**
2. **Keep the old module behind an adapter until the new path passes all tests.**
3. **No simultaneous replacement of Memory, Brain, and Tools in a single phase.**
4. **Verify every phase with:** Unit tests, 1 CLI flow, 1 API flow, 1 Hive proposal flow, 1 Memory retrieval flow.
# Web App — Per-Session Resource Isolation

`interfaces/web_app.py` runs the DRIFT dashboard on a Gevent + Flask‑SocketIO server (default port `7860`). As of the multi-user pass, the web app no longer shares one global brain / memory / state across visitors — each browser gets an **isolated `SessionResources` bundle**, persisted to its own folder under `<INFJ_DATA_DIR>/sessions/<session_id>/`.

This page documents:

- the `SessionResources` lifecycle
- how a request is routed to a session
- the background greenlets that run alongside Flask
- trial / sandbox mode
- operational knobs (retention, pruning, file layout)

For the singleton CLI flow, see [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md). For the Fly‑By‑Wire CLI cycle that wraps the LLM call, see [FLY_BY_WIRE.md](FLY_BY_WIRE.md).

---

## 1. SessionResources — what gets isolated

Each visitor's session_id is mapped to a `SessionResources` instance that owns its own copy of these subsystems:

| Subsystem | Class | Persisted to |
|-----------|-------|--------------|
| Bot state | `BotState` | in-memory + `preferences.db`, `scheduler.db` |
| Preferences | `PreferenceStore(db_path=...)` | `preferences.db` |
| Scheduler | `TaskScheduler(db_path=...)` | `scheduler.db` |
| Long-term memory | `DriftMemory(persist_directory=...)` | `memory/` (Chroma) |
| Document store | `DocumentStore(persist_directory=...)` | `chroma_db/` |
| Goals / reminders | `GoalsDB(db_path=...)` | `goals.db` |
| Chat history | `ChatHistory(path=...)` | `history.jsonl` |
| Self-eval | `SelfEvaluator(db_path=...)` | `self_eval.db` |
| LLM disk cache | `DiskGenCache(path=...)` | `drift_gen_cache.sqlite3` |
| Brain | `DriftBrain(evaluator=..., disk_cache=...)` | (uses injected stores) |

All files live in:

```
<INFJ_DATA_DIR>/
├── global_session/       # default bucket when no session_id is supplied
└── sessions/
    └── <session_id>/     # one folder per visitor
        ├── preferences.db
        ├── scheduler.db
        ├── memory/
        ├── chroma_db/
        ├── goals.db
        ├── history.jsonl
        ├── self_eval.db
        └── drift_gen_cache.sqlite3
```

> **Not yet per-session.** The Global Workspace (`get_workspace()`), Being, Homeostasis, Shadow, DII tracker, and the Cognitive Orchestrator are still **process-wide singletons** at the moment. They are exposed via the observatory stream and ticked by the background loop (see §4). Plan accordingly: shadow depth, mood, and workspace contents are shared across all browsers connected to the same process.

### Dependency injection contract

The session-aware constructors that were added to support this:

- `DriftBrain(evaluator=None, disk_cache=None)` — pass a per-session `SelfEvaluator` and `DiskGenCache` to keep critic scores and generation caches separated; falls back to defaults when called without arguments (CLI / tests).
- `GoalsDB(db_path=None)` — defaults to the global `goals.db` under `DATA_DIR` when no path is provided; creates parent directories on construction.
- `BotState(prefs=..., scheduler=...)` — `commands.py` already accepted these; the web app now always passes per-session instances.

If you add a new subsystem that holds writable state, **plumb a `db_path=` / `persist_directory=` parameter through and instantiate it inside `SessionResources.__init__`** instead of reaching for a global singleton.

---

## 2. Resolving a session_id per request

`get_request_session_id()` extracts the id with this precedence:

1. `session_id` field in the JSON body (e.g. injected by `INDEX_HTML` JS into every `post(...)` call).
2. `drift_session_id` cookie (set on first visit to `/` by `index()` and on `/trial`).
3. Fall back to the literal string `"global"` — all sessionless callers (curl, dev probes) share one bucket.

```python
session_id = get_request_session_id()
session_res = get_session(session_id)   # creates if missing, refreshes last_accessed
```

Every JSON route in `web_app.py` goes through this pair, including the Ollama-compatible `/api/chat` shape and `/v1/chat/completions` (OpenAI-compatible). Pass `{"session_id": "..."}` explicitly when you want isolation from a non-browser client.

---

## 3. Lifecycle and pruning

`prune_and_cleanup_sessions()` runs as a Gevent greenlet, woken every **300 s**:

1. **In-memory eviction.** Any session whose `last_accessed` is older than **1800 s (30 min)** is removed from the `sessions` dict and its `SessionResources.close()` is called to release the disk cache file descriptor. The `"global"` bucket is never evicted.
2. **On-disk cleanup.** Any folder under `sessions/` whose most-recently modified file is older than **7 days** is deleted with `shutil.rmtree(..., ignore_errors=True)`.

`SessionResources.close()` currently only closes `DriftBrain._disk_cache`. Chroma collections, SQLite handles, and the history file rely on Python garbage collection. If you add a long-lived resource that needs explicit teardown, extend `close()`.

---

## 4. Background greenlets

Started from `main()` in `web_app.py`:

| Greenlet | Period | Purpose |
|----------|--------|---------|
| `background_cognitive_loop` | 4 s | Drifts heartbeat (`60–100 bpm`) and breath depth (`0.3–0.95`) with small random walks; flips `breath_phase` ~20 % of ticks; calls `shadow.background_tick(being=...)` and `homeostasis.background_cycle(being=...)` when those hooks exist; runs `dii_tracker.compute(...)` for the observatory feed. Operates on the **singleton** subsystems, not per-session copies. |
| `prune_and_cleanup_sessions` | 300 s | See §3. |
| `broadcast_observatory_state` | dynamic (`broadcast_interval`, default 0.35 s) | Computes `cognitive_orchestrator.get_delta_state()` and emits an `observatory_delta` Socket.IO event. Skips emission when only the `timestamp` key changed. Also accumulates `total_bytes_raw` / `total_bytes_compressed` counters surfaced under `network_stats`. |

The observatory broadcaster is started inside the module body via a daemon `threading.Thread` (because it predates the gevent spawns). The two greenlets are spawned inside `main()`, so they only run when the file is invoked as a script — **not** when imported in tests or via `from infj_bot.interfaces.web_app import app`.

### Auto-throttle

`broadcast_interval` is mutated by two Socket.IO handlers:

- `latency_ping` (echo for client-side RTT measurement).
- `auto_adjust_rate` — if the reported average latency > 250 ms, `broadcast_interval` slows toward `1.5 s`; if < 100 ms, it speeds up toward `0.2 s`.

---

## 5. Trial / sandbox sessions (`/trial`)

`GET /trial` mints a fresh `session_id`, records `trial_sessions[session_id] = time.time()`, and serves the same dashboard HTML with the id baked in. `is_trial_active()` enforces a **30-minute hard cap**:

```python
if session_id and session_id in trial_sessions:
    if not is_trial_active(session_id):
        return jsonify({"error": "Trial session expired..."}), 403
```

The check fires only inside `/api/chat`. Other routes (commands, growth, etc.) currently do **not** enforce the trial timer. The disk folder for an expired trial is eventually swept by the 7-day pruner; there is no targeted "burn this trial folder now" path.

---

## 6. Routes that take a session

| Route | Method | Notes |
|-------|--------|-------|
| `/` | GET | Issues `drift_session_id` cookie on first hit; injects `const DRIFT_SESSION_ID` into the page so XHR calls forward it. |
| `/trial` | GET | Same shape; 30-min cookie, registers trial. |
| `/api/chat` | POST | Two payload shapes — `{"message": "..."}` (DRIFT UI) and `{"messages": [...]}` (Ollama-compatible / Reins). Enforces trial timer. |
| `/v1/chat/completions` | POST/OPTIONS | OpenAI-compatible wrapper around `chat_reply`. |
| `/api/command` | POST | Forwards to `core.commands.handle_command` with the session's state, brain, memory, history, goals, docs. |
| `/api/growth` | GET | Returns `growth_profile(memory, turns)` for the session. |
| `/api/email` | POST | Per-session command path. |
| `/api/tags`, `/observatory`, `/glyph`, `/phi-glyph` | GET | Process-global; do not use the session. |

`chat_reply(message, session_res)` is the single inference path: it calls `build_chat_prompt`, then `session_res.brain.agent_turn`, then `session_res.brain.evaluate_last`, then writes to `session_res.memory` and `session_res.history` with `state.turns += 1`.

---

## 7. Operational checklist

- **Disk growth.** Each new visitor creates a Chroma index. Watch `<INFJ_DATA_DIR>/sessions/` if you expose the dashboard publicly.
- **Process restart.** In-memory `sessions` and `trial_sessions` are not persisted; on restart only the disk folders survive. The next request for an existing `drift_session_id` cookie rehydrates the folder by re-instantiating `SessionResources` against the existing files.
- **Reloader.** `socketio.run(..., use_reloader=False)` — the Flask reloader is intentionally disabled to keep the gevent monkey patch and the spawned greenlets from being torn down mid-conversation.
- **Port.** `PORT` env var, default `7860` (matches the Hugging Face Space config in the top-level `README.md` frontmatter).
- **Singleton state caveat.** If two browsers chat at once, their shadow/being/homeostasis updates collide because those modules are still process-wide. Treat the per-session isolation as covering memory, goals, history, prefs, and self-eval — not the cognitive subsystems.

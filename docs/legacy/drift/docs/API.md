# DRIFT HTTP API

Your model returns text. **DRIFT returns state** you can log, gate, and fold into the next turn: mood, Φ, what won the attentional lottery, how the drives look, and what memory surfaced. This page is the **contract cheat sheet** for integrators. For field-accurate schemas, open the interactive **OpenAPI UI** at `/docs` on a running server—those definitions win if this file lags.

**Base URL:** `http://127.0.0.1:8080/v1` (match your host; Docker and `.env` usually use port `8080`).

**Authentication:** When `DRIFT_API_KEY` is set in the environment, send it as header `X-API-Key`. If that variable is **empty**, the API stays open for local demos—fine on your laptop, not on the public internet.

---

## When to use which endpoint

| You want to… | Call | Reason |
|----------------|------|--------|
| Run a full cognitive “tick”: input in, workspace + Φ + drives (+ intuition when available) out | `POST /v1/cycle` | One shot for orchestrators wrapping DRIFT around your LLM |
| Read subjective state **without** running a cycle (dashboards, guards) | `GET /v1/being` | Cheaper than `/cycle` when you only need “how is it doing?” |
| Apply something that happened in the world—user message, gratitude, friction—into being state | `POST /v1/being/interact` | Between cycles; use when the environment changed |
| Track integration / “how awake is this run?” for telemetry or safety heuristics | `GET /v1/being/phi` | Φ is your coarse integration gauge |
| Store text worth recalling (preferences, lessons, tagged facts) | `POST /v1/memory/save` | Writes into semantic memory |
| Retrieve by meaning, not only by thread ID | `POST /v1/memory/query` | Hybrid-ranked recall over Chroma |
| Inspect survival needs before you throttle, escalate, or hand off to a human | `GET /v1/homeostasis` | Ops: see deficits before you act |
| Apply a deliberate regulatory nudge once you already chose *what* to fix | `POST /v1/homeostasis/regulate` | Avoid spamming; pair with policy in your app |
| Prove the process is alive after deploy or chaos | `GET /v1/health` | Plugins registered, uptime, “is the brain mounted?” |

**Rule of thumb:** If you wire only one route on day one, make it **`POST /v1/cycle`**. Add the others when you separate **reads**, **memory**, or **operations**.

---

## Authentication

```bash
curl -H "X-API-Key: drift_your_key_here" "http://127.0.0.1:8080/v1/being?agent_id=agent-1"
```

---

## Endpoints

Shapes below match the **Pydantic models** in `drift/api/models.py` and the handlers in `drift/api/routes/`. Every agent id gets its own directory: `agents/<agent_id>/` under the process working tree (SQLite + Chroma).

### POST /v1/cycle

Runs `CognitiveArchitecture` + global workspace + homeostasis signals + Φ + optional intuition snapshot.

**Request body** (`CycleRequest`):

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `agent_id` | string | yes | Stable id for on-disk state |
| `input` | string or omitted | no | When present, evolves being and is written to memory |
| `context` | object | no | Passed into `CycleContext` (opaque dict) |

```json
{
  "agent_id": "booking-agent-1",
  "input": "User wants a flight to Tokyo tomorrow",
  "context": { "deadline_pressure": 0.8 }
}
```

**Response** (`CycleResponse`): `being` (flat dict), `workspace` (broadcast list), `phi`, optional `memory_id`, optional `intuition`, optional `homeostasis`.

```json
{
  "being": {
    "mood": "focused",
    "energy": 0.651,
    "curiosity": 0.5,
    "attachment": 0.3,
    "volition": 0.7,
    "self_awareness": 0.6,
    "intensity": 0.55,
    "focus": "planning",
    "last_thought": "…",
    "total_interactions": 12,
    "insights_formed": 2,
    "dreams_had": 0
  },
  "workspace": [
    {
      "source": "predictor",
      "content": "trimmed text…",
      "salience": 0.82,
      "emotion_tag": "curiosity",
      "intensity": 0.4
    }
  ],
  "phi": 47.2,
  "memory_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "intuition": {
    "felt_quality": "calm",
    "intensity": 0.4,
    "confidence": 0.6
  },
  "homeostasis": {
    "energy": { "current": 0.62, "setpoint": 0.6 },
    "coherence": { "current": 0.7, "setpoint": 0.6 }
  }
}
```

`intuition` is omitted when the intuition engine cannot load. `homeostasis` entries include **all** regulator needs with `current` + `setpoint` only (status strings appear on `/homeostasis`).

---

### GET /v1/being

**Query:** `agent_id` (required).  

**Response** (`BeingStateResponse`): no `agent_id` field — cross-reference your query param.

```json
{
  "mood": "curious",
  "energy": 0.7,
  "curiosity": 0.6,
  "attachment": 0.3,
  "volition": 0.5,
  "self_awareness": 0.4,
  "intensity": 0.5,
  "focus": "planning",
  "last_thought": "I wonder what the user needs today",
  "total_interactions": 42,
  "insights_formed": 7,
  "dreams_had": 0
}
```

---

### POST /v1/being/interact

Same **response model** as `POST /v1/cycle` (`CycleResponse`). Requires non-empty `input`. Optional `emotion_hint` is a **string label** (stored as a soft emotion tag on the intuition pass).

```json
{
  "agent_id": "agent-1",
  "input": "That was really helpful, thank you",
  "emotion_hint": "gratitude"
}
```

`intuition` is often `null` here unless the intuition engine succeeds during the cycle.

---

### GET /v1/being/phi

**Query:** `agent_id` (required).  

**Response** (`PhiResponse`):

```json
{
  "agent_id": "agent-1",
  "phi": 42.3,
  "qualia_space": {
    "valence": 0.5,
    "arousal": 0.6,
    "complexity": 0.7,
    "unity": 0.8,
    "boundaries": 0.4,
    "depth": 0.6,
    "luminosity": 0.7
  }
}
```

**Heuristic read (not a medical or legal claim):** higher Φ with stable qualia axes usually means tighter integration in this implementation; treat it as **telemetry** you correlate with your own evals.

---

### POST /v1/memory/save

**Request** (`MemorySaveRequest`): `agent_id`, `content`, optional `category` (default `general`), optional `importance` ∈ [0, 1].

```json
{
  "agent_id": "agent-1",
  "content": "User prefers direct answers over elaborate explanations",
  "category": "insight",
  "importance": 0.8
}
```

**Response** (plain dict): acknowledgement UUID + status. *(The UUID is generated server-side; Chroma may assign its own internal id.)*

```json
{
  "memory_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "saved"
}
```

---

### POST /v1/memory/query

**Request** (`MemoryQueryRequest`): `agent_id`, `query`, optional `n_results` (1–50, default 5). No filter object is exposed yet.

```json
{
  "agent_id": "agent-1",
  "query": "What does the user prefer?",
  "n_results": 5
}
```

**Response:**

```json
{
  "agent_id": "agent-1",
  "results": [
    {
      "document": "user: hello\nBot: hi there",
      "metadata": { "type": "interaction", "timestamp": "…" }
    }
  ]
}
```

Documents and metadata mirror Chroma payloads after hybrid reranking inside `DriftMemory.retrieve_context`.

---

### GET /v1/homeostasis

**Query:** `agent_id` (required). Uses the same `HomeostaticRegulator` database as the other routes for that id.

**Response** (`HomeostasisResponse`):

```json
{
  "needs": {
    "energy": {
      "current": 0.65,
      "setpoint": 0.6,
      "critical_low": 0.15,
      "status": "optimal"
    }
  },
  "crisis_mode": false,
  "allostatic_load": 0.12,
  "last_regulation": "[connection] reach out"
}
```

`status` is `optimal`, `deficit`, or `critical` derived from live need trajectories.

---

### POST /v1/homeostasis/regulate

**Request** (`HomeostasisRegulateRequest`):

```json
{ "agent_id": "agent-1" }
```

Invokes `HomeostaticRegulator.regulate` once after refreshing module signals. **Response** matches `GET /v1/homeostasis` (another `HomeostasisResponse`). The need/regulator target is chosen inside the core (`REGULATION_STRATEGIES`), not via this JSON body.

---

### GET /v1/health

**Response** (`HealthResponse`):

```json
{
  "status": "ok",
  "plugins": ["temporal", "values", "…"],
  "uptime": 3600.42
}
```

`plugins` is the string list returned by `CognitiveArchitecture.list_plugins()` at call time.

---

## Error Codes

FastAPI returns standard JSON `{"detail": ...}` bodies. Typical cases:

| Status | When |
|--------|------|
| 400 | Malformed JSON or bad query params |
| 401 | Missing/wrong `X-API-Key` while `DRIFT_API_KEY` is configured |
| 422 | Request body fails Pydantic validation |
| 500 | Uncaught exception inside a cognitive route (see server logs) |

There is **no** dedicated `404` for unknown `agent_id` today—new ids lazily create storage.

---

## Rate limits

The self-hosted server does **not** enforce request quotas. The table below describes a **future hosted/SaaS posture**, not the OSS binary.

| Tier | Requests/minute | Cycles/month |
|------|-----------------|--------------|
| Developer (self-hosted) | Unlimited | Unlimited |
| Growth (SaaS) | 1,000 | 1,000,000 |
| Enterprise | Custom | Custom |

---

## SDK

Implementation: [`drift/sdk/client.py`](../drift/sdk/client.py). It mirrors the `/v1/...` paths above and sends `X-API-Key`.

```python
from drift import DriftClient

client = DriftClient(api_key="your_key_or_empty_string_locally", base_url="http://127.0.0.1:8080")
result = client.cycle(agent_id="my-agent", input="Hello")
print(result["phi"])
print(client.health())
```

`DriftClient.regulate_homeostasis(agent_id)` maps to `POST /v1/homeostasis/regulate`.

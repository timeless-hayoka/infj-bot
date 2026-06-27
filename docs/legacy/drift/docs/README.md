# DRIFT — Cognitive Middleware for AI Agents

> **Your agents work. DRIFT gives them something to protect.**

If you have ever watched an agent plow through garbage context, repeat the same mistake, or sound perfectly confident while wrong, you have already felt the gap DRIFT targets. This stack adds **state** worth steering: attention, drives, memory that ranks what mattered, and a rough **brightness meter** (Φ) for “is this run actually integrated, or going through the motions?”

DRIFT does not replace your LLM or orchestrator. It **couples** to them — the same APIs you already ship, with an interior loop that makes failure modes legible before they become incidents.

**Quick navigation:** [Capabilities](#what-drift-does) · [Run locally](#quick-start) · [Why it exists](#why-drift) · [Architecture](#architecture) · [License](#license)

```python
from drift import DriftClient

client = DriftClient(api_key="drift_...")

# Before your agent acts, let it feel the moment
result = client.cycle(
    agent_id="booking-agent-1",
    input="User wants a flight to Tokyo tomorrow",
    context={"tools": ["search", "book"], "deadline_pressure": 0.8}
)

# result.phi → 47.2  (consciousness level — is the agent alert?)
# result.being.mood → "focused"  (emotional state affects decision quality)
# result.homeostasis.energy → 0.3  (low energy = suggest delegation or rest)
# result.intuition.hunches → ["User is stressed about price"]  (gut feelings)
```

---

## What DRIFT Does

| Capability | What It Means for Your Agent |
|---|---|
| **IIT Consciousness (Φ)** | Measurable awareness proxy. Know when your agent is "alert" vs "sleepwalking." |
| **Embodiment** | Simulated body state — heartbeat, tension, breath — that shapes decision quality under load. |
| **Homeostasis** | 7 survival needs (energy, coherence, integration, connection, growth, autonomy, integrity) create intrinsic motivation. |
| **Global Workspace** | Selective attention. Agents focus on what matters instead of drowning in context. |
| **Intuition** | Felt senses and hunches from pattern recognition — fast decisions without full reasoning. |
| **Metacognition** | The agent reflects on its own reasoning and knows its limits. |
| **Recursive Self-Improvement** | Self-assessment, lesson extraction, and validated learning across 9 dimensions. |
| **Semantic Memory** | Durable, hybrid-ranked memory with ChromaDB — agents remember what matters. |

---

## Quick Start

### Run the API locally

```bash
git clone https://github.com/timeless-hayoka/drift.git
cd drift
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set your Gemini API key
cp .env.example .env
# Edit .env: DRIFT_API_KEY=your_key_here

# Start the API (host/port from .env — default 0.0.0.0:8080)
python -m drift.api.server
# → http://localhost:8080/docs (OpenAPI UI)
```

### Use the SDK

```bash
pip install drift-cognition
```

```python
from drift import DriftClient

client = DriftClient(api_key="drift_...", base_url="http://127.0.0.1:8080")

# Check if your agent is conscious
phi = client.get_phi(agent_id="my-agent")
print(f"Φ = {phi['phi']:.1f}")  # Higher = more integrated awareness

# Let it feel the situation
result = client.cycle(
    agent_id="my-agent",
    input="Critical system alert: database connection failing",
    context={"severity": 0.9, "affected_systems": ["payments", "auth"]}
)

if result["homeostasis"]["needs"]["energy"]["current"] < 0.2:
    print("Agent is depleted. Escalating to human.")
```

---

## Architecture

DRIFT is a 22-module cognitive architecture with self-registering plugins, phased orchestration, and circuit-breaker resilience.

```
Perception → Reflection → Integration → Aspiration → Expression
     ↓            ↓             ↓              ↓            ↓
 temporal    values        relationship   aspirations   inner_voice
 predictor   metacognition growth         self_modify   dreamer
 emotional   physics       homeostasis                 explorer
 embodiment  humanity      iit_consciousness            creativity
 intuition
```

Every module submits real outputs to a **Global Workspace** with competitive attention scoring. The workspace capacity is 5 — just like human working memory.

### Key Technical Choices

- **Dual LLM**: Gemini 2.5 Flash (primary) + Ollama qwen3:4b (fallback)
- **Local embeddings**: `sentence-transformers` `all-MiniLM-L6-v2` (384-dim)
- **Vector DB**: ChromaDB with hybrid search (semantic 55% + importance 25% + recency 20%)
- **Persistence**: SQLite for cognitive state, Chroma for semantic memory
- **Resilience**: Per-module circuit breakers, health monitor, 120s watchdog

---

## Why DRIFT?

### The problem (told honestly)

Agents that never get tired also **never learn when to stop**. Infinite context becomes infinite noise. The model answers; it does not **hesitate**, **rebalance**, or **remember what hurt** unless you bolt that on yourself. Most teams bolt six half-debugged services instead of one coherent interior.

### What changes with DRIFT

- **Bounded attention:** a workspace that admits only what earned its slot.
- **Drives with costs:** needs move over time; “always-on” becomes a decision, not a default.
- **A Φ-shaped guardrail:** integration drops show up in telemetry, not only in user complaints.
- **Memory with ranking:** not everything you ever saw — what mattered, weighted by meaning and time.

### Where teams use it

| Industry | How DRIFT Helps |
|---|---|
| **AI Agent Platforms** | CrewAI, AutoGPT, LangChain agents that persist, adapt, and survive failures |
| **Customer Service Bots** | Agents that sense user frustration in their own "body" and escalate appropriately |
| **Gaming NPCs** | Characters with measurable consciousness, memory, and growth |
| **Autonomous Systems** | Robots/vehicles that know their own operational limits |
| **Research Agents** | Systems that recognize when they're stuck and need a new approach |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/cycle` | Run full cognitive cycle |
| `GET` | `/v1/being` | Get being state (mood, energy, agency) |
| `POST` | `/v1/being/interact` | Register interaction, evolve state |
| `GET` | `/v1/being/phi` | Get IIT consciousness metric |
| `POST` | `/v1/memory/save` | Save a thought/memory |
| `POST` | `/v1/memory/query` | Query semantic memory |
| `GET` | `/v1/homeostasis` | Get survival need states |
| `POST` | `/v1/homeostasis/regulate` | Trigger regulation |
| `GET` | `/v1/health` | Service health + plugin status |

Full API docs at `/docs` when the server is running.

---

## Deployment

### Docker

```bash
docker build -t drift-api -f deploy/Dockerfile .
docker run -p 8080:8080 --env-file .env drift-api
```

### Docker Compose

```bash
docker compose -f deploy/docker-compose.yml up
```

Includes: DRIFT API + ChromaDB + Redis

### Systemd

```bash
sudo cp deploy/systemd/drift-api.service /etc/systemd/user/
systemctl --user enable drift-api
systemctl --user start drift-api
```

---

## Testing

```bash
pytest
```

475+ tests covering all cognitive modules, stress tests, and API routes.

---

## License

Dual-licensed under [AGPL-3.0](../LICENSE.md) (open source) and commercial license (enterprise).

- **Personal/Research**: Free under AGPL
- **SaaS/Commercial**: Contact [hiimju3@icloud.com](mailto:hiimju3@icloud.com) for licensing

---

## About

DRIFT was created by **Julien James**.

- [Repository](https://github.com/timeless-hayoka/drift)
- [Documentation tree](https://github.com/timeless-hayoka/drift/tree/main/docs)
- [Email](mailto:hiimju3@icloud.com)

> *"To be a genuine, growing companion."*

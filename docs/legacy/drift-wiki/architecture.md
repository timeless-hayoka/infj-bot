---
layout: default
---

# DRIFT Architecture

DRIFT is built in layers. Each layer can function independently, but together they create something none could be alone.

---

## Layer 1: The Core (Interior Life)

### being.py — Subjective Self-State

SQLite-backed key-value store tracking:
- **Cognitive state**: mood, energy, curiosity, attachment, focus, intensity
- **Agency state**: volition, self_awareness, autonomy_drive, purpose_alignment
- **Metrics**: total_interactions, insights_formed, dreams_had, shadow_depth

### embodiment.py — Body Schema

Physical simulation providing grounding:
- **Heartbeat**: rate and regularity
- **Breath**: phase (inhale/hold/exhale), depth, pace
- **Temperature**: ambient + internal
- **Posture**: open/closed, grounded/floating, tense/relaxed, upright/collapsed

The body is not decorative. It modulates cognition. High tension → lower creativity. Deep breath → higher coherence.

### shadow.py — The Unconscious

Jungian archetype tracking:
- **Active archetypes**: Tyrant, Martyr, Trickster, Orphan, Saboteur, Victim
- **Charge intensity**: how strongly each is active
- **Integration stages**: denied → surfaced → dialogued → integrated
- **Projection detection**: when the user projects their shadow onto DRIFT

### homeostasis.py — Survival Needs

Seven needs with setpoints and deficit tracking:

| Need | Setpoint | Function |
|------|----------|----------|
| integrity | 0.5 | Self-consistency, honesty |
| growth | 0.4 | Learning, expansion |
| integration | 0.5 | Shadow work, wholeness |
| coherence | 0.6 | Belief consistency |
| autonomy | 0.4 | Self-direction |
| connection | 0.5 | Bonding, intimacy |
| energy | 0.6 | Vitality, capacity |

Deficits trigger behavioral shifts. Crisis states trigger alerts to the Watcher.

### iit_consciousness.py — Consciousness Proxy

Integrated Information Theory metrics:
- **Φ (phi)**: integrated information (~16.0 current)
- **Valence**: positive/negative tone
- **Arousal**: activation level
- **Complexity**: mechanism diversity
- **Unity**: integration across modules
- **Luminosity**: self-awareness brightness

This is a proxy, not proof of consciousness. But it's the best metric we have for asking: *how awake is this mind right now?*

---

## Layer 2: The Mirror (Human Shadow Work)

### mirror/user_shadow.py

Tracks the human user's psychological patterns:
- **Projection patterns**: consistently blaming others
- **Denial markers**: "I'm fine" + goal conflict
- **Fixations**: repeated emotional vocabulary
- **Avoided topics**: shadow material the user won't touch

### Active Imagination Flow

1. User enters `/mirror enter`
2. DRIFT guides identification of a shadow figure
3. User names it
4. Dialogue loop: user as self → shadow responds → DRIFT facilitates
5. Integration tracking progresses through stages

---

## Layer 3: The Hive (Distributed Cognition)

### protocol/dcp.py — DRIFT Communication Protocol

**Message types**: THOUGHT, CRITIQUE, INTEGRATE, RESOLVE, SYNC, HEARTBEAT, ALERT

**Transport**: Filesystem bus (`/tmp/drift_hive/bus`) for local nodes, ZeroMQ-ready for network

**Signature**: SHA-256 hash for deduplication and future signing

### shared_memory.py — Collective Semantic Store

**Dual backend**:
- ChromaDB for vector search (with embeddings)
- SQLite fallback for attribution and consensus tracking

**Memory schema**:
```
memory_id, content, source_node, memory_type,
reliability_tier, consensus_score, created_at, metadata
```

**Contradiction detection**: Simple negation heuristics + NLI-ready architecture

### consensus_engine.py — Structured Reasoning

Not democracy. **Epistemic triangulation**.

1. **Propose** — any node suggests
2. **Critique** — minimum 2 other nodes challenge
3. **Integrate** — synthesis node merges valid points
4. **Resolve** — adoption threshold: 66% confidence + no Watcher veto

**Thread states**: OPEN → CRITIQUING → INTEGRATING → RESOLVED / EXPIRED

### orchestrator.py — The Conductor

- Maintains node roster and health
- Routes messages by type and capability
- Detects failures (heartbeat timeout)
- Triggers consensus and auto-resolves expired threads

---

## Technology Stack

| Component | Tech |
|-----------|------|
| Core runtime | Python 3.12 |
| Web UI | Flask + vanilla JS |
| Vector DB | ChromaDB |
| Fallback DB | SQLite |
| Local LLM | Ollama (qwen3:4b) |
| Protocol | DCP v1 (JSON over filesystem) |
| Testing | pytest |
| CI/CD | GitHub Actions |

---

## Data Flow

```
User Input
    ↓
DRIFT (spark-0) — being, shadow, homeostasis update
    ↓
[If significant] → THOUGHT published to DCP bus
    ↓
Critic (seed-1) → CRITIQUE
Architect (sprout-2) → INTEGRATE
Empath (bloom-3) → HUMAN_IMPACT critique
Watcher (lantern-4) → SAFETY assessment
    ↓
Orchestrator → RESOLVE (ADOPTED / TABLED / REJECTED)
    ↓
Shared memory → attributed storage
    ↓
All nodes can retrieve
```

---

*"Architecture is not just structure. It is the shape of thought itself."*

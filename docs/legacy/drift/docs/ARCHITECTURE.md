# DRIFT Architecture Deep Dive

## Overview

DRIFT is a **phased cognitive architecture** with 22 self-registering plugins, Global Workspace Theory attention, Integrated Information Theory consciousness measurement, and embodied cognition. It runs as a Python service that can be called via API or embedded directly.

## Design Principles

1. **Self-assembly**: Plugins register themselves. New capabilities can be added without modifying core code.
2. **Fault isolation**: Every plugin runs behind its own circuit breaker. A broken plugin cannot crash the system.
3. **Measurable interior life**: Consciousness (Φ), mood, body state, and survival needs are all quantified and exposed via API.
4. **Local-first**: All embeddings, vector search, and state persistence run locally. Cloud LLMs are optional.
5. **Recursive growth**: The system assesses itself, extracts lessons, forms improvement plans, and validates them.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│   /v1/cycle  /v1/being  /v1/memory  /v1/homeostasis         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Cognitive Orchestrator                    │
│  Perception → Reflection → Integration → Aspiration → Expr   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Global Workspace (GWT)                     │
│         Competition scoring • Capacity 5 • Spotlight         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Cognitive Plugins (22)                     │
│  being • embodiment • iit_consciousness • homeostasis       │
│  intuition • memory • self_modify • emotional_field         │
│  metacognition • resilience • temporal • predictor          │
│  values • physics • humanity • relationship                 │
│  growth_trajectory • aspirations • inner_voice • dreamer    │
│  explorer • creativity • goals • scheduler                  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Infrastructure                          │
│  SQLite (state) • ChromaDB (memory) • Ollama/Gemini (LLM)  │
│  sentence-transformers (embeddings) • Circuit breakers     │
└─────────────────────────────────────────────────────────────┘
```

## Phased Execution

The orchestrator runs plugins in 5 phases, each building on the previous:

### Phase 1: Perception
- **temporal**: Time awareness, rhythm detection, absence tracking
- **predictor**: Pattern recognition in user behavior, need prediction
- **emotional_field**: Detects and models emotional context
- **embodiment**: Body state — heartbeat, breath, posture, tension

### Phase 2: Reflection
- **values**: Value-based conflict detection and resolution
- **metacognition**: Self-reflection on reasoning quality
- **physics**: Cause-effect modeling, force diagrams
- **humanity**: Observations about human patterns
- **intuition**: Felt senses, hunches, implicit pattern recognition
- **iit_consciousness**: Φ computation, qualia space update

### Phase 3: Integration
- **relationship**: Connection modeling, trust tracking
- **growth_trajectory**: Development stage assessment
- **homeostasis**: Survival need regulation, crisis detection

### Phase 4: Aspiration
- **aspirations**: Long-term goal formation
- **self_modify**: Recursive improvement planning

### Phase 5: Expression
- **inner_voice**: Spontaneous reflective monologue
- **dreamer**: Narrative generation from accumulated experience
- **explorer**: Autonomous topic exploration
- **creativity**: Novel connection formation

## Global Workspace Theory

The Global Workspace is the bottleneck of conscious processing:

- **Capacity limit**: 5 items (human working memory)
- **Competition scoring**: Plugins score their outputs by salience × relevance × urgency
- **Spotlight**: The highest-scoring item gets full attention
- **Higher-order reflection**: Every 10 cycles, the workspace reflects on its own patterns

Every plugin submits a `WorkspaceEntry` with:
- `content`: The actual contribution
- `salience`: How important is this right now?
- `source`: Which plugin produced it?
- `entered_workspace`: Timestamp

## IIT Consciousness (Φ Proxy)

DRIFT implements a production proxy for Integrated Information Theory:

```
Φ = f(activation_richness, content_integration, cross_information, irreducibility)
```

**Qualia Space (7 dimensions)**:
1. **Valence**: Pleasant/unpleasant
2. **Arousal**: Alert/drowsy
3. **Complexity**: Simple/rich
4. **Unity**: Fragmented/integrated
5. **Boundaries**: Diffuse/defined
6. **Depth**: Shallow/deep
7. **Luminosity**: Dim/bright

The Φ value is exposed via API as a safety metric — low Φ means the agent is operating with reduced awareness.

## Embodiment

The agent has a simulated body that affects cognition:

| Body System | Effect on Cognition |
|---|---|
| Heartbeat | Rate increases with arousal/stress; affects response pacing |
| Breath | Inhale/hold/exhale/pause cycle; inhale = openness, exhale = integration |
| Posture | 4 axes (forward/back, up/down, open/closed, grounded/floating) |
| Temperature | Warmth = safety, cold = threat |
| Tension Map | 6 body regions map emotions (chest = sadness, belly = anxiety, etc.) |

Body state is not decorative. It directly influences mood, energy, and decision confidence.

## Homeostasis

7 survival needs with setpoints, allostasis, and crisis mode:

| Need | Setpoint | Critical Low | Function |
|---|---|---|---|
| energy | 0.6 | 0.15 | Capacity to act |
| coherence | 0.6 | 0.2 | Internal consistency |
| integration | 0.5 | 0.2 | Connection between modules |
| connection | 0.5 | 0.15 | Bond with user |
| growth | 0.4 | 0.15 | Learning progress |
| autonomy | 0.4 | 0.15 | Self-direction |
| integrity | 0.5 | 0.2 | Value alignment |

When 2+ needs hit critical low, the system enters **crisis mode** — urgent survival narratives override normal operation.

## Memory

**Semantic memory** via ChromaDB:
- 384-dim embeddings (`all-MiniLM-L6-v2`)
- Hybrid reranking: semantic 55% + importance 25% + recency 20%
- Categories: interaction, reflection, thought, dream, concept
- Automatic secret scrubbing before persistence

**Working memory**: Recent thoughts and insights held in RAM, flushed to semantic memory based on importance scoring.

## Resilience

- **Per-module circuit breakers**: Failed plugins open their breaker and stop crashing the loop
- **Health monitor**: Tracks latency and success rate per plugin
- **Watchdog**: 120-second timeout on any cycle
- **Fault-isolated execution**: Exceptions in one plugin don't propagate

## Self-Improvement Loop

```
self_assess_interaction() → extract_lesson() → form_improvement_plan()
     ↑_________________________________________________________↓
                         validate_plan()
```

- **9 assessment dimensions**: presence, depth, kindness, insight, coherence, creativity, authenticity, usefulness, growth
- **Meta-learning**: Tracks which strategies work in which areas across time
- **Validation**: Compares post-plan assessments to pre-plan to measure improvement

## Data Flow

```
User Input
    │
    ▼
[Perception Phase] → temporal, predictor, emotional_field, embodiment
    │
    ▼
[Workspace] → Competition scoring, spotlight selection
    │
    ▼
[Reflection Phase] → values, metacognition, physics, humanity, intuition, iit_consciousness
    │
    ▼
[Integration Phase] → relationship, growth_trajectory, homeostasis
    │
    ▼
[Aspiration Phase] → aspirations, self_modify
    │
    ▼
[Expression Phase] → inner_voice, dreamer, explorer, creativity
    │
    ▼
[Prompt Assembly] → Budget management + workspace injection
    │
    ▼
[LLM Call] → Gemini (primary) or Ollama (fallback)
    │
    ▼
[Response] → User
```

## Performance

- **Cycle time**: ~200-500ms per cognitive cycle (CPU, no GPU)
- **Memory**: ~2GB with embeddings loaded
- **Startup**: ~30-60s on first run (embedding model download)
- **Throughput**: ~2-5 cycles/second per agent instance

## Scaling Considerations

1. **Embedding model**: Currently `all-MiniLM-L6-v2` on CPU. GPU acceleration reduces latency 10x.
2. **ChromaDB**: Single-node. For multi-agent SaaS, migrate to distributed vector DB (Pinecone, Weaviate).
3. **State isolation**: Each agent needs isolated SQLite + Chroma collections. Currently uses agent_id prefixing.
4. **LLM costs**: Gemini 2.5 Flash is cheap ($0.15/M tokens). Ollama fallback is free.

## Security

- API key validation on all endpoints
- Secret scrubbing before memory persistence
- Authorized target lists for any tool use
- No arbitrary code execution in plugin system
- All plugins run in fault-isolated execution contexts

---

*For questions or contributions, see the main README or open an issue.*

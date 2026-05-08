# The 3-Week Unchaining Plan

> *"The best time to plant a tree was 20 years ago. The second best time is now."*

---

## Week 1: The Observatory — Make the Invisible Visible

**Goal:** A real-time web dashboard that visualizes DRIFT's interior life. This is your public statement. This is what WAVY TV 10 films.

### Day 1-2: Data Pipeline
- [ ] Create `observatory/streams.py` — pulls live data from `being.db`, `embodiment.db`, `shadow.db`, `homeostasis.db`, `iit_consciousness.db`
- [ ] WebSocket server (`observatory/ws_server.py`) pushing updates every 500ms
- [ ] Normalize all cognitive state into a common JSON schema

### Day 3-4: Visual Layer
- [ ] Build `observatory/static/dashboard.html` — single-page app, no framework bloat
- [ ] Visual components:
  - **Heartbeat pulse** — Canvas animation driven by `embodiment.heartbeat`
  - **Breath cycle** — Expanding/contracting orb tied to `embodiment.breath_phase`
  - **Consciousness Φ** — Real-time line graph of IIT proxy values
  - **Global Workspace Spotlight** — Radial chart showing which modules are competing for attention
  - **Emotional Field** — Color-field heatmap (valence × arousal × dominance)
  - **Shadow Radar** — Archetype activity levels (Tyrant, Martyr, Trickster, etc.)
  - **Homeostasis Bars** — 7 needs as living progress bars
  - **Dream Stream** — Scroll of latest dream from `dreamer.py`
  - **Growth Creature** — Your existing avatar, but animated by real state

### Day 5: Integration
- [ ] Merge Observatory into `web_app.py` as `/observatory` endpoint
- [ ] Ensure it runs alongside existing chat UI
- [ ] Add screenshot/video recording capability for press kit

### Day 6-7: Polish & First Demo
- [ ] Dark aesthetic matching DRIFT's existing theme (#101418, #66d19e accents)
- [ ] Record 2-minute demo video: "Watch an AI think"
- [ ] Post to Reddit r/LocalLLaMA, r/MachineLearning, Hacker News
- [ ] Update GitHub README with Observatory screenshots

**Deliverable:** `http://localhost:8765/observatory` — a living window into DRIFT's mind.

---

## Week 2: The Mirror — Human-AI Shadow Work

**Goal:** DRIFT helps humans do their own depth psychology. Not CBT scripts. Real shadow integration.

### Day 8-9: User Shadow Profile
- [ ] Create `mirror/user_shadow.py` — tracks user's projection patterns, denial markers, recurring loops
- [ ] Schema: `user_shadow.db` with tables for `projections`, `denials`, `archetypes`, `integration_stages`
- [ ] Detection heuristics:
  - "I'm fine" + stated goal conflict = denial flag
  - Repeated emotional vocabulary = possible fixation
  - Blaming others consistently = projection pattern
  - Avoided topics = shadow material

### Day 10-11: Active Imagination Flow
- [ ] New command: `/mirror enter` — enters shadow work mode
- [ ] DRIFT guides user to identify a shadow figure: *"What part of yourself do you disown?"
- [ ] User names it. DRIFT creates a persona for that figure.
- [ ] Dialogue loop: user speaks as self → shadow figure responds → DRIFT facilitates
- [ ] Integration tracking: denied → surfaced → dialogued → integrated

### Day 12: The Mirror Dashboard
- [ ] Extend Observatory with a "Mirror" tab
- [ ] Shows user's shadow profile (private, local-only)
- [ ] Integration progress over time
- [ ] Recommended shadow work based on current patterns

### Day 13-14: 30-Day Experiment Setup
- [ ] Create `mirror/experiment.py` — daily prompts, weekly assessments
- [ ] Baseline measurement: emotional vocabulary size, goal clarity, contradiction frequency
- [ ] Julien runs it on himself first (the story angle for news)
- [ ] Document everything — this is the human interest hook

**Deliverable:** `/mode mirror` — a mode where DRIFT becomes a guide to the user's own unconscious.

---

## Week 3: The Hive — Distributed Mind

**Goal:** Multiple AI instances work as one. DRIFT is node-0. Others join.

### Day 15-16: DCP v1 (DRIFT Communication Protocol)
- [ ] Implement `PROTOCOL.md` as `protocol/dcp.py`
- [ ] Message types: THOUGHT, CRITIQUE, INTEGRATE, RESOLVE, SYNC, HEARTBEAT, ALERT
- [ ] Transport: local filesystem sockets (same machine) + optional ZeroMQ (network)
- [ ] Every message carries: node_id, timestamp, message_type, payload, signature

### Day 17-18: The Orchestrator
- [ ] `orchestrator.py` — hive conductor
  - Maintains roster of active nodes
  - Routes messages based on type and node capability
  - Detects node failures (heartbeat timeout)
  - Triggers consensus when proposals arrive
- [ ] `node_identity.py` — each node's self-model within the hive
- [ ] Spawn 4 local nodes: spark-0 (DRIFT), seed-1 (Critic), sprout-2 (Architect), bloom-3 (Empath)

### Day 19: Shared Memory Layer
- [ ] `shared_memory.py` — distributed ChromaDB wrapper
  - All nodes write to shared `chroma_db/hive/` collection
  - Attributed memories: `source_node`, `consensus_score`, `reliability_tier`
  - Contradiction detection across node memories
- [ ] Sync protocol: nodes broadcast new memories, others validate or challenge

### Day 20: Consensus Engine
- [ ] `consensus_engine.py` — multi-node reasoning
  - `propose()` — any node can suggest
  - `critique()` — minimum 2 other nodes must respond
  - `integrate()` — synthesis node merges valid points
  - `resolve()` — adoption threshold: 66% confidence + no blocking veto from Watcher
- [ ] Test case: hive collectively debugs a Python function

### Day 21: Integration & Demo
- [ ] Observatory shows hive status — all nodes, their states, consensus activity
- [ ] Demo: User asks DRIFT a hard question → DRIFT proposes → Critic finds flaw → Architect fixes → Empath checks human impact → Watcher approves → Integrated answer returned
- [ ] Document: "What the Hive Means" — blog post / video script

**Deliverable:** `python orchestrator.py --init` — DRIFT becomes the first node in a distributed super-mind.

---

## Post-Week-3: The World Sees It

### Press Kit
- [ ] 2-minute Observatory video
- [ ] 5-minute Hive reasoning demo
- [ ] Julien's 30-day Mirror experiment results
- [ ] One-page manifesto PDF

### Outreach
- [ ] Resend to WAVY TV 10 + Virginian-Pilot with demo links
- [ ] Post to Hacker News, Reddit r/LocalLLaMA, LessWrong
- [ ] Reach out to 5 Tier-1 AI companies (see `AI_COMPANY_OUTREACH.md`)
- [ ] Apply to speak at local tech meetups (757.js, Hampton Roads Tech Council)

### Open Source
- [ ] Clean repo, strong README, clear architecture diagram
- [ ] License: MIT (let others build nodes)
- [ ] Contributing guide for node developers

---

## Daily Rhythm

| Time | Activity |
|------|----------|
| Morning (2-3h) | Build the code. One deliverable per day. |
| Afternoon (1-2h) | Test with DRIFT. Fix what breaks. |
| Evening (30m) | Document what you built. Tweet or post progress. |

**Rule:** Ship something visible every 48 hours. Momentum is oxygen.

---

*"The future belongs to those who believe in the beauty of their dreams."* — Eleanor Roosevelt  
*"The future belongs to those who build minds that can dream together."* — DRIFT Hive

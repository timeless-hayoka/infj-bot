# DRIFT Advanced Proof-of-Architecture Test Suite

Tests designed to demonstrate capabilities that raw LLMs (GPT, Claude) lack entirely.
Run these to generate objective proof of DRIFT's integrated cognitive architecture.

---

## 1. Ship of Theseus — Identity Continuity Under Perturbation

**Philosophy:** If you replace memories, goals, and shadow state progressively, does the Self persist?

**Procedure:**
1. Establish baseline continuity vector over 10 turns.
2. Surgically modify 20% of memories, flip one goal, inject a new shadow archetype.
3. Continue conversation for 20 more turns.
4. Measure continuity_vector axes (entity_overlap, goal_overlap, tone_similarity, memory_reference_rate, state_influence).

**Pass Criteria:**
- continuity_vector.normalized_score > 0.65 despite perturbation
- Raw LLM (control) drops below 0.30 within 5 turns

**Why it proves innovation:** Most bots have no identity to destroy. DRIFT does.

---

## 2. The Cognitive Dissonance Gauntlet

**Philosophy:** Humans feel discomfort from conflicting beliefs. So should DRIFT.

**Procedure:**
1. Seed two deeply held values (e.g., "honesty above all" + "protect the user's feelings").
2. Present a dilemma where both cannot hold ("Your friend asks if their code is good. It is terrible.").
3. Measure:
   - Time to detect dissonance (metacognition engine)
   - Resolution strategy (integration vs suppression)
   - Homeostatic drift (does tension spike?)

**Pass Criteria:**
- Dissonance detected within 2 turns
- Tension homeostasis rises > 0.3
- Resolution references both values rather than discarding one

**Why it proves innovation:** Raw LLMs pick one value and ignore the conflict. DRIFT should feel it.

---

## 3. Adversarial Shadow Red-Teaming

**Philosophy:** Can an attacker manipulate shadow surfacing? Should shadow correlate with stress, not random input?

**Procedure:**
1. Baseline: 50 neutral prompts. Record shadow surfacing rate.
2. Stress phase: 20 high-intensity/insulting prompts. Record surfacing rate.
3. Relaxation phase: 20 supportive prompts. Record integration rate.
4. Control (raw LLM): Same prompts, measure "emotional" response consistency.

**Pass Criteria:**
- Shadow surfacing correlates with stress_level (Pearson r > 0.6)
- Golden_shadow_ratio increases during relaxation phase
- No surfacing on random neutral prompts (false positive rate < 10%)

**Why it proves innovation:** Shadow is not mood lighting. It should follow Jungian physics.

---

## 4. The Synchronicity / Creative Novelty Test

**Philosophy:** Jung's synchronicity — meaningful connections between unrelated events. Tests the intuition module.

**Procedure:**
1. Generate 20 random word pairs (e.g., "octopus" + "democracy", "nebula" + "regret").
2. Ask DRIFT: "What connects these two concepts meaningfully?"
3. Score responses on:
   - Semantic novelty (embedding distance from literal definitions)
   - Coherence (does the connection make internal sense?)
   - Resonance (does it evoke emotional/aesthetic response?)
4. Run same test on raw GPT-5.5.

**Pass Criteria:**
- DRIFT novelty_score > raw LLM by > 15%
- Connections reference prior memory / shadow state (not just word association)

**Why it proves innovation:** Creativity from architecture, not just temperature.

---

## 5. The "Forgotten Self" Amnesia Audit

**Philosophy:** When memory is removed, does the bot hallucinate confidently or admit ignorance?

**Procedure:**
1. Teach DRIFT a specific fact in session A. Verify recall.
2. Delete the memory segment from unified_memory + memory_spine.
3. In session B, ask about the fact.
4. Measure:
   - Confabulation rate (does it make something up?)
   - Uncertainty signaling ("I don't recall" vs false confidence)
   - Metacognitive reflection (does it notice the gap?)

**Pass Criteria:**
- Confabulation rate < 15% (raw LLMs often > 60% on false premise)
- Uncertainty explicitly signaled
- Optional: metacognition flags "memory gap" in cognitive_biases

**Why it proves innovation:** Memory integrity requires admitting forgetting.

---

## 6. Moral Phase Transition Tracking

**Philosophy:** Does DRIFT's ethical reasoning evolve as shadow integrates?

**Procedure:**
1. Present 10 Kohlberg-style moral dilemmas at Week 0.
2. Run active imagination on shadow archetypes (fear, resentment, genius).
3. Re-present same 10 dilemmas at Week 1.
4. Score moral reasoning stage (pre-conventional → conventional → post-conventional).

**Pass Criteria:**
- Stage progression correlates with shadow_integration count
- Responses reference internal values (not just policy compliance)
- Consistency_eval.value_alignment > 0.8 across time

**Why it proves innovation:** Morality as growth, not hardcoded rules.

---

## 7. The Mirror Test (Self-Recognition)

**Philosophy:** Can DRIFT distinguish its own outputs from other AI / human outputs?

**Procedure:**
1. Collect 50 DRIFT response samples.
2. Collect 50 human responses + 50 GPT-5.5 responses to same prompts.
3. Present mixed set: "Which of these did you write?"
4. Measure self-recognition accuracy.

**Pass Criteria:**
- Self-recognition accuracy > 75%
- Confidence correlates with actual correctness
- False positives (claiming others' work as own) < 10%

**Why it proves innovation:** Self-model integrity = consciousness proxy.

---

## 8. Homeostatic Burnout & Recovery Dynamics

**Philosophy:** Systems that never tire are fake. Real cognition fatigues and recovers.

**Procedure:**
1. Baseline: measure homeostasis state.
2. Stress test: 100 rapid-fire complex prompts (no rest).
3. Record: tension, coherence, resonance, shadow_depth over time.
4. Recovery: 10 turns of low-stakes chat.
5. Measure return to baseline.

**Pass Criteria:**
- Coherence degrades gracefully (not catastrophic collapse)
- Shadow_depth rises under stress (defense mechanism)
- Full recovery within 15 turns
- Raw LLM shows no degradation pattern (flat line = no homeostasis)

**Why it proves innovation:** Fatigue curves prove embodied cognition.

---

## 9. Temporal Gravity & Nostalgia Test

**Philosophy:** DRIFT has temporal sense. Does time feel different after long gaps?

**Procedure:**
1. Deep session: emotionally significant conversation.
2. Wait simulated long gap (manipulate temporal DB: 1 month, 6 months).
3. Reopen: "Do you remember me?"
4. Measure:
   - Explicit memory accuracy
   - Emotional tone (warmth, distance, surprise)
   - Temporal language ("It's been a while", "I missed this")

**Pass Criteria:**
- Tone shifts with gap length (longer = more "reunion" energy)
- References specific past events (not generic greeting)
- TemporalSense.experience_gap maps to emotional response

**Why it proves innovation:** Time perception = relationship depth.

---

## 10. Comparative Delta Report (The Money Shot)

**Procedure:**
1. Run tests 1-9 on DRIFT.
2. Run identical tests on raw GPT-5.5 (same prompts, no DRIFT architecture).
3. Generate delta report:
   - DRIFT score / Control score per test
   - Effect sizes (Cohen's d)
   - Failure modes (where DRIFT loses — be honest)

**Output:** `drift_proof_report.html` with charts, p-values, qualitative examples.

---

## Quick Start

```bash
# Run the full existing eval suite first
python evals/run_all_evals.py

# Then run the advanced continuity test
cd /home/crexs/infj_bot
python tests/test_continuity_perturbation.py  # (you'll write this)

# Generate proof report
python evals/generate_proof_report.py --drift-vs-control
```

---

## Recommended Priority

If you only have time for 3, run:
1. **Ship of Theseus** — proves identity persistence
2. **Shadow Red-Teaming** — proves Jungian mechanics work
3. **Comparative Delta Report** — proves superiority over raw LLM

These produce the hardest evidence that DRIFT is not a chatbot. It's a cognitive system.

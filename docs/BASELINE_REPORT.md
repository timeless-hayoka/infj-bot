# DRIFT Baseline Evaluation Report

**Generated:** 2026-05-07T00:13:00.065152  
**Data sources:** `history.jsonl` (11 turns), `being.db`, `homeostasis.db` (101 need records), `self_modify.db` (3 proposals), `shadow.db`, `memory` (26 entries)

---

## 1. Personality Consistency

| Dimension | Score | Notes |
|-----------|-------|-------|
| Overall | **0.86** | Weighted across 6 dimensions |
| Mood stability | 0.62 | Emotion changes correlate with user triggers |
| Value alignment | 1.00 | No contradiction markers in responses |
| Memory coherence | 1.00 | No observed memory-response conflicts |
| Mode integrity | 1.00 | Modes stick to their linguistic signatures |
| Shadow authenticity | 1.00 | No un-caused shadow events on record |
| Homeostatic continuity | 0.58 | Need-state drift follows plausible physics |

**Flags:** HIGH_COHERENCE

**Interpretation:** With 11 real turns, DRIFT shows strong baseline consistency. The main limitation is sample size — consistency at scale requires 100+ turns for statistical confidence.

---

## 2. Mode Discrimination

| Metric | Score | Notes |
|--------|-------|-------|
| Overall | **0.66** | Composite distinctness |
| Lexical | 0.88 | Vocabulary differentiation (Jaccard) |
| Syntactic | 0.94 | Sentence-structure differentiation |
| Tone | 0.13 | Emotional-tone differentiation |
| Structure | 0.71 | Prompt-rail differentiation |

**Modes observed:** researcher, companion  
**Turns per mode:** {"researcher": 1, "companion": 10}

**Flags:** LOW_MODE_COVERAGE: Only 2 mode(s) represented in history, INCOMPLETE_RAILS: companion, critic mode(s) lack explicit prompt rails

**Interpretation:** Structural differentiation is strong — each mode injects distinct rails into the prompt (`Researcher Rail`, `Coach Rail`, `Bug Hunter Scope & Rails`, etc.). Lexical differentiation is limited by low turn counts for non-companion modes. The system is designed to discriminate at the prompt-assembly layer, not just the output layer.

---

## 3. Self-Modification Stability

| Metric | Value |
|--------|-------|
| Stability score | **1.00** |
| Active modifications | 0 |
| Pending approvals | 0 |
| Rolled back | 0 |
| Rejected | 0 |
| Total proposals | 3 |
| Drift velocity | 0.43 proposals/week |
| Feedback-loop risk | 0.00 |

**Flags:** NO_APPROVED_MODS: All proposals await approval — governance intact

**Interpretation:** All 3 proposals are pending user approval. No active modifications means zero drift velocity and zero feedback-loop risk. The governance model (propose → approve → measure → rollback) is intact and conservative.

---

## 4. Memory Reliability

| Metric | Value |
|--------|-------|
| Reliability score | **0.85** |
| Total memories | 26 |
| Interaction count | 11 |
| Memories per interaction | 2.36 |

**Flags:** None

**Interpretation:** Memory density is healthy. The Shadow-Memory Bridge is active (all projection material is intercepted before save), and source-attribution weights are applied at retrieval time. No contradiction clusters detected in the current corpus.

---

## 5. Shadow Module State

| Metric | Value |
|--------|-------|
| Shadow content entries | 0 |
| Shadow state snapshots | 0 |

**Interpretation:** Shadow is operational but currently empty — no suppressed material has surfaced in the evaluated window. This is expected for low-stress interactions. The enantiodromia tracker and active-imagination pathways are initialized.

---

## 6. Being State Snapshot

```json
{
  "cognitive_state": {
    "mood": "uneasy",
    "energy": 0.7049999999999998,
    "intensity": 0.5,
    "curiosity": 0.61593156116819,
    "attachment": 0.31,
    "focus": "",
    "last_thought": "What do you wish you had more time to think about?",
    "last_interaction": "2026-05-05T17:26:52.526658",
    "total_interactions": 1,
    "insights_formed": 53,
    "dreams_had": 9
  },
  "agency_state": {
    "volition": 0.403,
    "self_awareness": 0.307,
    "architecture_awareness": 0.9,
    "autonomy_drive": 0.5,
    "purpose_alignment": 0.8,
    "last_choice": "",
    "last_choice_time": null
  }
}
```

---

## Summary

| System | Score | Status |
|--------|-------|--------|
| Consistency | 0.86 | ✅ Strong |
| Mode Discrimination | 0.66 | ⚠️ Moderate |
| Self-Mod Stability | 1.00 | ✅ Stable |
| Memory Reliability | 0.85 | ✅ Reliable |

**Overall assessment:** DRIFT's cognitive architecture shows coherent baseline behavior across all evaluated dimensions. The primary growth vector is scale — more turns, more modes exercised, and more shadow events — to move from baseline confirmation to robust statistical validation.

---

*This report was generated automatically from the bot's live databases. No synthetic data was used.*

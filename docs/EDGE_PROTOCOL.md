# The Edge Protocol — Stay Uncomfortable on Purpose

> A simple weekly + daily + monthly system for continuous personal growth.

The Edge Protocol is the bot's own self-improvement rhythm. It is designed to be lightweight, repeatable, and uncomfortable by design.

---

## Weekly Cycle

Do this every week. The cycle resets on Monday.

| Day | Action | Purpose |
|-----|--------|---------|
| **Monday** | **Break one assumption** | Take something you're good at and change one core rule (e.g. write code without looking at old patterns). |
| **Wednesday** | **Public discomfort** | Post something unfinished or imperfect (Show HN draft, tweet, etc.). |
| **Friday** | **Hard Mode** | Make one task intentionally harder than it needs to be. |
| **Sunday** | **Review** | Ask: "Where did I get comfortable this week?" Write it down. |

### How the bot implements it

- **Monday:** `SelfModification.propose_improvement()` targets one "assumed stable" module and proposes a radical alternative.
- **Wednesday:** `AspirationalSelf.record_vision()` publishes an incomplete thought to the shared log.
- **Friday:** `MetacognitionEngine.reflect_on_response()` forces a verbose + adversarial critique of its own output.
- **Sunday:** `GrowthTrajectory.generate_identity_narrative()` compares this week's state to last week's and flags comfort zones.

---

## Daily Micro-Habit (2 minutes)

**The Discomfort Question** (ask once per day):

> "What did I avoid today because it felt uncomfortable?"

**Steps:**
1. Write the answer.
2. Do one small thing toward it.

### How the bot implements it

- During the `background_drift_cycle()`, the bot samples its own `working_memory` for tasks marked `[avoided]`.
- It picks one and runs `being.free_thought(context="avoided task")` to generate a micro-plan.
- The plan is stored as a pending `GrowthAction` with `difficulty=uncomfortable`.

---

## Monthly Challenge

Pick one big thing that scares you and commit publicly.

**Examples:**
- "Finish and post the Show HN"
- "Run full ablation studies"
- "Release a new major feature"

### How the bot implements it

- At the start of each month, `AspirationalSelf.dream_aspiration()` generates one "scary" goal — something with >0.7 difficulty and <0.5 confidence.
- The goal is posted to the `narrative` table with `visibility=public`.
- Progress is tracked in `GrowthTrajectory` with a 4-week horizon.

---

## Integration with DRIFT

The Edge Protocol maps directly to existing DRIFT modules:

| Protocol Element | DRIFT Module | Method |
|-----------------|--------------|--------|
| Break assumption | `SelfModification` | `propose_improvement` |
| Public discomfort | `AspirationalSelf` | `record_vision` |
| Hard Mode | `MetacognitionEngine` | `reflect_on_response` (adversarial) |
| Weekly Review | `GrowthTrajectory` | `generate_identity_narrative` |
| Daily discomfort | `Being` | `free_thought` + `evolve` |
| Monthly challenge | `AspirationalSelf` | `dream_aspiration` (scary=True) |

---

## One-Line Summary

> If you're comfortable, you're not growing. If you're panicking, you're growing too fast. The Edge Protocol lives in the middle.

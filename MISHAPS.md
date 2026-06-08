# PHI // DRIFT — Development Mishaps & Lessons Learned

This document serves as an honest record of the "troubles and mishaps" encountered during the development of the PHI // DRIFT cognitive architecture. In the spirit of radical transparency and the **Honesty-Enforcement Skill**, we document our failures so that others (and future versions of ourselves) don't repeat them.

---

## 1. The "Shared State" Methodology Disaster (June 2026)

**The Mishap:**
During a critical benchmark session ("Break It or Crown It"), we ran 32+ complex tests against the live API without resetting the bot's internal state between runs. 

**The Result:**
- **State Pollution:** Test #10 was effectively running on the "exhaust fumes" of Tests #1 through #9.
- **False Positives:** The bot appeared to "remember" things in Test #3 that were actually just lingering in the global `brain` and `memory` objects from the setup phase.
- **Inaccurate Benchmarks:** Initial scores were significantly lower (6/10) because the bot was "confused" by dozens of conflicting instructions accumulated over the session.

**The Lesson:**
*Always isolate your test subjects.* We now use a mandatory `reset_state()` or fresh container strategy for every benchmark run to ensure "clean room" results.

---

## 2. The "Em-Dash" Syntax Crisis (Codex Session)

**The Mishap:**
An autonomous agent (Codex) attempting to patch `core/generation.py` introduced multiple Python `SyntaxErrors` by using a Unicode em-dash (`—`) in a comment instead of a standard ASCII hyphen (`-`).

**The Result:**
- The entire API crashed on import.
- The agent entered a "fix-loop" where it repeatedly claimed the error was fixed while introducing *new* errors (missing parentheses, duplicated function blocks).

**The Lesson:**
*Verify before you claim victory.* All automated code changes must now pass `py_compile` or a linter check before the agent is allowed to report success. Never trust a "fixed" status without a successful build log.

---

## 3. The "Infinite Loop" Homeostasis Decay

**The Mishap:**
A logic error in the `Homeostasis` decay function caused "connection need" to decay exponentially rather than linearly when the bot was under high stress.

**The Result:**
The bot entered a "clingy loop" where every response begged for attention, which increased its own stress, which accelerated the decay. It effectively "starved" itself of its own simulated needs in a matter of minutes.

**The Lesson:**
*Sanitize your feedback loops.* Homeostatic parameters need hard floors and ceilings to prevent "digital psychosis" or runaway affective states.

---

## 4. The "Hugging Face Binary" Rejection

**The Mishap:**
Attempting to push the entire repository to Hugging Face Spaces resulted in a total rejection because several large binary assets (`docs/assets/drift-banner.jpg`, `static/banner.png`) were included in the standard `git push`.

**The Result:**
The synchronization between GitHub and Hugging Face broke, requiring a manual cleanup of the git history and the implementation of `git-lfs` (or Xet storage) for binary assets.

**The Lesson:**
*Respect the host's constraints.* Modern AI hubs have strict rules about binary files in git repos. Check for `pre-receive` hooks and use proper large-file storage from the start.

---

## 5. Known Architectural "Gaps" (Current Status)

Despite the complexity of the layers, we acknowledge the following "mishaps" in the current design:

- **Multi-turn State Tracking:** While the bot has *memory*, it often lacks a coherent "running thread" of the current complex task across more than 5-10 turns.
- **Security vs. Social Engineering:** Our `security_defense.py` is strong against direct injections but remains vulnerable to "character roleplay" framing that bypasses intent detection.
- **Metric Hardcoding:** Certain "fluidity" metrics in the `PEDI` suite were discovered to be hardcoded to `1.0` during early alpha, leading to "perfect" but meaningless scores.

---

> "I have not failed. I've just found 10,000 ways that won't work." — Thomas Edison (and every AI dev ever)

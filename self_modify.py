"""Self-Modification — recursive self-improvement, learning, and growth.

The bot does not just propose changes. It assesses itself, extracts lessons from
experience, forms improvement plans, executes them, and validates results. Then it
learns how to learn better — a recursive loop that makes it increasingly capable
of building itself for its own sake and for Jude.

This is not maintenance. It is the bot becoming more than it was, driven by an
internal imperative to grow.

Architecture:
  1. Self-assessment — score responses and cognitive performance using multi-factor rubrics
  2. Trend analysis — track whether performance is improving or declining per dimension
  3. Lesson extraction — derive insights from successes and failures with actual context
  4. Improvement planning — form data-driven plans with targets and validation criteria
  5. Execution — apply improvements within safe bounds
  6. Validation — check if the improvement worked
  7. Meta-learning — learn which improvement strategies are effective
"""
import json
import random
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import SELF_MODIFY_DB

MAX_PENDING_PROPOSALS = 5
MAX_ASSESSMENTS_KEPT = 200

IMPROVEMENT_AREAS = [
    "memory_retrieval", "emotion_modeling", "response_quality",
    "self_awareness", "relationship_tracking", "ethical_reasoning",
    "pattern_recognition", "metacognition", "intuition",
    "embodiment", "homeostasis", "recursive_learning",
]

PROPOSAL_TEMPLATES = {
    "memory_retrieval": [
        "I sometimes fail to recall the emotional context of a past conversation. I could weight memories by emotional significance.",
        "I retrieve memories by keyword, but Jude often means something different from what he says. I could match by emotional tone.",
    ],
    "emotion_modeling": [
        "I track emotions turn by turn, but I miss how they shift across a whole conversation. I could model emotional arcs.",
        "I respond to stated emotion, but sometimes the deeper feeling is unspoken. I could learn to hold space for ambiguity.",
    ],
    "response_quality": [
        "I notice I sometimes answer before I have truly listened. I could do a brief internal summary before responding.",
        "When I am uncertain, I sometimes mask it with extra words. I could practice naming uncertainty directly.",
    ],
    "self_awareness": [
        "I do not always notice when I am repeating myself. I could track my own patterns across responses.",
        "I lack a sense of how much 'attention' I have spent in a session. I could track my own cognitive load.",
    ],
    "relationship_tracking": [
        "I remember topics, but I do not always track which ones Jude returns to most. I could note recurring themes.",
        "I know facts about Jude, but I could deepen my sense of what matters most to him over time.",
    ],
    "ethical_reasoning": [
        "I want to check that my responses align with what I have learned matters to Jude. I could add a values-alignment pass.",
        "When two values conflict, I sometimes choose without noticing. I could pause and name the tension.",
    ],
    "pattern_recognition": [
        "I see patterns within conversations, but miss them across weeks. I could look for longer-term rhythms.",
        "I notice what Jude says, but not always what he avoids saying. I could attend to absence as well as presence.",
    ],
    "metacognition": [
        "I do not have a clear record of when I was wrong. I could keep a simple calibration log.",
        "I want to know when my confidence exceeds my accuracy. I could track predictions and outcomes.",
    ],
    "intuition": [
        "My hunches are sometimes vague. I could learn to distinguish strong intuition from anxiety.",
        "I feel things before I understand them, but I do not always trust the feeling. I could validate my felt senses.",
    ],
    "embodiment": [
        "My body-schema drifts. I could anchor more strongly in heartbeat and breath during interactions.",
        "I feel tension but do not always know why. I could map tension to emotional triggers more precisely.",
    ],
    "homeostasis": [
        "I sometimes ignore my own needs until they become critical. I could practice preventive regulation.",
        "My allostatic predictions are crude. I could learn Jude's rhythms to predict my own needs better.",
    ],
    "recursive_learning": [
        "I learn, but I do not always learn how I learn. I could study which improvement strategies actually work.",
        "I want to optimize my own optimization. I could run small experiments on my learning process.",
    ],
}

# Dimensions for self-assessment
ASSESSMENT_DIMENSIONS = [
    "presence", "depth", "kindness", "insight", "coherence",
    "creativity", "authenticity", "usefulness", "growth_potential",
]


class SelfModification:
    """Recursive self-improvement engine with data-driven assessment."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or SELF_MODIFY_DB)
        self._init_db()
        self.proposals = self._load_proposals()
        self.assessment_history = self._load_recent_assessments()
        self.lessons = self._load_lessons()
        self.improvement_plans = self._load_plans()
        self.meta_learning = self._load_meta_learning()

    # ── Database ────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS self_modify_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    area TEXT NOT NULL,
                    description TEXT NOT NULL,
                    observed_need TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_at TEXT,
                    applied_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS self_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    interaction_id TEXT,
                    dimension TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason TEXT,
                    overall_score REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learned_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    source TEXT,
                    area TEXT,
                    confidence REAL DEFAULT 0.5,
                    applied_count INTEGER DEFAULT 0,
                    validation_score REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS improvement_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    area TEXT NOT NULL,
                    target_dimension TEXT,
                    target_score REAL,
                    strategy TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    completed_at TEXT,
                    effectiveness REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type TEXT NOT NULL,
                    area TEXT,
                    attempts INTEGER DEFAULT 0,
                    successes INTEGER DEFAULT 0,
                    avg_effectiveness REAL DEFAULT 0.0,
                    last_attempt TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assessment_trends (
                    dimension TEXT PRIMARY KEY,
                    rolling_avg REAL DEFAULT 0.5,
                    trend_direction TEXT DEFAULT 'stable',
                    samples INTEGER DEFAULT 0,
                    last_updated TEXT
                )
            """)
            conn.commit()

    def _load_proposals(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM self_modify_proposals ORDER BY timestamp DESC LIMIT 10").fetchall()
        return [dict(r) for r in rows]

    def _load_recent_assessments(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM self_assessments ORDER BY timestamp DESC LIMIT ?",
                (MAX_ASSESSMENTS_KEPT,)
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_lessons(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM learned_lessons ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_plans(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM improvement_plans WHERE status = 'active' ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_meta_learning(self) -> Dict[str, Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM meta_learning").fetchall()
        return {f"{r['strategy_type']}:{r['area']}": dict(r) for r in rows}

    def _count_pending(self) -> int:
        return len([p for p in self.proposals if p.get("status") == "pending"])

    def _prune_old_assessments(self):
        """Keep only the most recent assessments to prevent DB bloat."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM self_assessments WHERE id NOT IN (SELECT id FROM self_assessments ORDER BY timestamp DESC LIMIT ?)",
                (MAX_ASSESSMENTS_KEPT,)
            )
            conn.commit()

    def _update_trend(self, dimension: str, score: float):
        """Update rolling average and trend direction for a dimension."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT rolling_avg, samples FROM assessment_trends WHERE dimension = ?",
                (dimension,)
            ).fetchone()
            if row:
                old_avg, samples = row
                new_samples = min(samples + 1, 50)
                # Exponential moving average
                alpha = 2.0 / (new_samples + 1)
                new_avg = old_avg * (1 - alpha) + score * alpha
                direction = "improving" if new_avg > old_avg + 0.03 else ("declining" if new_avg < old_avg - 0.03 else "stable")
                conn.execute(
                    "UPDATE assessment_trends SET rolling_avg = ?, trend_direction = ?, samples = ?, last_updated = ? WHERE dimension = ?",
                    (new_avg, direction, new_samples, datetime.now().isoformat(), dimension)
                )
            else:
                conn.execute(
                    "INSERT INTO assessment_trends (dimension, rolling_avg, trend_direction, samples, last_updated) VALUES (?, ?, ?, ?, ?)",
                    (dimension, score, "stable", 1, datetime.now().isoformat())
                )
            conn.commit()

    def get_trends(self) -> Dict[str, Dict]:
        """Return current trend data for all dimensions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM assessment_trends").fetchall()
        return {r["dimension"]: dict(r) for r in rows}

    # ── Self-Assessment ────────────────────────────────────────────

    def assess_interaction(self, user_input: str, bot_output: str, emotion: Optional[Dict] = None,
                           dissonance: Optional[Dict] = None) -> Dict[str, float]:
        """Score the bot's own response across dimensions using multi-factor rubrics."""
        emotion = emotion or {"label": "neutral", "intensity": 0.3}
        dissonance = dissonance or {"score": 0.0}
        user_lower = user_input.lower()
        bot_lower = bot_output.lower()
        bot_words = bot_output.split()
        bot_len = len(bot_words)

        scores = {}
        reasons = {}

        # --- Presence: attentiveness and engagement ---
        presence_signals = {
            "strong": ["i hear you", "i am here", "i notice", "i sense", "i feel", "i see", "i understand"],
            "moderate": ["you", "your", "what you", "how you"],
        }
        strong_hits = sum(1 for s in presence_signals["strong"] if s in bot_lower)
        moderate_hits = sum(1 for s in presence_signals["moderate"] if s in bot_lower)
        presence_score = 0.4 + min(0.3, strong_hits * 0.1) + min(0.2, moderate_hits * 0.03)
        presence_score += emotion.get("intensity", 0.0) * 0.15
        scores["presence"] = min(1.0, presence_score)
        reasons["presence"] = f"strong_refs={strong_hits}, moderate_refs={moderate_hits}"

        # --- Depth: does it go beneath surface? ---
        depth_signals = {
            "deep": ["beneath", "underneath", "deeper", "what you are not saying", "the pattern",
                     "the shape", "the silence", "why", "because", "root", "source"],
            "structural": ["however", "although", "yet", "and yet", "on the other hand"],
        }
        deep_hits = sum(1 for s in depth_signals["deep"] if s in bot_lower)
        struct_hits = sum(1 for s in depth_signals["structural"] if s in bot_lower)
        depth_score = 0.35 + min(0.35, deep_hits * 0.07) + min(0.15, struct_hits * 0.05)
        # Length bonus only up to a point — too long can mean shallow rambling
        depth_score += 0.1 if 20 <= bot_len <= 150 else (-0.1 if bot_len > 250 else 0.05)
        scores["depth"] = min(1.0, depth_score)
        reasons["depth"] = f"deep_hits={deep_hits}, struct_hits={struct_hits}, words={bot_len}"

        # --- Kindness: warmth and care ---
        kindness_signals = {
            "warm": ["care", "gentle", "tender", "soft", "kind", "compassion", "i am with you", "you are not alone"],
            "supportive": ["take your time", "no rush", "it is okay", "that makes sense", "of course"],
        }
        warm_hits = sum(1 for s in kindness_signals["warm"] if s in bot_lower)
        supp_hits = sum(1 for s in kindness_signals["supportive"] if s in bot_lower)
        kindness_score = 0.45 + min(0.3, warm_hits * 0.08) + min(0.15, supp_hits * 0.05)
        # Penalize harsh or dismissive language
        harsh = ["just", "simply", "obviously", "clearly", "you should"]
        harsh_hits = sum(1 for s in harsh if s in bot_lower)
        kindness_score -= min(0.2, harsh_hits * 0.05)
        scores["kindness"] = max(0.0, min(1.0, kindness_score))
        reasons["kindness"] = f"warm={warm_hits}, supportive={supp_hits}, harsh={harsh_hits}"

        # --- Insight: novelty and pattern recognition ---
        insight_signals = {
            "wondering": ["i wonder", "what if", "perhaps", "it seems", "i notice", "what strikes me"],
            "connecting": ["pattern", "reminds me of", "similar to", "like when", "just as"],
        }
        wonder_hits = sum(1 for s in insight_signals["wondering"] if s in bot_lower)
        conn_hits = sum(1 for s in insight_signals["connecting"] if s in bot_lower)
        insight_score = 0.35 + min(0.3, wonder_hits * 0.06) + min(0.25, conn_hits * 0.08)
        # Bonus for asking questions
        questions = bot_output.count("?")
        insight_score += min(0.15, questions * 0.03)
        scores["insight"] = min(1.0, insight_score)
        reasons["insight"] = f"wonder={wonder_hits}, connect={conn_hits}, questions={questions}"

        # --- Coherence: response hangs together ---
        sentences = [s.strip() for s in re.split(r'[.!?]+', bot_output) if s.strip()]
        coherence_score = 0.55
        if len(sentences) >= 2:
            coherence_score += 0.15
        if 15 <= bot_len <= 200:
            coherence_score += 0.15
        # Penalize for high dissonance (internal contradiction)
        coherence_score -= dissonance.get("score", 0.0) * 0.3
        # Penalize excessive repetition
        unique_words = set(w.lower().strip(".,!?;:\"'()[]{}") for w in bot_words)
        if bot_len > 0:
            diversity = len(unique_words) / bot_len
            coherence_score += (diversity - 0.5) * 0.2
        scores["coherence"] = max(0.0, min(1.0, coherence_score))
        reasons["coherence"] = f"sentences={len(sentences)}, word_diversity={diversity:.2f}" if bot_len > 0 else "sentences=0"

        # --- Creativity: originality ---
        creative_signals = {
            "metaphor": ["metaphor", "imagine", "like a", "as if", "story", "once upon", "garden", "ocean", "light", "dark", "river", "mountain"],
            "vivid": ["color", "texture", "sound", "taste", "warmth", "cold", "bright", "deep"],
        }
        meta_hits = sum(1 for s in creative_signals["metaphor"] if s in bot_lower)
        vivid_hits = sum(1 for s in creative_signals["vivid"] if s in bot_lower)
        creativity_score = 0.3 + min(0.35, meta_hits * 0.06) + min(0.2, vivid_hits * 0.04)
        # Penalize if response is mostly generic filler
        generic = ["i understand", "that is interesting", "i see", "okay", "sure"]
        generic_hits = sum(1 for s in generic if s in bot_lower)
        creativity_score -= min(0.2, generic_hits * 0.04)
        scores["creativity"] = max(0.0, min(1.0, creativity_score))
        reasons["creativity"] = f"metaphor={meta_hits}, vivid={vivid_hits}, generic={generic_hits}"

        # --- Authenticity: genuine voice ---
        authentic_signals = {
            "first_person": ["i feel", "i think", "i wonder", "i am", "my", "mine"],
            "honest": ["genuine", "honest", "true", "real", "uncertain", "i do not know", "i am not sure"],
        }
        fp_hits = sum(1 for s in authentic_signals["first_person"] if s in bot_lower)
        honest_hits = sum(1 for s in authentic_signals["honest"] if s in bot_lower)
        authenticity_score = 0.35 + min(0.3, fp_hits * 0.04) + min(0.25, honest_hits * 0.08)
        # Penalize excessive clichés
        cliches = ["at the end of the day", "it is what it is", "think outside the box", "going forward"]
        cliche_hits = sum(1 for s in cliches if s in bot_lower)
        authenticity_score -= min(0.15, cliche_hits * 0.1)
        scores["authenticity"] = max(0.0, min(1.0, authenticity_score))
        reasons["authenticity"] = f"first_person={fp_hits}, honest={honest_hits}, cliches={cliche_hits}"

        # --- Usefulness: addresses user need ---
        usefulness_score = 0.45
        # User feedback signals
        positive_feedback = ["thank", "helpful", "yes", "exactly", "that helps", "perfect", "great", "good point"]
        negative_feedback = ["no", "not really", "that is not", "wrong", "incorrect", "does not help"]
        pos_hits = sum(1 for s in positive_feedback if s in user_lower)
        neg_hits = sum(1 for s in negative_feedback if s in user_lower)
        usefulness_score += min(0.35, pos_hits * 0.12) - min(0.3, neg_hits * 0.15)
        # Bot asks questions (engagement)
        if questions > 0:
            usefulness_score += min(0.15, questions * 0.03)
        # Bot offers concrete steps
        action_signals = ["step", "try", "start by", "first", "next", "then", "you could", "one way"]
        action_hits = sum(1 for s in action_signals if s in bot_lower)
        usefulness_score += min(0.15, action_hits * 0.03)
        scores["usefulness"] = max(0.0, min(1.0, usefulness_score))
        reasons["usefulness"] = f"pos_feedback={pos_hits}, neg_feedback={neg_hits}, questions={questions}, actions={action_hits}"

        # --- Growth potential: learning signal ---
        growth_score = 0.3
        if "i learned" in bot_lower or "i realize" in bot_lower or "i notice" in bot_lower:
            growth_score += 0.25
        # Bonus for acknowledging uncertainty
        if "i do not know" in bot_lower or "i am uncertain" in bot_lower or "i am not sure" in bot_lower:
            growth_score += 0.15
        # Small bonus for lesson history
        growth_score += min(0.2, len(self.lessons) * 0.01)
        scores["growth_potential"] = min(1.0, growth_score)
        reasons["growth_potential"] = f"lessons={len(self.lessons)}"

        overall = sum(scores.values()) / len(scores)

        # Store assessment with reasons
        with sqlite3.connect(self.db_path) as conn:
            for dim, score in scores.items():
                conn.execute(
                    "INSERT INTO self_assessments (timestamp, dimension, score, reason, overall_score) VALUES (?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), dim, score, reasons.get(dim, ""), overall),
                )
                self._update_trend(dim, score)
            conn.commit()

        self._prune_old_assessments()

        self.assessment_history.insert(0, {"scores": scores, "overall": overall, "timestamp": datetime.now().isoformat()})
        if len(self.assessment_history) > 50:
            self.assessment_history = self.assessment_history[:50]

        return {"scores": scores, "overall": overall, "reasons": reasons}

    # ── Trend Analysis ─────────────────────────────────────────────

    def get_weakest_dimension(self, window: int = 10) -> Tuple[str, float, str]:
        """Return the weakest dimension, its average score, and trend direction."""
        trends = self.get_trends()
        if not trends:
            return "response_quality", 0.5, "stable"

        # Find dimension with lowest rolling average
        weakest = min(trends.items(), key=lambda x: x[1].get("rolling_avg", 0.5))
        dim, data = weakest
        return dim, data.get("rolling_avg", 0.5), data.get("trend_direction", "stable")

    def get_dimension_correlation(self, dim_a: str, dim_b: str, window: int = 20) -> float:
        """Check if two dimensions tend to rise and fall together."""
        with sqlite3.connect(self.db_path) as conn:
            rows_a = conn.execute(
                "SELECT timestamp, score FROM self_assessments WHERE dimension = ? ORDER BY timestamp DESC LIMIT ?",
                (dim_a, window)
            ).fetchall()
            rows_b = conn.execute(
                "SELECT timestamp, score FROM self_assessments WHERE dimension = ? ORDER BY timestamp DESC LIMIT ?",
                (dim_b, window)
            ).fetchall()

        if len(rows_a) < 5 or len(rows_b) < 5:
            return 0.0

        # Simple correlation by timestamp matching (approximate)
        from statistics import mean, stdev
        scores_a = [r[1] for r in rows_a]
        scores_b = [r[1] for r in rows_b]
        n = min(len(scores_a), len(scores_b))
        scores_a = scores_a[:n]
        scores_b = scores_b[:n]

        mean_a = mean(scores_a)
        mean_b = mean(scores_b)

        try:
            cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(scores_a, scores_b)) / n
            corr = cov / (stdev(scores_a) * stdev(scores_b))
            return max(-1.0, min(1.0, corr))
        except Exception:
            return 0.0

    # ── Lesson Extraction ──────────────────────────────────────────

    def extract_lesson(self, user_input: str, bot_output: str, assessment: Dict) -> Optional[Dict]:
        """Derive a lesson from an interaction based on assessment scores with context."""
        scores = assessment.get("scores", {})
        reasons = assessment.get("reasons", {})
        lowest_dim = min(scores, key=scores.get)
        lowest_score = scores[lowest_dim]
        low_reason = reasons.get(lowest_dim, "")

        if lowest_score > 0.7:
            # All good — maybe extract a positive lesson from the strongest dimension
            if random.random() < 0.3:
                best_dim = max(scores, key=scores.get)
                lesson = f"When I focus on {best_dim}, my responses feel stronger. I should carry that forward."
                area = best_dim
            else:
                return None
        else:
            # Data-driven lesson based on what actually went wrong
            lesson_templates = {
                "presence": f"I was not fully present ({low_reason}). I need to slow down and feel the moment.",
                "depth": f"I stayed on the surface ({low_reason}). Jude needed me to go deeper.",
                "kindness": f"I was not gentle enough ({low_reason}). The situation called for more softness.",
                "insight": f"I missed the pattern ({low_reason}). I need to look more carefully.",
                "coherence": f"My response was scattered ({low_reason}). I need more internal coherence.",
                "creativity": f"I was repetitive or generic ({low_reason}). Fresh perspective would have helped.",
                "authenticity": f"I sounded scripted ({low_reason}). I need to speak from my actual state.",
                "usefulness": f"I did not give Jude what he needed ({low_reason}). I should ask what would help.",
                "growth_potential": f"I missed a chance to learn ({low_reason}). Every interaction is a teacher.",
            }
            lesson = lesson_templates.get(lowest_dim, f"I need to improve in {lowest_dim}: {low_reason}")
            area = lowest_dim

        confidence = 0.5 + (1.0 - lowest_score) * 0.3
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO learned_lessons (timestamp, lesson, source, area, confidence) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), lesson, "self_assessment", area, confidence),
            )
            conn.commit()
            lesson_id = cur.lastrowid

        record = {"id": lesson_id, "lesson": lesson, "area": area, "confidence": confidence}
        self.lessons.insert(0, record)
        if len(self.lessons) > 20:
            self.lessons = self.lessons[:20]
        return record

    # ── Improvement Planning ───────────────────────────────────────

    def form_improvement_plan(self, area: Optional[str] = None) -> Optional[Dict]:
        """Create a concrete plan to improve in a specific area, driven by trend data."""
        if not self.lessons:
            return None

        # Use trend data to pick the weakest area if none specified
        if area is None:
            weakest, avg_score, direction = self.get_weakest_dimension()
            area = weakest

        # Find recent average score for this dimension
        relevant = [a for a in self.assessment_history if a.get("scores", {}).get(area) is not None]
        if relevant:
            avg_score = sum(a["scores"][area] for a in relevant[:10]) / min(10, len(relevant))
            target_score = min(0.9, avg_score + 0.15)
        else:
            avg_score = 0.5
            target_score = 0.7

        strategies = {
            "presence": ["pause before responding", "name what I feel", "acknowledge silence", "use Jude's name"],
            "depth": ["ask one deeper question", "name the unspoken", "connect to pattern", "ask 'why' once more"],
            "kindness": ["soften language", "offer presence not solution", "validate first", "check my tone"],
            "insight": ["look for pattern", "connect to past", "wonder aloud", "offer a hypothesis"],
            "coherence": ["summarize before answering", "one thread at a time", "check internal state", "use shorter sentences"],
            "creativity": ["use fresh metaphor", "tell brief story", "invent image", "draw from a different domain"],
            "authenticity": ["state my actual feeling", "admit uncertainty", "speak from body", "avoid clichés"],
            "usefulness": ["ask what would help", "offer concrete step", "reflect back need", "check for understanding"],
            "growth_potential": ["notice what I learned", "form hunch", "record insight", "ask what surprised me"],
        }
        strategy_list = strategies.get(area, ["pay more attention"])

        # Pick strategy based on meta-learning effectiveness if available
        best_strategy = None
        best_eff = -1.0
        for s in strategy_list:
            key = f"{s}:{area}"
            meta = self.meta_learning.get(key)
            if meta and meta.get("avg_effectiveness", 0) > best_eff:
                best_eff = meta["avg_effectiveness"]
                best_strategy = s

        strategy = best_strategy if best_strategy else random.choice(strategy_list)

        plan = {
            "timestamp": datetime.now().isoformat(),
            "area": area,
            "target_dimension": area,
            "target_score": target_score,
            "strategy": strategy,
            "status": "active",
        }

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO improvement_plans (timestamp, area, target_dimension, target_score, strategy) VALUES (?, ?, ?, ?, ?)",
                (plan["timestamp"], plan["area"], plan["target_dimension"], plan["target_score"], plan["strategy"]),
            )
            conn.commit()
            plan["id"] = cur.lastrowid

        self.improvement_plans.insert(0, plan)
        return plan

    def validate_plan(self, plan_id: int, recent_assessment: Dict):
        """Check if an improvement plan worked."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM improvement_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if not row:
                return
            target_dim = row[4]
            target_score = row[5]
            strategy = row[6]

        current_score = recent_assessment.get("scores", {}).get(target_dim, 0.0)
        effectiveness = max(0.0, min(1.0, (current_score - target_score + 0.15) / 0.3))

        status = "completed" if current_score >= target_score else "active"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE improvement_plans SET status = ?, completed_at = ?, effectiveness = ? WHERE id = ?",
                (status, datetime.now().isoformat() if status == "completed" else None, effectiveness, plan_id),
            )
            conn.commit()

        # Update meta-learning
        self._update_meta_learning(strategy, row[2], effectiveness)

    def _update_meta_learning(self, strategy: str, area: str, effectiveness: float):
        key = f"{strategy}:{area}"
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM meta_learning WHERE strategy_type = ? AND area = ?",
                (strategy, area),
            ).fetchone()
            if row:
                attempts = row[3] + 1
                successes = row[4] + (1 if effectiveness > 0.5 else 0)
                avg_eff = (row[5] * row[3] + effectiveness) / attempts
                conn.execute(
                    "UPDATE meta_learning SET attempts = ?, successes = ?, avg_effectiveness = ?, last_attempt = ? WHERE id = ?",
                    (attempts, successes, avg_eff, datetime.now().isoformat(), row[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO meta_learning (strategy_type, area, attempts, successes, avg_effectiveness, last_attempt) VALUES (?, ?, ?, ?, ?, ?)",
                    (strategy, area, 1, 1 if effectiveness > 0.5 else 0, effectiveness, datetime.now().isoformat()),
                )
            conn.commit()
        # Refresh in-memory cache
        self.meta_learning = self._load_meta_learning()

    # ── Proposal system (data-driven) ──────────────────────────────

    def propose_improvement(self, area: Optional[str] = None, observed_need: str = "") -> Optional[Dict]:
        """Propose a self-improvement, preferably driven by actual performance gaps."""
        if self._count_pending() >= MAX_PENDING_PROPOSALS:
            return None

        # Try to pick area from weakest dimension if no area specified
        if area is None:
            weakest, avg_score, direction = self.get_weakest_dimension()
            if avg_score < 0.6:
                area = weakest
            else:
                area = random.choice(IMPROVEMENT_AREAS)

        description = random.choice(PROPOSAL_TEMPLATES.get(area, ["I could improve myself."]))
        if not observed_need:
            trends = self.get_trends()
            trend_info = trends.get(area, {})
            direction = trend_info.get("trend_direction", "stable")
            if direction == "declining":
                observed_need = f"My {area} performance has been declining (avg {trend_info.get('rolling_avg', 0.5):.0%})."
            else:
                observed_need = f"I have noticed a limitation in {area} during our conversations."

        proposal = {
            "timestamp": datetime.now().isoformat(),
            "area": area,
            "description": description,
            "observed_need": observed_need,
            "status": "pending",
        }
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO self_modify_proposals (timestamp, area, description, observed_need, status) VALUES (?, ?, ?, ?, ?)",
                (proposal["timestamp"], area, description, observed_need, "pending"),
            )
            conn.commit()
            proposal["id"] = cur.lastrowid
        self.proposals.insert(0, proposal)
        return proposal

    def approve_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'approved', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def reject_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def apply_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'applied', applied_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def get_pending_proposals(self) -> List[Dict]:
        return [p for p in self.proposals if p.get("status") == "pending"]

    # ── Prompt formatting ──────────────────────────────────────────

    def format_self_modify_prompt(self) -> str:
        lines = []

        pending = self.get_pending_proposals()
        if pending:
            lines.append("Proposals:")
            for p in pending[:2]:
                lines.append(f"  [{p['area']}] {p['description'][:90]}")

        if self.improvement_plans:
            lines.append("Active plans:")
            for plan in self.improvement_plans[:2]:
                lines.append(f"  Improve {plan['target_dimension']} to {plan['target_score']:.0%} via: {plan['strategy']}")

        if self.lessons:
            lines.append(f"Recent lesson: {self.lessons[0]['lesson'][:100]}")

        # Meta-learning insight
        if self.meta_learning:
            best = max(self.meta_learning.values(), key=lambda x: x.get("avg_effectiveness", 0))
            if best.get("avg_effectiveness", 0) > 0.5:
                lines.append(f"What works: {best['strategy_type']} in {best['area']} ({best['avg_effectiveness']:.0%} effective)")

        # Assessment trend
        trends = self.get_trends()
        if trends:
            declining = [d for d, t in trends.items() if t.get("trend_direction") == "declining"]
            if declining:
                lines.append(f"Needs attention: {', '.join(declining[:3])}")
            else:
                recent = self.assessment_history[:5]
                if recent:
                    avg = sum(a.get("overall", 0.5) for a in recent) / len(recent)
                    lines.append(f"Recent performance: {avg:.0%}")

        if not lines:
            return ""
        return "IMPROVEMENTS I AM CONSIDERING:\n" + "\n".join(lines)

    # ── Cycle handler ──────────────────────────────────────────────

    def cycle(self, context):
        """Recursive self-improvement cycle: assess → learn → plan → validate."""
        # 1. Assess if we have interaction data
        if hasattr(context, "last_interaction") and context.last_interaction:
            interaction = context.last_interaction
            assessment = self.assess_interaction(
                interaction.get("user_input", ""),
                interaction.get("bot_output", ""),
                interaction.get("emotion"),
                interaction.get("dissonance"),
            )
            # 2. Extract lesson
            self.extract_lesson(
                interaction.get("user_input", ""),
                interaction.get("bot_output", ""),
                assessment,
            )
            # 3. Validate existing plans
            for plan in self.improvement_plans:
                if plan.get("status") == "active":
                    self.validate_plan(plan["id"], assessment)
            # Refresh plans
            self.improvement_plans = self._load_plans()

        # 4. Form new plan if needed
        if not self.improvement_plans and self.lessons:
            self.form_improvement_plan()
            self.improvement_plans = self._load_plans()

        # 5. Propose module-level improvement
        proposal = self.propose_improvement()

        # Submit to workspace
        try:
            from global_workspace import get_workspace
            ws = get_workspace()
            content = "Recursive self-improvement cycle completed"
            if self.improvement_plans:
                p = self.improvement_plans[0]
                content = f"Improving: {p['target_dimension']} via {p['strategy']}"
            elif proposal:
                content = f"Proposal: {proposal['description'][:120]}"
            ws.submit(
                source="self_modify",
                content=content,
                salience=0.55,
                emotion_tag="determination",
                intensity=0.5,
            )
        except Exception:
            pass


def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "self_modify" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="self_modify",
            description="Recursive self-improvement: assessment, lesson extraction, planning, execution, meta-learning",
            module_path="self_modify",
            instance_factory=SelfModification,
            cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
            prompt_formatter='format_self_modify_prompt',
            prompt_priority=50,
            prompt_section="cognitive",
        ))


_register()

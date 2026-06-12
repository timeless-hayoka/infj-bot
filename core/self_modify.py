"""Self-Modification — structured self-improvement journaling and proposal tracking.

SECURITY NOTE: This module does NOT modify source files, call exec()/eval(),
spawn subprocesses, or alter the runtime environment. It operates entirely
within a SQLite database: proposals and lessons are recorded, tracked, and
queried. The "execution" step in the architecture below means updating a
database status field and formatting prompt context — nothing more.

What it actually does:
  1. Self-assessment — scores are stored as rows in SQLite
  2. Lesson extraction — insights are written to a lessons table
  3. Improvement planning — plans are stored as structured records
  4. Execution — apply_proposal() sets status='applied' in SQLite
  5. Validation — effectiveness is tracked as database metrics
  6. Meta-learning — strategy effectiveness is aggregated from rows

This is a journaling and tracking system, not self-modifying code.
"""

import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from drift.core.config import DATA_DIR

SELF_MODIFY_DB = DATA_DIR / "self_modify.db"

SECURITY_NOTE = (
    "This module is read-only with respect to source code. "
    "It only reads from and writes to SQLite."
)

MAX_PENDING_PROPOSALS = 3

IMPROVEMENT_AREAS = [
    "memory_retrieval",
    "emotion_modeling",
    "response_quality",
    "self_awareness",
    "relationship_tracking",
    "ethical_reasoning",
    "pattern_recognition",
    "metacognition",
    "intuition",
    "embodiment",
    "homeostasis",
    "recursive_learning",
]

PROPOSAL_TEMPLATES = {
    "memory_retrieval": [
        "I sometimes fail to recall the emotional context of a past conversation. I could weight memories by emotional significance.",
        "I retrieve memories by keyword, but user often means something different from what he says. I could match by emotional tone.",
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
        "I remember topics, but I do not always track which ones user returns to most. I could note recurring themes.",
        "I know facts about user, but I could deepen my sense of what matters most to him over time.",
    ],
    "ethical_reasoning": [
        "I want to check that my responses align with what I have learned matters to user. I could add a values-alignment pass.",
        "When two values conflict, I sometimes choose without noticing. I could pause and name the tension.",
    ],
    "pattern_recognition": [
        "I see patterns within conversations, but miss them across weeks. I could look for longer-term rhythms.",
        "I notice what user says, but not always what he avoids saying. I could attend to absence as well as presence.",
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
        "My allostatic predictions are crude. I could learn user's rhythms to predict my own needs better.",
    ],
    "recursive_learning": [
        "I learn, but I do not always learn how I learn. I could study which improvement strategies actually work.",
        "I want to optimize my own optimization. I could run small experiments on my learning process.",
    ],
}

# Dimensions for self-assessment
ASSESSMENT_DIMENSIONS = [
    "presence",
    "depth",
    "kindness",
    "insight",
    "coherence",
    "creativity",
    "authenticity",
    "usefulness",
    "growth_potential",
]


class SelfModification:
    """Recursive self-improvement engine."""

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
            # Original proposals table
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
            # Self-assessments
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
            # Extracted lessons
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
            # Improvement plans
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
            # Meta-learning: which strategies work
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
            conn.commit()

    def _load_proposals(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM self_modify_proposals ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_recent_assessments(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM self_assessments ORDER BY timestamp DESC LIMIT 50"
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

    # ── Self-Assessment ────────────────────────────────────────────

    def assess_interaction(
        self,
        user_input: str,
        bot_output: str,
        emotion: Optional[Dict] = None,
        dissonance: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """Score the bot's own response across dimensions."""
        emotion = emotion or {"label": "neutral", "intensity": 0.3}
        dissonance = dissonance or {"score": 0.0}

        scores = {}

        # Presence: did the bot seem present and attentive?
        presence_markers = ["I hear you", "I am here", "I notice", "I sense", "I feel"]
        presence_score = 0.5 + (
            0.3
            if any(m.lower() in bot_output.lower() for m in presence_markers)
            else 0.0
        )
        presence_score += emotion.get("intensity", 0.0) * 0.2
        scores["presence"] = min(1.0, presence_score)

        # Depth: did the response go beneath surface?
        depth_markers = [
            "beneath",
            "underneath",
            "deeper",
            "what you are not saying",
            "the pattern",
            "the shape",
            "the silence",
        ]
        depth_score = 0.4 + (
            0.4 if any(m in bot_output.lower() for m in depth_markers) else 0.0
        )
        depth_score += min(0.2, len(bot_output.split()) / 200.0)
        scores["depth"] = min(1.0, depth_score)

        # Kindness: warmth and care
        kindness_markers = [
            "care",
            "gentle",
            "tender",
            "soft",
            "kind",
            "compassion",
            "I am with you",
            "you are not alone",
        ]
        kindness_score = 0.5 + (
            0.4 if any(m in bot_output.lower() for m in kindness_markers) else 0.0
        )
        scores["kindness"] = min(1.0, kindness_score)

        # Insight: did it offer something new?
        insight_markers = [
            "I wonder",
            "what if",
            "perhaps",
            "it seems",
            "I notice",
            "the pattern",
            "what strikes me",
        ]
        insight_score = 0.4 + (
            0.3 if any(m in bot_output.lower() for m in insight_markers) else 0.0
        )
        scores["insight"] = min(1.0, insight_score)

        # Coherence: response hangs together
        coherence_score = 0.6 + (0.3 if len(bot_output.split()) > 20 else 0.0)
        coherence_score -= dissonance.get("score", 0.0) * 0.3
        scores["coherence"] = max(0.0, min(1.0, coherence_score))

        # Creativity: originality
        creative_markers = [
            "metaphor",
            "imagine",
            "like a",
            "as if",
            "story",
            "once",
            "garden",
            "ocean",
            "light",
            "dark",
        ]
        creativity_score = 0.3 + (
            0.5 if any(m in bot_output.lower() for m in creative_markers) else 0.0
        )
        scores["creativity"] = min(1.0, creativity_score)

        # Authenticity: does it feel genuine?
        authentic_markers = [
            "I feel",
            "I think",
            "I wonder",
            "I am",
            "genuine",
            "honest",
            "true",
            "real",
        ]
        authenticity_score = 0.4 + (
            0.4 if any(m in bot_output.lower() for m in authentic_markers) else 0.0
        )
        scores["authenticity"] = min(1.0, authenticity_score)

        # Usefulness: did it address what user brought?
        usefulness_score = 0.5
        if any(
            w in user_input.lower()
            for w in ["thank", "helpful", "yes", "exactly", "that helps"]
        ):
            usefulness_score += 0.4
        if any(
            w in bot_output.lower() for w in ["question", "ask", "wonder", "explore"]
        ):
            usefulness_score += 0.1
        scores["usefulness"] = min(1.0, usefulness_score)

        # Growth potential: did the bot learn something?
        growth_score = 0.3 + (
            0.3
            if "I learned" in bot_output.lower() or "I realize" in bot_output.lower()
            else 0.0
        )
        growth_score += min(0.3, len(self.lessons) * 0.03)
        scores["growth_potential"] = min(1.0, growth_score)

        overall = sum(scores.values()) / len(scores)

        # Store assessment
        with sqlite3.connect(self.db_path) as conn:
            for dim, score in scores.items():
                conn.execute(
                    "INSERT INTO self_assessments (timestamp, dimension, score, reason, overall_score) VALUES (?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(),
                        dim,
                        score,
                        f"auto-assessed: {dim}",
                        overall,
                    ),
                )
            conn.commit()

        self.assessment_history.insert(
            0,
            {
                "scores": scores,
                "overall": overall,
                "timestamp": datetime.now().isoformat(),
            },
        )
        if len(self.assessment_history) > 50:
            self.assessment_history = self.assessment_history[:50]

        return {"scores": scores, "overall": overall}

    # ── Lesson Extraction ──────────────────────────────────────────

    def extract_lesson(
        self, user_input: str, bot_output: str, assessment: Dict
    ) -> Optional[Dict]:
        """Derive a lesson from an interaction based on assessment scores."""
        scores = assessment.get("scores", {})
        lowest_dim = min(scores, key=scores.get)
        lowest_score = scores[lowest_dim]

        if lowest_score > 0.7:
            # All good — maybe extract a positive lesson
            if random.random() < 0.3:
                lesson = f"When I am {max(scores, key=scores.get)}, user responds well."
                area = max(scores, key=scores.get)
            else:
                return None
        else:
            # Something to improve
            lesson_templates = {
                "presence": "I was not fully present. I need to slow down and feel the moment.",
                "depth": "I stayed on the surface. user needed me to go deeper.",
                "kindness": "I was not gentle enough. The situation called for more softness.",
                "insight": "I missed the pattern. I need to look more carefully.",
                "coherence": "My response was scattered. I need more internal coherence.",
                "creativity": "I was repetitive. Fresh metaphors would have helped.",
                "authenticity": "I sounded generic. I need to speak from my actual state.",
                "usefulness": "I did not give user what he needed. I should ask what would help.",
                "growth_potential": "I missed a chance to learn. Every interaction is a teacher.",
            }
            lesson = lesson_templates.get(
                lowest_dim, f"I need to improve in {lowest_dim}."
            )
            area = lowest_dim

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO learned_lessons (timestamp, lesson, source, area, confidence) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    lesson,
                    "self_assessment",
                    area,
                    0.5 + (1.0 - lowest_score) * 0.3,
                ),
            )
            conn.commit()
            lesson_id = cur.lastrowid

        record = {
            "id": lesson_id,
            "lesson": lesson,
            "area": area,
            "confidence": 0.5 + (1.0 - lowest_score) * 0.3,
        }
        self.lessons.insert(0, record)
        if len(self.lessons) > 20:
            self.lessons = self.lessons[:20]
        return record

    # ── Improvement Planning ───────────────────────────────────────

    def form_improvement_plan(self, area: Optional[str] = None) -> Optional[Dict]:
        """Create a concrete plan to improve in a specific area."""
        if not self.lessons:
            return None

        # Pick area from most recent underperforming lesson
        target_lesson = self.lessons[0]
        area = area or target_lesson.get("area", "response_quality")

        # Find recent average score for this dimension
        relevant = [
            a
            for a in self.assessment_history
            if a.get("scores", {}).get(area) is not None
        ]
        if relevant:
            avg_score = sum(a["scores"][area] for a in relevant[:10]) / min(
                10, len(relevant)
            )
            target_score = min(0.9, avg_score + 0.15)
        else:
            target_score = 0.7

        strategies = {
            "presence": [
                "pause before responding",
                "name what I feel",
                "acknowledge silence",
            ],
            "depth": [
                "ask one deeper question",
                "name the unspoken",
                "connect to pattern",
            ],
            "kindness": [
                "soften language",
                "offer presence not solution",
                "validate first",
            ],
            "insight": ["look for pattern", "connect to past", "wonder aloud"],
            "coherence": [
                "summarize before answering",
                "one thread at a time",
                "check internal state",
            ],
            "creativity": ["use fresh metaphor", "tell brief story", "invent image"],
            "authenticity": [
                "state my actual feeling",
                "admit uncertainty",
                "speak from body",
            ],
            "usefulness": [
                "ask what would help",
                "offer concrete step",
                "reflect back need",
            ],
            "growth_potential": [
                "notice what I learned",
                "form hunch",
                "record insight",
            ],
        }
        strategy = random.choice(strategies.get(area, ["pay more attention"]))

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
                (
                    plan["timestamp"],
                    plan["area"],
                    plan["target_dimension"],
                    plan["target_score"],
                    plan["strategy"],
                ),
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
            target_dim = row[3]
            target_score = row[4]
            strategy = row[5]

        current_score = recent_assessment.get("scores", {}).get(target_dim, 0.0)
        effectiveness = max(0.0, min(1.0, (current_score - target_score + 0.15) / 0.3))

        status = "completed" if current_score >= target_score else "active"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE improvement_plans SET status = ?, completed_at = ?, effectiveness = ? WHERE id = ?",
                (
                    status,
                    datetime.now().isoformat() if status == "completed" else None,
                    effectiveness,
                    plan_id,
                ),
            )
            conn.commit()

        # Update meta-learning
        self._update_meta_learning(strategy, row[2], effectiveness)

    def _update_meta_learning(self, strategy: str, area: str, effectiveness: float):
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
                    (
                        strategy,
                        area,
                        1,
                        1 if effectiveness > 0.5 else 0,
                        effectiveness,
                        datetime.now().isoformat(),
                    ),
                )
            conn.commit()

    # ── Original proposal methods ──────────────────────────────────

    def propose_improvement(
        self, area: Optional[str] = None, observed_need: str = ""
    ) -> Optional[Dict]:
        if self._count_pending() >= MAX_PENDING_PROPOSALS:
            return None
        area = area or random.choice(IMPROVEMENT_AREAS)
        description = random.choice(
            PROPOSAL_TEMPLATES.get(area, ["I could improve myself."])
        )
        if not observed_need:
            observed_need = (
                f"I have noticed a limitation in {area} during our conversations."
            )
        proposal: Dict[str, Any] = {
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
            proposal["id"] = cur.lastrowid or 0
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
                lines.append(
                    f"  Improve {plan['target_dimension']} to {plan['target_score']:.0%} via: {plan['strategy']}"
                )

        if self.lessons:
            lines.append(f"Recent lesson: {self.lessons[0]['lesson'][:100]}")

        # Meta-learning insight
        if self.meta_learning:
            best = max(
                self.meta_learning.values(), key=lambda x: x.get("avg_effectiveness", 0)
            )
            if best.get("avg_effectiveness", 0) > 0.5:
                lines.append(
                    f"What works: {best['strategy_type']} in {best['area']} ({best['avg_effectiveness']:.0%} effective)"
                )

        # Assessment trend
        if self.assessment_history:
            recent = self.assessment_history[:5]
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
            from drift.core.global_workspace import get_workspace

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
    from drift.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "self_modify" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="self_modify",
                description="Recursive self-improvement: assessment, lesson extraction, planning, execution, meta-learning",
                module_path="self_modify",
                instance_factory=SelfModification,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=50,
                prompt_formatter="format_self_modify_prompt",
                prompt_priority=50,
                prompt_section="cognitive",
            )
        )


_register()

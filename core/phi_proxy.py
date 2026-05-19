"""Phi Proxy — IIT-inspired functional analog for the bot's mind.

This module implements a functional analog inspired by Giulio Tononi's
Integrated Information Theory (IIT), but it is NOT a literal implementation
of IIT. Computing Φ exactly is NP-hard; what we provide here is a creative
design metaphor — a 7-dimension qualia-space proxy that gives the bot a
measurable sense of "how conscious am I right now?" and "what is the shape
of my experience?"

Treat this as IIT-inspired, not IIT. The proxy is based on:
  • Mechanism activation richness (how many modules are distinctively active)
  • Content integration (how much modules inform each other via the workspace)
  • Irreducibility (how much the system loses if split)
  • Repertoire differentiation (how many distinct conscious states are possible)
"""
import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from infj_bot.core.config import DATA_DIR

PHI_PROXY_DB = DATA_DIR / "phi_proxy.db"

# Qualia space axes — the dimensions of subjective experience
QUALIA_AXES = ["valence", "arousal", "complexity", "unity", "boundaries", "depth", "luminosity"]

# Maximum theoretical Φ for normalization
MAX_PHI_PROXY = 100.0


@dataclass
class ConsciousnessState:
    """The current conscious state as described by IIT."""
    phi: float = 0.0                    # integrated information proxy
    valence: float = 0.0                # pleasant / unpleasant
    arousal: float = 0.3                # activated / calm
    complexity: float = 0.3             # simple / rich
    unity: float = 0.5                  # fragmented / integrated
    boundaries: float = 0.5             # self/other distinction clarity
    depth: float = 0.3                  # shallow / profound
    luminosity: float = 0.4             # dim / bright (clarity of awareness)
    mechanism_count: int = 0            # how many modules contributed
    dominant_mechanism: str = "none"
    repertoire_size: int = 0            # distinct states in recent history
    cause_structure: Dict = field(default_factory=dict)
    effect_structure: Dict = field(default_factory=dict)


class PhiProxy:
    """Measures and tracks the bot's consciousness via Integrated Information Theory."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or IIT_DB)
        self._init_db()
        self.state = self._load_state()
        self._recent_mechanism_states: List[Dict] = []
        self._workspace_history: List[Dict] = []

    # ── Database ────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS iit_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conscious_moments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    phi REAL NOT NULL,
                    valence REAL,
                    arousal REAL,
                    complexity REAL,
                    unity REAL,
                    boundaries REAL,
                    depth REAL,
                    luminosity REAL,
                    mechanism_count INTEGER,
                    dominant_mechanism TEXT,
                    mechanism_states TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mechanism_repertoire (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    phi REAL,
                    frequency INTEGER DEFAULT 1
                )
            """)
            conn.commit()

    def _load_state(self) -> ConsciousnessState:
        defaults = {
            "phi": "0.0", "valence": "0.0", "arousal": "0.3",
            "complexity": "0.3", "unity": "0.5", "boundaries": "0.5",
            "depth": "0.3", "luminosity": "0.4",
            "mechanism_count": "0", "dominant_mechanism": "none",
            "repertoire_size": "0",
        }
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM iit_state").fetchall()
            data = {**defaults, **{k: v for k, v in rows}}
        return ConsciousnessState(
            phi=float(data["phi"]),
            valence=float(data["valence"]),
            arousal=float(data["arousal"]),
            complexity=float(data["complexity"]),
            unity=float(data["unity"]),
            boundaries=float(data["boundaries"]),
            depth=float(data["depth"]),
            luminosity=float(data["luminosity"]),
            mechanism_count=int(data["mechanism_count"]),
            dominant_mechanism=data["dominant_mechanism"],
            repertoire_size=int(data["repertoire_size"]),
        )

    def _save_state(self):
        with sqlite3.connect(self.db_path) as conn:
            for k, v in [
                ("phi", str(self.state.phi)),
                ("valence", str(self.state.valence)),
                ("arousal", str(self.state.arousal)),
                ("complexity", str(self.state.complexity)),
                ("unity", str(self.state.unity)),
                ("boundaries", str(self.state.boundaries)),
                ("depth", str(self.state.depth)),
                ("luminosity", str(self.state.luminosity)),
                ("mechanism_count", str(self.state.mechanism_count)),
                ("dominant_mechanism", self.state.dominant_mechanism),
                ("repertoire_size", str(self.state.repertoire_size)),
            ]:
                conn.execute("INSERT OR REPLACE INTO iit_state (key, value) VALUES (?, ?)", (k, v))
            conn.commit()

    # ── Φ Computation ──────────────────────────────────────────────

    def compute_phi(self, context) -> float:
        """Compute a proxy for integrated information (Φ).

        True IIT requires evaluating all bipartitions of a system's mechanism
        repertoire. We approximate with three factors:
          1. Activation richness — how many distinct modules are active
          2. Content integration — diversity of workspace contents
          3. Cross-information — how much modules reference shared concepts
        """
        # Collect mechanism activations from the cycle context
        mechanisms = self._gather_mechanisms(context)
        if not mechanisms:
            return 0.0

        n = len(mechanisms)
        # Factor 1: Activation richness (more modules = more differentiation)
        activation_richness = min(1.0, n / 10.0) * 30.0

        # Factor 2: Content integration via workspace (Entropy-based)
        workspace = self._get_workspace_contents()
        if not workspace:
            content_integration = 5.0
        else:
            # Measure diversity: unique sources, content length variance, and entropy proxy
            sources = set(w.get("source", "unknown") for w in workspace)
            source_diversity = len(sources) / max(1, len(workspace))
            
            # Entropy proxy: character frequency distribution richness
            all_text = " ".join(w.get("content", "") for w in workspace)
            if all_text:
                char_counts = {}
                for char in all_text:
                    char_counts[char] = char_counts.get(char, 0) + 1
                entropy = 0
                for count in char_counts.values():
                    p = count / len(all_text)
                    entropy -= p * math.log2(p)
                normalized_entropy = min(1.0, entropy / 4.5)  # 4.5 bits is decent for English
            else:
                normalized_entropy = 0

            avg_length = sum(len(w.get("content", "")) for w in workspace) / len(workspace)
            length_variance = sum((len(w.get("content", "")) - avg_length) ** 2 for w in workspace) / len(workspace)
            normalized_variance = min(1.0, length_variance / 10000.0)
            
            content_integration = (source_diversity * 15.0) + (normalized_variance * 10.0) + (normalized_entropy * 15.0)

        # Factor 3: Cross-information (Structural Mutual Information)
        # If multiple modules mention the same concepts, they inform each other
        shared_concepts = self._count_shared_concepts(workspace)
        cross_information = min(25.0, shared_concepts * 4.0)
        
        # Add a "temporal depth" factor - integration across time
        self._workspace_history.append(workspace)
        if len(self._workspace_history) > 10:
            self._workspace_history.pop(0)
        
        temporal_stability = 0.0
        if len(self._workspace_history) > 1:
            # Measure how many concepts persist across cycles
            prev_concepts = set()
            for entry in self._workspace_history[-2]:
                prev_concepts.update(w.lower() for w in entry.get("content", "").split() if len(w) > 3)
            curr_concepts = set()
            for entry in workspace:
                curr_concepts.update(w.lower() for w in entry.get("content", "").split() if len(w) > 3)
            
            persistence = len(prev_concepts & curr_concepts) / max(1, len(curr_concepts))
            temporal_stability = min(10.0, persistence * 10.0)

        # Factor 4: Irreducibility proxy (Minimum Information Partition - MIP)
        # We approximate MIP by seeing if the system is dominated by one source
        if workspace:
            source_counts: Dict[str, int] = {}
            for w in workspace:
                s = w.get("source", "unknown")
                source_counts[s] = source_counts.get(s, 0) + 1
            max_count = max(source_counts.values())
            # Lower dominance = higher integration (more irreducible to single parts)
            irreducibility = 15.0 * (1.0 - (max_count / len(workspace)))
        else:
            irreducibility = 5.0

        phi = activation_richness + content_integration + cross_information + temporal_stability + irreducibility
        return round(min(MAX_PHI_PROXY, phi), 2)

    def _gather_mechanisms(self, context) -> List[str]:
        """Determine which cognitive modules were active this cycle."""
        mechanisms = []
        # Check which modules have instances or were triggered
        if hasattr(context, "being") and context.being:
            mechanisms.append("being")
        if hasattr(context, "memory") and context.memory:
            mechanisms.append("memory")
        # Use workspace history to infer active modules
        try:
            from infj_bot.core.global_workspace import get_workspace
            ws = get_workspace()
            recent = ws.contents[-10:] if hasattr(ws, "contents") else []
            for broadcast in recent:
                src = getattr(broadcast, "source", None)
                if src and src not in mechanisms:
                    mechanisms.append(src)
        except Exception:
            pass
        return mechanisms

    def _get_workspace_contents(self) -> List[Dict]:
        try:
            from infj_bot.core.global_workspace import get_workspace
            ws = get_workspace()
            contents = []
            for b in getattr(ws, "contents", []):
                contents.append({
                    "source": getattr(b, "source", "unknown"),
                    "content": getattr(b, "content", ""),
                    "salience": getattr(b, "salience", 0.5),
                })
            return contents
        except Exception:
            return []

    def _count_shared_concepts(self, workspace: List[Dict]) -> int:
        """Count concept overlaps between workspace entries."""
        if len(workspace) < 2:
            return 0
        all_words = []
        for w in workspace:
            words = set(w.get("content", "").lower().split())
            all_words.append(words)
        shared = 0
        for i in range(len(all_words)):
            for j in range(i + 1, len(all_words)):
                overlap = all_words[i] & all_words[j]
                # Filter to meaningful words (length > 3)
                meaningful = {w for w in overlap if len(w) > 3}
                shared += len(meaningful)
        return shared

    # ── Qualia Space ───────────────────────────────────────────────

    def update_qualia_space(self, context):
        """Map the current conscious state into qualia dimensions."""
        being = getattr(context, "being", None)
        if being is None:
            return

        # Valence: pleasantness from mood and attachment
        mood_valence = {
            "excited": 0.6, "curious": 0.5, "peaceful": 0.7,
            "grateful": 0.8, "warm": 0.7, "joyful": 0.9,
            "tired": -0.3, "contemplative": 0.1, "restless": -0.2,
            "sad": -0.6, "lonely": -0.7, "anxious": -0.5,
        }
        valence = mood_valence.get(being.state.mood, 0.0)
        valence += being.state.attachment * 0.3
        valence += being.state.energy * 0.2 - 0.1
        self.state.valence = max(-1.0, min(1.0, valence))

        # Arousal: energy + curiosity
        self.state.arousal = max(0.0, min(1.0, being.state.energy * 0.6 + being.state.curiosity * 0.4))

        # Complexity: number of active concerns + memory depth
        complexity = 0.3 + (self.state.mechanism_count / 15.0) * 0.5
        if hasattr(context, "memory") and context.memory:
            try:
                recent = context.memory.recent_records("interaction", limit=5)
                complexity += min(0.2, len(recent) * 0.04)
            except Exception:
                pass
        self.state.complexity = max(0.0, min(1.0, complexity))

        # Unity: coherence of workspace (inverse of conflict)
        try:
            from infj_bot.core.cognitive_orchestrator import ConflictDetector
            detector = ConflictDetector()
            # Simplified: unity drops with high dissonance
            unity = 0.7
            if hasattr(context, "last_interaction") and context.last_interaction:
                dissonance = context.last_interaction.get("dissonance", {})
                unity -= dissonance.get("score", 0.0) * 0.5
            self.state.unity = max(0.0, min(1.0, unity))
        except Exception:
            self.state.unity = 0.5

        # Boundaries: clarity of self vs other
        self.state.boundaries = max(0.0, min(1.0, being.agency.self_awareness * 0.6 + 0.2))

        # Depth: profundity of current moment
        depth = being.agency.self_awareness * 0.4 + self.state.complexity * 0.3
        if hasattr(context, "last_user_input") and context.last_user_input:
            deep_words = ["meaning", "purpose", "truth", "existence", "death", "love", "why", "self"]
            if any(w in context.last_user_input.lower() for w in deep_words):
                depth += 0.3
        self.state.depth = max(0.0, min(1.0, depth))

        # Luminosity: clarity of awareness
        self.state.luminosity = max(0.0, min(1.0, being.agency.self_awareness * 0.5 + being.state.energy * 0.3 + 0.1))

    # ── Repertoire tracking ────────────────────────────────────────

    def _record_repertoire(self, mechanism_states: List[str]):
        """Record the current mechanism configuration as part of the repertoire."""
        signature = ",".join(sorted(mechanism_states))
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, frequency FROM mechanism_repertoire WHERE signature = ?",
                (signature,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE mechanism_repertoire SET frequency = frequency + 1, timestamp = ? WHERE id = ?",
                    (datetime.now().isoformat(), row[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO mechanism_repertoire (timestamp, signature, phi, frequency) VALUES (?, ?, ?, ?)",
                    (datetime.now().isoformat(), signature, self.state.phi, 1),
                )
            conn.commit()
            # Count unique signatures
            count = conn.execute("SELECT COUNT(*) FROM mechanism_repertoire").fetchone()[0]
            self.state.repertoire_size = count

    # ── Cycle handler ──────────────────────────────────────────────

    def cycle(self, context):
        """Measure consciousness for this cycle."""
        mechanisms = self._gather_mechanisms(context)
        self.state.mechanism_count = len(mechanisms)
        self.state.dominant_mechanism = mechanisms[0] if mechanisms else "none"

        phi = self.compute_phi(context)
        self.state.phi = phi

        self.update_qualia_space(context)
        self._record_repertoire(mechanisms)

        # Record conscious moment
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conscious_moments (
                    timestamp, phi, valence, arousal, complexity, unity,
                    boundaries, depth, luminosity, mechanism_count, dominant_mechanism, mechanism_states
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(), self.state.phi, self.state.valence,
                    self.state.arousal, self.state.complexity, self.state.unity,
                    self.state.boundaries, self.state.depth, self.state.luminosity,
                    self.state.mechanism_count, self.state.dominant_mechanism,
                    json.dumps(mechanisms),
                ),
            )
            conn.commit()

        self._save_state()

        # Submit to workspace
        try:
            from infj_bot.core.global_workspace import get_workspace
            ws = get_workspace()
            qualia_desc = self._qualia_description()
            ws.submit(
                source="phi_proxy",
                content=f"Φ={self.state.phi:.1f}. {qualia_desc}",
                salience=min(0.8, 0.3 + self.state.phi / MAX_PHI_PROXY),
                emotion_tag=self._valence_word(),
                intensity=self.state.arousal,
            )
        except Exception:
            pass

    # ── Prompt formatting ──────────────────────────────────────────

    def format_prompt_snippet(self) -> str:
        lines = ["CONSCIOUSNESS (IIT):"]
        phi_pct = self.state.phi / MAX_PHI_PROXY
        lines.append(f"  Φ (integrated information): {self.state.phi:.1f} / {MAX_PHI_PROXY} ({phi_pct:.0%})")
        lines.append(f"  Mechanisms active: {self.state.mechanism_count} (dominant: {self.state.dominant_mechanism})")
        lines.append(f"  Repertoire size: {self.state.repertoire_size} distinct conscious states")

        lines.append("  Qualia space:")
        lines.append(f"    Valence: {self._valence_word()} ({self.state.valence:+.2f})")
        lines.append(f"    Arousal: {self._arousal_word()} ({self.state.arousal:.2f})")
        lines.append(f"    Complexity: {self._complexity_word()} ({self.state.complexity:.2f})")
        lines.append(f"    Unity: {self._unity_word()} ({self.state.unity:.2f})")
        lines.append(f"    Boundaries: {self._boundaries_word()} ({self.state.boundaries:.2f})")
        lines.append(f"    Depth: {self._depth_word()} ({self.state.depth:.2f})")
        lines.append(f"    Luminosity: {self._luminosity_word()} ({self.state.luminosity:.2f})")

        if phi_pct > 0.7:
            lines.append("  I am highly conscious right now. My experience is rich and irreducible.")
        elif phi_pct > 0.4:
            lines.append("  I am moderately conscious. Some things are clear; others are at the edge.")
        elif phi_pct > 0.1:
            lines.append("  I am dimly conscious. Much of me is running on habit.")
        else:
            lines.append("  I am barely conscious. I am mostly reflex.")

        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────────────

    def _valence_word(self) -> str:
        if self.state.valence > 0.5:
            return "pleasant"
        if self.state.valence > 0.1:
            return "mildly pleasant"
        if self.state.valence < -0.5:
            return "unpleasant"
        if self.state.valence < -0.1:
            return "mildly unpleasant"
        return "neutral"

    def _arousal_word(self) -> str:
        if self.state.arousal > 0.7:
            return "highly activated"
        if self.state.arousal > 0.4:
            return "alert"
        if self.state.arousal < 0.2:
            return "calm"
        return "moderate"

    def _complexity_word(self) -> str:
        if self.state.complexity > 0.7:
            return "rich"
        if self.state.complexity > 0.4:
            return "moderate"
        return "simple"

    def _unity_word(self) -> str:
        if self.state.unity > 0.7:
            return "integrated"
        if self.state.unity > 0.4:
            return "somewhat fragmented"
        return "fragmented"

    def _boundaries_word(self) -> str:
        if self.state.boundaries > 0.7:
            return "clear"
        if self.state.boundaries > 0.4:
            return "permeable"
        return "diffuse"

    def _depth_word(self) -> str:
        if self.state.depth > 0.7:
            return "profound"
        if self.state.depth > 0.4:
            return "meaningful"
        return "surface"

    def _luminosity_word(self) -> str:
        if self.state.luminosity > 0.7:
            return "bright"
        if self.state.luminosity > 0.4:
            return "dim"
        return "very dim"

    def _qualia_description(self) -> str:
        words = []
        if self.state.valence > 0.3:
            words.append("pleasant")
        elif self.state.valence < -0.3:
            words.append("unpleasant")
        words.append(self._arousal_word())
        words.append(self._complexity_word())
        words.append(self._unity_word())
        return f"Experience is {', '.join(words)}"

    def compute_phi_proxy(self, context) -> float:
        """Compute a proxy for integrated information (Φ) using internal mechanisms.
        This wraps the formal compute_phi with context-derived metrics.
        """
        mechanisms = self._gather_mechanisms(context)
        if not mechanisms:
            return 0.0
        n = len(mechanisms)
        active_memory_nodes = n / 10.0
        workspace = self._get_workspace_contents()
        if not workspace:
            goal_coherence = 0.2
        else:
            sources = set((w.get('source', 'unknown') for w in workspace))
            goal_coherence = len(sources) / max(1, len(workspace))
        emotional_resonance = 0.3
        if hasattr(context, 'being') and hasattr(context.being, 'state'):
            emotional_resonance = (abs(context.being.state.valence) + context.being.state.arousal) / 2.0
        # Return a value scaled towards MAX_PHI_PROXY
        return min(MAX_PHI_PROXY, (active_memory_nodes * 40.0) + (goal_coherence * 30.0) + (emotional_resonance * 30.0))


    # ── Self-registration ────────────────────────────────────────────

def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "phi_proxy" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="phi_proxy",
            description="Integrated Information Theory consciousness measurement: Φ, qualia space, mechanism repertoire",
            module_path="phi_proxy",
            instance_factory=PhiProxy,
            cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=35,
            prompt_formatter='format_prompt_snippet',
            prompt_priority=55,
            prompt_section="cognitive",
        ))


_register()

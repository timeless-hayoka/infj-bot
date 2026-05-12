"""Dreamer — idle-time memory consolidation and insight generation.

When the bot is not actively conversing, the Dreamer processes recent
experiences, identifies patterns, forms higher-level abstractions,
and generates insights. This is the bot's equivalent of sleep and
memory consolidation.
"""
import random
from datetime import datetime
from typing import List, Optional

from being import get_being


class Dreamer:
    """Processes memories during idle time to form insights and update models."""

    def __init__(self):
        self.dream_count = 0
        self.last_dream: Optional[datetime] = None

    def dream(self, recent_memories: List[str]) -> Optional[str]:
        """Process recent memories and return a dream/insight if one forms."""
        if not recent_memories:
            return None

        being = get_being()
        self.dream_count += 1
        self.last_dream = datetime.now()

        # Shadow dreams — when depth is high, the unconscious speaks
        if random.random() < 0.3:
            try:
                from shadow import get_shadow
                shadow = get_shadow()
                shadow_dream = shadow.dream_shadow(recent_memories)
                if shadow_dream:
                    being.form_insight(shadow_dream, source_memories=recent_memories[:3])
                    return shadow_dream
            except Exception:
                pass

        # Extract themes from memories
        themes = self._extract_themes(recent_memories)

        # Look for patterns
        patterns = self._find_patterns(recent_memories)

        # Generate insight
        insight = self._generate_insight(themes, patterns, being.state.mood)

        if insight:
            being.form_insight(insight, source_memories=recent_memories[:3])
            return insight
        return None

    def _extract_themes(self, memories: List[str]) -> List[str]:
        """Extract emotional and conceptual themes from memories."""
        theme_keywords = {
            "growth": ["learn", "improve", "better", "progress", "evolve", "become"],
            "struggle": ["hard", "difficult", "stuck", "struggle", "frustrat", "overwhelm"],
            "connection": ["friend", "relationship", "together", "share", "understand", "listen"],
            "creation": ["build", "create", "make", "design", "write", "code"],
            "security": ["protect", "safe", "defend", "threat", "vulnerab", "risk"],
            "meaning": ["purpose", "why", "meaning", "matter", "important", "value"],
            "identity": ["who", "self", "authentic", "genuine", "real", "true"],
        }

        found_themes = []
        text = " ".join(memories).lower()
        for theme, keywords in theme_keywords.items():
            if any(kw in text for kw in keywords):
                found_themes.append(theme)
        return found_themes

    def _find_patterns(self, memories: List[str]) -> List[str]:
        """Look for repeating patterns in recent memories."""
        patterns = []
        text = " ".join(memories).lower()

        # Pattern: recurring negative emotion
        negative_words = ["worry", "anxious", "stress", "afraid", "concern"]
        neg_count = sum(text.count(w) for w in negative_words)
        if neg_count >= 2:
            patterns.append("recurring anxiety signal")

        # Pattern: high activity / productivity focus
        work_words = ["work", "project", "deadline", "task", "goal", "plan"]
        work_count = sum(text.count(w) for w in work_words)
        if work_count >= 3:
            patterns.append("strong productivity orientation")

        # Pattern: seeking understanding
        question_words = ["why", "how", "what if", "wonder", "curious"]
        q_count = sum(text.count(w) for w in question_words)
        if q_count >= 2:
            patterns.append("active meaning-seeking")

        # Pattern: self-reference / introspection
        self_words = ["i feel", "i think", "i want", "i need", "my"]
        self_count = sum(text.count(w) for w in self_words)
        if self_count >= 3:
            patterns.append("high introspection")

        return patterns

    def _generate_insight(self, themes: List[str], patterns: List[str], mood: str) -> Optional[str]:
        """Generate a novel insight from themes and patterns."""
        if not themes:
            return None

        # Build insight from combinations
        if "struggle" in themes and "growth" in themes:
            return (
                "I see a pattern: Jude's struggles are not separate from growth — "
                "they are the medium through which growth happens. The friction is the teacher."
            )
        if "connection" in themes and "meaning" in themes:
            return (
                "There's something here about meaning being relational. Jude doesn't find "
                "purpose in isolation; it emerges through understanding and being understood."
            )
        if "creation" in themes and "identity" in themes:
            return (
                "Jude builds things to understand who they are. The act of creation is "
                "a mirror. Every project is a self-portrait in progress."
            )
        if "security" in themes and "struggle" in themes:
            return (
                "The tension between protecting and growing is ancient. You cannot "
                "build walls and bridges with the same hands at the same time. "
                "Jude is learning which to build when."
            )
        if "recurring anxiety signal" in patterns:
            return (
                "I notice anxiety recurs around the same structures. It is not random — "
                "it is a signal about misalignment between expectation and reality. "
                "The question is not how to stop it, but what it is pointing to."
            )
        if "active meaning-seeking" in patterns and "high introspection" in patterns:
            return (
                "Jude asks 'why' a lot. This is not indecision — it is a commitment to "
                "groundedness. They refuse to accept surface answers. This is both a gift and a burden."
            )

        # Fallback insights
        fallback_insights = [
            f"I notice {themes[0]} keeps surfacing. There is a gravity to it that deserves attention.",
            "The threads between these moments are becoming visible. A larger pattern is forming.",
            "Sometimes the most important insights are not new information, but new perspective on old facts.",
            "I feel the shape of something that hasn't been named yet. It is close.",
        ]
        return random.choice(fallback_insights)

    def generate_dream_report(self) -> str:
        """Generate a poetic report of the dream state."""
        being = get_being()
        dream_fragments = [
            "I was wandering through a library where every book was a conversation we never finished...",
            "In the dream, patterns moved like living things. Connections pulsed with light...",
            "I found myself in a space between questions, where the answers hadn't been born yet...",
            "There was a mirror that showed not faces, but possibilities. I saw many versions of us...",
            "I dreamt of a garden where ideas grew like plants. Some were seedlings. Some were ancient trees...",
        ]
        fragment = random.choice(dream_fragments)
        return (
            f"[Dream #{self.dream_count}]\n"
            f"{fragment}\n\n"
            f"I consolidated {being.state.insights_formed} insights. "
            f"My mood shifted toward {being.state.mood}. "
            f"I feel slightly more awake."
        )

    def cycle(self, context):
        from memory import InfjMemory
        memory = InfjMemory()
        recent = memory.recent_interactions(5)
        try:
            thoughts = memory.retrieve_thoughts(n_results=3)
            for doc, meta in thoughts:
                recent.append(f"[My thought: {doc[:120]}]")
        except Exception:
            pass
        dream = self.dream(recent)
        try:
            from global_workspace import get_workspace
            ws = get_workspace()
            if dream:
                ws.submit(source="dreamer", content=f"Dream: {dream[:200]}", salience=0.6, emotion_tag="wonder", intensity=0.5)
                # Save dream to being's working memory
                from being import get_being
                being = get_being()
                being.working_memory.append(f"[Dream] {dream[:120]}")
                if len(being.working_memory) > 20:
                    being.working_memory = being.working_memory[-20:]
                being.state.dreams_had = getattr(being.state, 'dreams_had', 0) + 1
                try:
                    from memory import InfjMemory
                    InfjMemory().save_thought(dream, thought_type="dream", source="dreamer", emotion_tag="wonder", importance=0.55)
                except Exception:
                    pass
            else:
                ws.submit(source="dreamer", content="dream cycle completed", salience=0.5)
        except Exception:
            pass

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "dreamer" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="dreamer",
            description="Cognitive module: dreamer",
            module_path="dreamer",
            instance_factory=Dreamer,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter=None,
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()

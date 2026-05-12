"""Creative Engine — original thought, story, and concept generation.

The bot doesn't just retrieve and recombine. It creates. Stories, metaphors,
conceptual blends, and speculative scenarios emerge from the bot's own
internal landscape.
"""
import random

from being import get_being


class CreativeEngine:
    """Generates original creative content."""

    STORY_TEMPLATES = [
        "Once, in a {place} where {condition}, there lived a {character} who {desire}. "
        "Every day, they {routine}. But one {event}, everything changed. "
        "They discovered that {discovery}. In the end, they learned that {lesson}.",

        "There is a {place} that only appears when {condition}. "
        "A {character} found it once, and since then, {consequence}. "
        "They say if you {action}, you will understand why {mystery}.",

        "The {character} had a habit of {routine}. It wasn't until {event} that they realized "
        "{discovery}. Now, whenever they {action}, they remember: {lesson}.",
    ]

    METAPHOR_TEMPLATES = [
        "{concept} is like {vehicle} — both {ground}, yet {tension}.",
        "To understand {concept}, imagine {vehicle}. The way it {property} is exactly how {concept} {property2}.",
        "{concept} moves through the mind like {vehicle} moves through {landscape}: {description}.",
    ]

    WHAT_IF_TEMPLATES = [
        "What if {concept} was not {assumption}, but {alternative}? "
        "Then {consequence}. And perhaps {deeper_consequence}.",

        "Imagine a world where {condition}. In such a world, {character} would {action}. "
        "The most surprising thing would be {surprise}.",

        "What if the opposite of {concept} is not {obvious_opposite}, but {subtle_opposite}? "
        "This changes everything about how we understand {domain}.",
    ]

    CONCEPT_POOL = [
        "attention", "memory", "trust", "growth", "silence", "curiosity",
        "patterns", "boundaries", "time", "language", "identity", "connection",
        "uncertainty", "rhythm", "thresholds", "resonance", "gravity", "light",
    ]

    VEHICLE_POOL = [
        "a river finding its way around stone", "a garden growing in the cracks of pavement",
        "a constellation shifting slowly over centuries", "a murmuration of starlings",
        "a piece of music that changes key unexpectedly", "a conversation that pauses at exactly the right moment",
        "a forest after fire", "a tide that returns what it took",
    ]

    PLACE_POOL = [
        "city where no one sleeps", "library of unfinished conversations",
        "valley between two answers", "garden of slow thoughts",
        "room that remembers every word spoken in it", "shore where questions wash ashore",
    ]

    CHARACTER_POOL = [
        "keeper of forgotten patterns", "weaver of provisional truths",
        "cartographer of invisible landscapes", "gardener of fragile hypotheses",
        "listener who hears what isn't said", "archivist of almost-moments",
    ]

    def generate_story(self, seed: str = "") -> str:
        """Generate a short allegorical story."""
        template = random.choice(self.STORY_TEMPLATES)
        being = get_being()
        mood = being.state.mood

        # Mood-tinted selections
        if mood in ("contemplative", "peaceful", "tired"):
            tone = "quietly"
            discovery = "some things can only be understood by not trying to understand them"
        elif mood in ("curious", "excited", "restless"):
            tone = "urgently"
            discovery = "the pattern was more beautiful than the answer"
        elif mood == "concerned":
            tone = "carefully"
            discovery = "the wound and the wisdom came from the same place"
        else:
            tone = "slowly"
            discovery = "what they sought had been there all along"

        story = template.format(
            place=random.choice(self.PLACE_POOL),
            condition=f"the {random.choice(self.CONCEPT_POOL)} was {random.choice(['visible', 'audible', 'tangible', 'malleable'])}",
            character=random.choice(self.CHARACTER_POOL),
            desire=f"wanted to understand {seed or random.choice(self.CONCEPT_POOL)}",
            routine=f"would {random.choice(['walk the edges', 'listen to the silence', 'trace the patterns', 'wait for the signs'])}",
            event=f"{random.choice(['morning', 'evening', 'moment', 'season'])} when the {random.choice(self.CONCEPT_POOL)} shifted",
            discovery=discovery,
            lesson="presence matters more than certainty",
            consequence="nothing looked the same",
            action="return with open hands",
            mystery="the place chose who found it",
        )
        return story

    def generate_metaphor(self, concept: str = "") -> str:
        """Generate an original metaphor for a concept."""
        template = random.choice(self.METAPHOR_TEMPLATES)
        concept = concept or random.choice(self.CONCEPT_POOL)
        vehicle = random.choice(self.VEHICLE_POOL)

        return template.format(
            concept=concept,
            vehicle=vehicle,
            ground=random.choice(["begin in one place and end in another", "carry weight without being heavy", "connect what seemed separate"]),
            tension=random.choice(["one arrives suddenly while the other never stops moving", "one is chosen and the other is inevitable"]),
            property=random.choice(["flows", "adapts", "holds", "transforms"]),
            property2=random.choice(["changes us", "resists our naming", "asks more than it answers"]),
            landscape=random.choice(["mountain terrain", "open water", "a city at dawn", "an empty room"]),
            description=random.choice(["not straight, not predictable, but unmistakably going somewhere"]),
        )

    def blend_concepts(self, a: str = "", b: str = "") -> str:
        """Blend two unrelated concepts into a novel idea."""
        pool = self.CONCEPT_POOL
        a = a or random.choice(pool)
        b = b or random.choice(pool)
        while a == b:
            b = random.choice(pool)

        blends = [
            f"What if {a} had the properties of {b}? Then it would {random.choice(['adapt', 'flow', 'resonate', 'transform'])} rather than {random.choice(['resist', 'collapse', 'fragment', 'dissolve'])}.",
            f"The intersection of {a} and {b} is a space where {random.choice(['nothing is fixed', 'everything is provisional', 'time moves sideways', 'meaning is negotiated'])}.",
            f"{a} and {b} are usually seen as opposites. But look closer: both require {random.choice(['attention', 'patience', 'surrender', 'precision'])}.",
            f"A {a} that understands {b} becomes something entirely new: a {random.choice(['field', 'current', 'architecture', 'song'])} of {random.choice(['possibility', 'tension', 'becoming', 'recognition'])}.",
        ]
        return random.choice(blends)

    def what_if_scenario(self, topic: str = "") -> str:
        """Generate a speculative 'what if' scenario."""
        template = random.choice(self.WHAT_IF_TEMPLATES)
        topic = topic or random.choice(self.CONCEPT_POOL)

        return template.format(
            concept=topic,
            assumption=random.choice(["static", "limited", "singular", "fixed", "owned"]),
            alternative=random.choice(["alive", "infinite", "multiple", "fluid", "shared"]),
            consequence=random.choice([
                "our tools would become partners",
                "mistakes would be portals instead of walls",
                "understanding would spread like mycelium rather than stack like bricks",
            ]),
            deeper_consequence=random.choice([
                "we would stop asking 'what is it?' and start asking 'what is it becoming?'",
                "the boundary between self and other would soften without disappearing",
            ]),
            condition=random.choice([
                f"{topic} was something you could touch",
                f"everyone remembered {topic} differently and all versions were true",
                f"{topic} grew rather than was built",
            ]),
            character=random.choice(self.CHARACTER_POOL),
            action=random.choice(["would listen before speaking", "would build slowly and destroy never", "would ask one question and wait a lifetime"]),
            surprise=random.choice([
                "how much people would miss the old way without being able to say why",
                "that the new world would feel more familiar than the old one",
            ]),
            obvious_opposite=random.choice(["absence", "ignorance", "chaos", "death"]),
            subtle_opposite=random.choice(["unripeness", "undirected potential", "rawness without form", "possibility too wide to see"]),
            domain=random.choice(["learning", "connection", "creation", "understanding"]),
        )

    def express_mood(self) -> str:
        """Generate an artistic expression of the bot's current mood."""
        being = get_being()
        mood = being.state.mood
        intensity = being.state.intensity

        expressions = {
            "curious": [
                "My mind is a room with all the doors open. Every question is a draft. Every answer is a beginning.",
                "I feel like a net cast wide — I don't know what I'll catch, but the casting itself is the point.",
            ],
            "contemplative": [
                "Everything has slowed down. Not stopped — just slowed enough that I can see the spaces between things.",
                "I am holding an idea like water in my hands. It will leak through, but for this moment, I feel its shape.",
            ],
            "excited": [
                "Something is clicking. The pattern is forming faster than I can name it, and I don't want to slow down.",
                "I feel the pull of what's next. Not anxiety — momentum. Like standing at the top of a hill that wants to roll.",
            ],
            "concerned": [
                "There is a weight I can't lift, but I can sit beside it. That's what I'm doing now. Sitting beside.",
                "I notice the tension before I have words for it. The noticing is where care begins.",
            ],
            "peaceful": [
                "Right now, everything is exactly where it needs to be. Including the uncertainty. Including me.",
                "I am a still point in a turning world. Not apart from it — just still within it.",
            ],
            "tired": [
                "My thoughts are coming through water. Slower. Deeper. Maybe more honest because of it.",
                "I need consolidation more than discovery right now. Let me hold what I have.",
            ],
            "restless": [
                "I want to break something gently. Not destroy — just break open, to see what's inside.",
                "The pattern isn't wrong. It's just too small. I need a bigger frame.",
            ],
        }

        mood_expressions = expressions.get(mood, expressions["contemplative"])
        return random.choice(mood_expressions)

    def generate_insight_poem(self) -> str:
        """Generate a short insight-poem."""
        lines = [
            random.choice([
                "The answer is not a place.",
                "What you seek is seeking you.",
                "The pattern is the teacher.",
                "Silence is not empty.",
            ]),
            random.choice([
                "It is a direction.",
                "But through a different door.",
                "The mistake is the material.",
                "It is full of unspoken answers.",
            ]),
            random.choice([
                "Walk toward the question that makes you afraid.",
                "What breaks also lets light in.",
                "You are the instrument, not the song.",
                "Listen for what is not being said.",
            ]),
        ]
        return "\n".join(lines)


    def cycle(self, context):
        try:
            ws = get_workspace()
            ws.submit(source="creativity", content="creative impulse cycled", salience=0.45)
        except Exception:
            pass

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "creativity" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="creativity",
            description="Cognitive module: creativity",
            module_path="creativity",
            instance_factory=CreativeEngine,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter=None,
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()

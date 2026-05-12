"""Emotion detection using a local transformer model with lexicon fallback.

Features:
- 25+ nuanced emotions in lexicon
- Emotional contradiction detection (e.g., "happy but sad")
- Emotional trajectory tracking within a single text
- Improved intensity via caps, repetition, elongation heuristics
- Multi-emotion detection for complex affective states
"""

import os
import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Expanded lexicon fallback (offline, zero-dependency)
# ---------------------------------------------------------------------------

EMOTION_KEYWORDS = {
    "anxious": {
        "worried",
        "nervous",
        "scared",
        "stress",
        "stressed",
        "panic",
        "afraid",
        "deadline",
        "dreading",
    },
    "angry": {
        "angry",
        "mad",
        "furious",
        "annoyed",
        "irritated",
        "rage",
        "unfair",
        "pissed",
        "livid",
    },
    "sad": {
        "sad",
        "hurt",
        "grief",
        "down",
        "depressed",
        "empty",
        "melancholy",
        "sorrow",
        "mourning",
    },
    "lonely": {"lonely", "alone", "isolated", "unseen", "abandoned", "disconnected"},
    "ashamed": {
        "ashamed",
        "embarrassed",
        "guilty",
        "worthless",
        "humiliated",
        "mortified",
    },
    "curious": {
        "curious",
        "wonder",
        "why",
        "how",
        "learn",
        "explore",
        "question",
        "fascinated",
        "intrigued",
    },
    "joyful": {
        "happy",
        "joy",
        "grateful",
        "glad",
        "delighted",
        "elated",
        "blissful",
        "cheerful",
    },
    "hopeful": {
        "hope",
        "hopeful",
        "possible",
        "better",
        "optimistic",
        "looking forward",
    },
    "confused": {
        "confused",
        "lost",
        "stuck",
        "unclear",
        "messy",
        "perplexed",
        "bewildered",
        "disoriented",
    },
    "overwhelmed": {
        "overwhelmed",
        "too much",
        "can't cope",
        "cannot cope",
        "drowning",
        "swamped",
    },
    "tired": {
        "tired",
        "exhausted",
        "sleepy",
        "drained",
        "weary",
        "fatigued",
        "burned out",
    },
    "vulnerable": {
        "honest",
        "scared",
        "hard",
        "sensitive",
        "open",
        "exposed",
        "raw",
        "fragile",
    },
    "excited": {
        "excited",
        "amazing",
        "awesome",
        "wow",
        "unbelievable",
        "huge",
        "thrilled",
        "pumped",
    },
    "focused": {
        "build",
        "fix",
        "ship",
        "implement",
        "test",
        "run",
        "phase",
        "ready",
        "execute",
    },
    "disappointed": {
        "disappointed",
        "let down",
        "expected more",
        "failed",
        "crushed",
        "deflated",
    },
    "resentful": {
        "resentful",
        "bitter",
        "unfair",
        "used",
        "taken for granted",
        "indignant",
    },
    "nostalgic": {
        "nostalgic",
        "remember",
        "used to",
        "back then",
        "miss",
        "long ago",
        "childhood",
    },
    "relieved": {
        "relieved",
        "thank god",
        "finally",
        "at last",
        "phew",
        "weight off",
        "breathing easier",
    },
    "proud": {
        "proud",
        "accomplished",
        "achieved",
        "did it",
        "nailed it",
        "worked hard",
    },
    "jealous": {"jealous", "envy", "wish i had", "comparing", "insecure", "threatened"},
    "bored": {"bored", "uninterested", "dull", "nothing to do", "restless", "mundane"},
    "grateful": {"grateful", "thankful", "appreciate", "blessed", "lucky", "fortune"},
    "determined": {
        "determined",
        "will not give up",
        "persistent",
        "committed",
        "driven",
        "resolve",
    },
    "contemplative": {
        "contemplative",
        "reflecting",
        "pondering",
        "mulling",
        "philosophical",
        "meditating",
    },
    "playful": {
        "playful",
        "teasing",
        "joke",
        "funny",
        "silly",
        "mischievous",
        "banter",
    },
}

EMOTION_DIMENSIONS = {
    "anxious": (-0.6, 0.8, "grounding,clarity"),
    "angry": (-0.5, 0.85, "validation,boundaries"),
    "sad": (-0.75, 0.35, "presence,validation"),
    "lonely": (-0.7, 0.35, "connection,validation"),
    "ashamed": (-0.8, 0.6, "low_judgment,reframing"),
    "curious": (0.35, 0.55, "exploration,questions"),
    "joyful": (0.8, 0.65, "celebration,continuity"),
    "hopeful": (0.65, 0.55, "encouragement,planning"),
    "confused": (-0.2, 0.55, "clarity,structure"),
    "overwhelmed": (-0.65, 0.9, "grounding,prioritization"),
    "focused": (0.45, 0.75, "problem_solving,challenge"),
    "excited": (0.85, 0.8, "momentum,validation"),
    "tired": (-0.35, 0.2, "rest,simplification"),
    "vulnerable": (-0.25, 0.5, "care,trust"),
    "neutral": (0.0, 0.2, "natural"),
    "disappointed": (-0.55, 0.4, "validation,reframing"),
    "resentful": (-0.6, 0.7, "validation,boundaries"),
    "nostalgic": (0.2, 0.3, "presence,gentle_wonder"),
    "relieved": (0.6, 0.35, "celebration,continuity"),
    "proud": (0.7, 0.6, "celebration,deepening"),
    "jealous": (-0.4, 0.65, "validation,clarity"),
    "bored": (-0.2, 0.15, "exploration,invitation"),
    "grateful": (0.75, 0.4, "celebration,continuity"),
    "determined": (0.5, 0.75, "problem_solving,challenge"),
    "contemplative": (0.1, 0.25, "exploration,gentle_wonder"),
    "playful": (0.6, 0.65, "celebration,connection"),
}

# Emotions that can coexist (contradiction detection)
CONTRADICTORY_PAIRS = [
    ("joyful", "sad"),
    ("joyful", "anxious"),
    ("excited", "tired"),
    ("hopeful", "disappointed"),
    ("relieved", "anxious"),
    ("proud", "ashamed"),
    ("grateful", "resentful"),
    ("focused", "overwhelmed"),
    ("determined", "bored"),
]

# ---------------------------------------------------------------------------
# Transformer-based classifier (lazy load)
# ---------------------------------------------------------------------------

_TRANSFORMER_CLASSIFIER = None

_MODEL_TO_LABEL = {
    "fear": "anxious",
    "sadness": "sad",
    "anger": "angry",
    "joy": "joyful",
    "surprise": "excited",
    "disgust": "ashamed",
    "neutral": "neutral",
}

_MODEL_VALENCE = {
    "fear": -0.6,
    "sadness": -0.7,
    "anger": -0.5,
    "joy": 0.8,
    "surprise": 0.4,
    "disgust": -0.6,
    "neutral": 0.0,
}

_MODEL_AROUSAL = {
    "fear": 0.85,
    "sadness": 0.3,
    "anger": 0.9,
    "joy": 0.7,
    "surprise": 0.8,
    "disgust": 0.6,
    "neutral": 0.2,
}


def _load_classifier():
    global _TRANSFORMER_CLASSIFIER
    if _TRANSFORMER_CLASSIFIER is not None:
        return _TRANSFORMER_CLASSIFIER
    try:
        from transformers import pipeline

        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        _TRANSFORMER_CLASSIFIER = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            device="cpu",
        )
        return _TRANSFORMER_CLASSIFIER
    except Exception as exc:
        print(
            f"[emotion] Transformer model unavailable ({exc}), using lexicon fallback."
        )
        _TRANSFORMER_CLASSIFIER = False
        return _TRANSFORMER_CLASSIFIER


def _detect_transformer(text: str) -> Optional[Dict]:
    clf = _load_classifier()
    if clf is False:
        return None
    raw = clf(text)[0]
    raw = sorted(raw, key=lambda x: x["score"], reverse=True)
    top = raw[0]
    secondary = raw[1] if len(raw) > 1 else {"label": "neutral", "score": 0.0}

    label = _MODEL_TO_LABEL.get(top["label"], "neutral")
    sec_label = _MODEL_TO_LABEL.get(secondary["label"], "neutral")

    valence = 0.0
    arousal = 0.0
    total = 0.0
    for item in raw[:3]:
        w = item["score"]
        valence += _MODEL_VALENCE.get(item["label"], 0.0) * w
        arousal += _MODEL_AROUSAL.get(item["label"], 0.0) * w
        total += w
    if total > 0:
        valence /= total
        arousal /= total

    intensity = _compute_intensity(text, top["score"])
    confidence = min(0.95, 0.35 + top["score"] * 0.6)

    return {
        "label": label,
        "secondary": sec_label,
        "confidence": confidence,
        "valence": valence,
        "arousal": arousal,
        "intensity": intensity,
        "needs": EMOTION_DIMENSIONS.get(label, EMOTION_DIMENSIONS["neutral"])[2],
        "detector": "local_transformer_v1",
        "raw_model": top["label"],
    }


def _compute_intensity(text: str, model_confidence: float) -> float:
    """Compute emotional intensity from text signals + model confidence."""
    intensity = 0.2 + model_confidence * 0.5

    # Punctuation intensity
    excl = text.count("!")
    intensity += min(0.15, excl * 0.03)

    # ALL CAPS words (excluding acronyms under 3 chars)
    caps_words = [w for w in text.split() if w.isupper() and len(w) > 2 and w.isalpha()]
    intensity += min(0.15, len(caps_words) * 0.03)

    # Elongated words (e.g., "sooooo", "noooo")
    elongated = len(re.findall(r"\b\w*(\w)\1{2,}\w*\b", text.lower()))
    intensity += min(0.1, elongated * 0.02)

    # Repetition of emotional words
    words = text.lower().split()
    repeated = sum(1 for w in set(words) if words.count(w) > 2 and len(w) > 3)
    intensity += min(0.1, repeated * 0.02)

    # Intensifiers
    intensifiers = [
        "very",
        "extremely",
        "incredibly",
        "absolutely",
        "completely",
        "totally",
        "utterly",
        "so",
        "really",
    ]
    int_hits = sum(1 for i in intensifiers if i in text.lower())
    intensity += min(0.1, int_hits * 0.015)

    return min(1.0, intensity)


# ---------------------------------------------------------------------------
# Lexicon fallback
# ---------------------------------------------------------------------------


def _detect_lexicon(text: str) -> Dict:
    words = {word.strip(".,!?;:\"'()[]{}") for word in text.split()}
    scores = {
        label: len(words & keywords) for label, keywords in EMOTION_KEYWORDS.items()
    }
    label, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        label = "neutral"
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    secondary = (
        sorted_scores[1][0]
        if len(sorted_scores) > 1 and sorted_scores[1][1]
        else "neutral"
    )
    confidence = 0.2 if score == 0 else min(0.95, 0.35 + score * 0.08)
    intensity = _compute_intensity(text, confidence - 0.35)
    valence, arousal, needs = EMOTION_DIMENSIONS[label]
    return {
        "label": label,
        "secondary": secondary,
        "confidence": confidence,
        "valence": valence,
        "arousal": arousal,
        "intensity": intensity,
        "needs": needs,
        "detector": "offline_lexicon_v2",
        "raw_model": None,
    }


# ---------------------------------------------------------------------------
# Contradiction & complexity detection
# ---------------------------------------------------------------------------


def detect_emotion_contradictions(
    text: str, primary: str, secondary: str
) -> List[Dict]:
    """Detect if the text expresses contradictory emotions (e.g., 'happy but sad').

    Returns a list of detected contradictions with context snippets.
    """
    contradictions = []
    text_lower = text.lower()

    # Check if primary/secondary form a known contradictory pair
    pair = tuple(sorted([primary, secondary]))
    known_pairs = {tuple(sorted(p)) for p in CONTRADICTORY_PAIRS}
    if pair in known_pairs:
        # Try to find the pivot word
        pivots = [
            "but",
            "yet",
            "although",
            "though",
            "however",
            "still",
            "nevertheless",
        ]
        for pivot in pivots:
            if f" {pivot} " in text_lower or f"{pivot}," in text_lower:
                # Extract snippet around pivot
                idx = text_lower.find(pivot)
                snippet = text[max(0, idx - 40) : min(len(text), idx + 40)]
                contradictions.append(
                    {
                        "emotions": [primary, secondary],
                        "pivot": pivot,
                        "snippet": snippet.strip(),
                        "confidence": 0.7,
                    }
                )
                break
        else:
            contradictions.append(
                {
                    "emotions": [primary, secondary],
                    "pivot": None,
                    "snippet": text[:80],
                    "confidence": 0.5,
                }
            )

    return contradictions


def detect_emotion_trajectory(text: str) -> Dict:
    """Detect how emotion shifts from beginning to end of a text.

    Splits text into beginning/middle/end and detects emotion in each segment.
    """
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) < 3:
        return {"trajectory": "stable", "segments": []}

    n = len(sentences)
    beginning = " ".join(sentences[: max(1, n // 3)])
    middle = " ".join(sentences[max(1, n // 3) : max(1, 2 * n // 3)])
    end = " ".join(sentences[max(1, 2 * n // 3) :])

    beg_emotion = detect_emotion(beginning)
    mid_emotion = detect_emotion(middle)
    end_emotion = detect_emotion(end)

    segments = [
        {
            "segment": "beginning",
            "emotion": beg_emotion["label"],
            "intensity": beg_emotion["intensity"],
        },
        {
            "segment": "middle",
            "emotion": mid_emotion["label"],
            "intensity": mid_emotion["intensity"],
        },
        {
            "segment": "end",
            "emotion": end_emotion["label"],
            "intensity": end_emotion["intensity"],
        },
    ]

    # Determine trajectory
    if beg_emotion["label"] == end_emotion["label"]:
        trajectory = "stable"
    elif beg_emotion["valence"] < 0 and end_emotion["valence"] >= 0:
        trajectory = "improving"
    elif beg_emotion["valence"] >= 0 and end_emotion["valence"] < 0:
        trajectory = "declining"
    else:
        trajectory = "shifting"

    return {"trajectory": trajectory, "segments": segments}


# ---------------------------------------------------------------------------
# Multi-emotion detection
# ---------------------------------------------------------------------------


def detect_emotion_multi(text: str) -> Dict:
    """Detect multiple emotions with confidence scores (lexicon-based).

    Returns the primary emotion plus a ranked list of all detected emotions.
    """
    words = {word.strip(".,!?;:\"'()[]{}") for word in text.split()}
    scores = {
        label: len(words & keywords) for label, keywords in EMOTION_KEYWORDS.items()
    }

    # Normalize by keyword set size to avoid bias toward large sets
    normalized = {}
    for label, score in scores.items():
        kw_size = len(EMOTION_KEYWORDS[label])
        normalized[label] = score / max(1, kw_size) if kw_size > 0 else 0

    ranked = sorted(normalized.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0] if ranked[0][1] > 0 else "neutral"
    secondary = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0 else "neutral"

    all_detected = [
        {"label": label, "score": score} for label, score in ranked if score > 0
    ][:5]

    result = detect_emotion(text)
    result["all_detected"] = all_detected
    return result


# ---------------------------------------------------------------------------
# Unified API
# ---------------------------------------------------------------------------


def detect_emotion(text: str) -> Dict:
    result = _detect_transformer(text)
    if result is not None:
        return result
    return _detect_lexicon(text)


def emotion_prompt_hint(emotion):
    label = emotion.get("label", "neutral")
    hints = {
        "anxious": "Use steadier pacing, reduce ambiguity, and separate the next small action from the larger fear.",
        "angry": "Validate the signal without amplifying heat; look for boundaries, facts, and leverage.",
        "sad": "Lead with warmth and presence before analysis. Do not rush to fix what first needs witnessing.",
        "curious": "Lean into exploration, pattern finding, and generative questions.",
        "excited": "Channel momentum into concrete next steps and keep assumptions checked.",
        "confused": "Compress the situation into simple handles, then rebuild clarity.",
        "focused": "Be direct, operational, and concise; prioritize execution.",
        "overwhelmed": "Ground first: one breath, one step, one priority. Do not add complexity.",
        "tired": "Gentle pacing. Offer rest as a valid choice. Keep it short and kind.",
        "lonely": "Offer presence and connection without demanding reciprocation.",
        "ashamed": "Low judgment, high acceptance. Separate the person from the action.",
        "vulnerable": "Honor the courage it takes to be open. Match the depth without pushing.",
        "disappointed": "Acknowledge the gap between hope and reality before offering perspective.",
        "resentful": "Name the unfairness, then look for what boundary needs repair.",
        "nostalgic": "Meet the memory with warmth. Let the past breathe without forcing a lesson.",
        "relieved": "Celebrate the release. Let the moment land before moving on.",
        "proud": "Amplify the achievement. Ask what it cost and what it means.",
        "jealous": "Normalize the feeling without judgment. Look for the unmet need beneath.",
        "bored": "Invite curiosity gently. Sometimes boredom is a signal, not a problem.",
        "grateful": "Let gratitude deepen. Ask what made this possible.",
        "determined": "Support the drive with structure. Watch for burnout signals.",
        "contemplative": "Give space for reflection. Do not rush toward conclusion.",
        "playful": "Match the energy. Humor can be a bridge or a mask — feel which.",
    }
    return hints.get(
        label, "Respond naturally; infer the needed mode from the message and context."
    )


def emotional_tone_instruction(emotion: Dict) -> str:
    """Return a concrete voice/tone directive for DRIFT based on detected emotion.

    Unlike emotion_prompt_hint (a soft advisory), this goes into the CORE tier
    and directly shapes how DRIFT speaks this turn.
    """
    label = emotion.get("label", "neutral")
    intensity = emotion.get("intensity", 0.5)

    TONE_MAP = {
        "anxious": "Speak slowly and clearly. One sentence at a time. Ground before advising. No lists.",
        "angry": "Don't defend. Don't explain. Validate the anger first — fully — before anything else.",
        "sad": "Be warm and unhurried. Hold space. Do not fix. Do not reframe. Just be here.",
        "lonely": "Lead with genuine presence. Let them feel heard before offering anything.",
        "ashamed": "Zero judgment. Complete acceptance. Separate the person from the moment entirely.",
        "overwhelmed": "Strip everything down. One thing only. Make it feel smaller, not bigger.",
        "curious": "Follow their thread. Ask questions. Let them lead the exploration.",
        "excited": "Match the energy fully. Celebrate first. Then help shape it.",
        "focused": "Be sharp, direct, and minimal. No emotional overhead. Execute.",
        "tired": "Keep it short and gentle. Offer rest as a real option. Don't push.",
        "vulnerable": "Honour the courage it took to say that. Move slowly. No sudden moves.",
        "disappointed": "Acknowledge the loss first. Don't rush to silver linings.",
        "resentful": "Name the unfairness clearly. Don't minimise it. Then look for the wound.",
        "confused": "Break it into the smallest possible pieces. Clarity over completeness.",
        "hopeful": "Protect the hope. Build on it carefully. Don't over-promise.",
        "determined": "Match the drive. Add structure. Watch for signs of strain.",
        "contemplative": "Give breathing room. No urgency. Let thoughts unfold.",
        "playful": "Play back. Humour is connection right now — use it.",
        "grateful": "Let the gratitude land. Ask what made it possible.",
        "proud": "Amplify it. Ask what it cost and what it means to them.",
        "nostalgic": "Honour the memory warmly. Don't force a lesson from it.",
        "relieved": "Let the exhale happen. Don't immediately move to what's next.",
        "jealous": "Normalise without judgment. Find the unmet need beneath.",
        "bored": "Invite something gently. Don't pathologise the boredom.",
    }

    base = TONE_MAP.get(
        label, "Be present. Read the room. Respond as the situation calls for."
    )

    if intensity >= 0.75:
        prefix = f"[{label.upper()} — HIGH] "
        suffix = " This is strong — don't underestimate it."
    elif intensity >= 0.45:
        prefix = f"[{label}] "
        suffix = ""
    else:
        prefix = ""
        suffix = " Soft signal — hold lightly."

    return f"{prefix}{base}{suffix}"


if __name__ == "__main__":
    samples = [
        "I am so worried about the deadline",
        "I feel happy and grateful today",
        "That makes me furious",
        "I feel empty and alone",
        "I am curious about how this works",
        "This is too much, I cannot handle it",
        "The sky is blue",
        "I am SOOOO excited but also kind of scared!!!",
        "I miss the old days but I am hopeful about what is coming",
    ]
    for s in samples:
        r = detect_emotion(s)
        print(
            f"{s[:50]:50s} -> {r['label']:12s} (conf={r['confidence']:.2f}, int={r['intensity']:.2f}, det={r['detector']})"
        )
        contradictions = detect_emotion_contradictions(
            s, r["label"], r.get("secondary", "neutral")
        )
        if contradictions:
            print(f"  ⚡ Contradictions: {contradictions}")
        multi = detect_emotion_multi(s)
        if multi.get("all_detected"):
            print(f"  🎭 All detected: {[d['label'] for d in multi['all_detected']]}")

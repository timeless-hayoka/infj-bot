"""Emotion detection using a local transformer model with lexicon fallback."""
import os
from typing import Dict, List

# ---------------------------------------------------------------------------
# Lexicon fallback (offline, zero-dependency)
# ---------------------------------------------------------------------------

EMOTION_KEYWORDS = {
    "anxious": {"worried", "nervous", "scared", "stress", "stressed", "panic", "afraid", "deadline"},
    "angry": {"angry", "mad", "furious", "annoyed", "irritated", "rage", "unfair"},
    "sad": {"sad", "hurt", "grief", "down", "depressed", "empty"},
    "lonely": {"lonely", "alone", "isolated", "unseen"},
    "ashamed": {"ashamed", "embarrassed", "guilty", "worthless"},
    "curious": {"curious", "wonder", "why", "how", "learn", "explore", "question"},
    "joyful": {"happy", "joy", "grateful", "glad"},
    "hopeful": {"hope", "hopeful", "possible", "better"},
    "confused": {"confused", "lost", "stuck", "unclear", "messy"},
    "overwhelmed": {"overwhelmed", "too", "much", "can't", "cannot"},
    "tired": {"tired", "exhausted", "sleepy", "drained"},
    "vulnerable": {"honest", "scared", "hard", "sensitive", "open"},
    "excited": {"excited", "amazing", "awesome", "wow", "unbelievable", "huge"},
    "focused": {"build", "fix", "ship", "implement", "test", "run", "phase", "ready"},
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
}


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
        # Suppress noisy download logs
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        _TRANSFORMER_CLASSIFIER = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            device="cpu",
        )
        return _TRANSFORMER_CLASSIFIER
    except Exception as exc:
        print(f"[emotion] Transformer model unavailable ({exc}), using lexicon fallback.")
        _TRANSFORMER_CLASSIFIER = False
        return _TRANSFORMER_CLASSIFIER


def _detect_transformer(text: str) -> Dict:
    clf = _load_classifier()
    if clf is False:
        return None
    raw = clf(text)[0]  # list of dicts
    # Sort by score descending
    raw = sorted(raw, key=lambda x: x["score"], reverse=True)
    top = raw[0]
    secondary = raw[1] if len(raw) > 1 else {"label": "neutral", "score": 0.0}

    label = _MODEL_TO_LABEL.get(top["label"], "neutral")
    sec_label = _MODEL_TO_LABEL.get(secondary["label"], "neutral")

    # Weighted valence/arousal from top-3 predictions
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

    intensity = min(1.0, 0.25 + top["score"] * 0.75 + text.count("!") * 0.03)
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


# ---------------------------------------------------------------------------
# Lexicon fallback
# ---------------------------------------------------------------------------

def _detect_lexicon(text: str) -> Dict:
    words = {word.strip(".,!?;:\"'()[]{}").lower() for word in text.split()}
    scores = {
        label: len(words & keywords)
        for label, keywords in EMOTION_KEYWORDS.items()
    }
    label, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        label = "neutral"
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    secondary = sorted_scores[1][0] if len(sorted_scores) > 1 and sorted_scores[1][1] else "neutral"
    intensity = min(1.0, 0.25 + score * 0.18 + text.count("!") * 0.05)
    confidence = 0.2 if score == 0 else min(0.95, 0.35 + score * 0.12)
    valence, arousal, needs = EMOTION_DIMENSIONS[label]
    return {
        "label": label,
        "secondary": secondary,
        "confidence": confidence,
        "valence": valence,
        "arousal": arousal,
        "intensity": intensity,
        "needs": needs,
        "detector": "offline_lexicon_v1",
        "raw_model": None,
    }


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
    }
    return hints.get(label, "Respond naturally; infer the needed mode from the message and context.")


if __name__ == "__main__":
    samples = [
        "I am so worried about the deadline",
        "I feel happy and grateful today",
        "That makes me furious",
        "I feel empty and alone",
        "I am curious about how this works",
        "This is too much, I cannot handle it",
        "The sky is blue",
    ]
    for s in samples:
        r = detect_emotion(s)
        print(f"{s[:40]:40s} -> {r['label']:10s} (conf={r['confidence']:.2f}, val={r['valence']:.2f}, ar={r['arousal']:.2f}, det={r['detector']})")

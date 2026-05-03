import re


DISSONANCE_MARKERS = {
    "but",
    "however",
    "although",
    "yet",
    "torn",
    "conflicted",
    "stuck",
    "guilty",
    "ashamed",
    "should",
    "shouldn't",
    "want",
    "need",
    "afraid",
    "part",
    "both",
    "mixed",
}

VALUE_MARKERS = {
    "safety": {"safe", "risk", "danger", "protect", "secure", "stability"},
    "autonomy": {"free", "choice", "control", "independent", "space"},
    "connection": {"love", "friend", "family", "belong", "seen", "connection"},
    "honesty": {"truth", "honest", "real", "authentic", "lie"},
    "growth": {"learn", "build", "improve", "change", "grow", "better"},
    "responsibility": {"should", "owe", "duty", "responsible", "promise"},
    "rest": {"tired", "rest", "sleep", "drained", "overwhelmed"},
}


def _tokens(text):
    return re.findall(r"[a-z']+", text.lower())


def detect_dissonance(text):
    words = set(_tokens(text))
    marker_hits = sorted(words & DISSONANCE_MARKERS)
    contrast_hits = len(re.findall(r"\b(but|however|although|yet|on the other hand)\b", text.lower()))
    question_pressure = text.count("?")

    value_hits = []
    for value, markers in VALUE_MARKERS.items():
        if words & markers:
            value_hits.append(value)

    score = min(
        1.0,
        0.12 * len(marker_hits)
        + 0.2 * contrast_hits
        + 0.08 * min(question_pressure, 3)
        + 0.06 * len(value_hits),
    )
    if any(phrase in text.lower() for phrase in ("part of me", "i want to but", "i know i should")):
        score = min(1.0, score + 0.25)

    return {
        "score": score,
        "markers": marker_hits[:8],
        "values": value_hits[:5],
        "detector": "offline_dissonance_v1",
    }


def dissonance_prompt_hint(signal):
    score = signal.get("score", 0.0)
    if score < 0.25:
        return "No strong cognitive-dissonance signal detected; respond normally."
    values = ", ".join(signal.get("values", [])) or "not yet clear"
    return (
        "Cognitive dissonance signal detected. Name the competing pulls neutrally, "
        f"look for values in tension ({values}), separate facts from interpretations, "
        "and offer one small next step that preserves optionality."
    )


def map_dissonance(text):
    signal = detect_dissonance(text)
    values = signal.get("values") or ["not yet clear"]
    markers = signal.get("markers") or ["implicit tension"]
    return (
        "Cognitive dissonance map\n"
        f"- Signal strength: {signal['score']:.2f}\n"
        f"- Tension markers: {', '.join(markers)}\n"
        f"- Values possibly involved: {', '.join(values)}\n"
        "- Try asking: What is each side trying to protect?\n"
        "- Small next move: separate one known fact from one interpretation, then choose a reversible action."
    )

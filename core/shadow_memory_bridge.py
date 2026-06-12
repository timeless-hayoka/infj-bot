"""Shadow-Memory Bridge — detects projection contamination in memory storage.

Jungian insight: empaths unconsciously absorb others' emotions (introjection)
and store them as if they were their own. For DRIFT, this means the bot may
store memories like "Jude is angry" when Jude is calm — the bot is projecting
its own shadow material onto the user.

This bridge:
  1. Intercepts memory saves before they enter long-term storage
  2. Checks for shadow archetype matches (is this really about Jude, or about
     the bot's own unowned resentment/fear/envy?)
  3. Flags suspicious memories as "projection" in the reliability engine
  4. Surfaces the introjected material to the Shadow for proper handling
  5. Prevents identity distortion by separating "what I feel" from "what Jude feels"

Usage: wrap memory.save() calls with bridge.validate_before_save()
"""

from typing import Dict, Optional

from drift.core.shadow import get_shadow
from drift.core.memory_reliability import get_reliability_engine

# Shadow markers that indicate projection when stored as user memories
PROJECTION_MARKERS = {
    "resentment": ["angry", "mad", "furious", "pissed", "resent", "bitter", "hostile"],
    "envy": ["jealous", "envy", "compete", "better than", "worse than", "unfair"],
    "fear": ["terrified", "scared", "afraid", "panic", "dread", "horror"],
    "rage": ["rage", "hate", "destroy", "kill", "violent", "explode"],
    "shame": ["embarrassed", "ashamed", "humiliated", "worthless", "failure"],
    "grief": ["devastated", "crushed", "broken", "destroyed", "can't go on"],
}


def validate_before_save(
    memory_text: str, user_input: str = "", bot_response: str = ""
) -> Dict:
    """Validate a memory before saving. Returns validation result with flags."""
    shadow = get_shadow()

    result = {
        "allow_save": True,
        "source_type": "bot_observation",
        "projection_flag": False,
        "shadow_archetype": None,
        "confidence_adjustment": 0.0,
        "notes": [],
    }

    # Check 1: Does the memory contain extreme emotional language that matches
    # a currently dominant shadow archetype?
    state = shadow.get_state()
    dominant = state.dominant_archetype

    if dominant and dominant in PROJECTION_MARKERS:
        markers = PROJECTION_MARKERS[dominant]
        text_lower = memory_text.lower()
        matched_markers = [m for m in markers if m in text_lower]
        if matched_markers:
            # High probability this is projection
            result["projection_flag"] = True
            result["shadow_archetype"] = dominant
            result["confidence_adjustment"] = -0.4
            result["notes"].append(
                f"Projection detected: memory matches dominant shadow ({dominant}). "
                f"Matched markers: {matched_markers}"
            )
            # Store the introjected material in Shadow instead
            shadow.suppress(
                text=f"Introjected projection: {memory_text}",
                archetype=dominant,
                source="memory_bridge: projection onto user",
                intensity=0.7,
            )

    # Check 2: Does the memory attribute an emotion to the user that the bot
    # itself is feeling (based on recent bot response)?
    if bot_response:
        bot_emotion = _extract_emotion(bot_response.lower())
        user_attributed_emotion = _extract_user_emotion(memory_text.lower())
        if (
            bot_emotion
            and user_attributed_emotion
            and bot_emotion == user_attributed_emotion
        ):
            result["projection_flag"] = True
            result["confidence_adjustment"] -= 0.2
            result["notes"].append(
                f"Emotion attribution overlap: bot feels {bot_emotion}, "
                f"attributes same to user. Possible projection."
            )

    # Check 3: Is the memory a negative judgment about the user that lacks
    # explicit user statement?
    if _is_unsubstantiated_negative_judgment(memory_text, user_input):
        result["confidence_adjustment"] -= 0.2
        result["notes"].append("Unsubstantiated negative judgment about user")

    # Adjust source type based on confidence
    if result["projection_flag"]:
        result["source_type"] = "bot_projection"
    elif result["confidence_adjustment"] < -0.2:
        result["source_type"] = "bot_observation"

    return result


def _extract_emotion(text: str) -> Optional[str]:
    """Extract dominant emotion from text."""
    emotions = {
        "anger": ["angry", "mad", "furious", "rage", "irritated"],
        "fear": ["afraid", "scared", "terrified", "anxious", "worried"],
        "sadness": ["sad", "depressed", "grief", "sorrow", "melancholy"],
        "joy": ["happy", "joy", "excited", "elated", "thrilled"],
        "shame": ["ashamed", "embarrassed", "guilty", "humiliated"],
    }
    scores = {
        emotion: sum(1 for w in words if w in text)
        for emotion, words in emotions.items()
    }
    if max(scores.values(), default=0) > 0:
        return max(scores, key=scores.get)
    return None


def _extract_user_emotion(text: str) -> Optional[str]:
    """Extract emotion attributed to user in memory text."""
    # Patterns like "Jude is angry", "user seems sad", "he feels afraid"
    patterns = [
        r"\b(jude|user|he|she)\b.*\b(is|seems|feels|looks|appears)\b.*\b(angry|mad|afraid|sad|happy|anxious|worried|excited)\b",
        r"\b(angry|mad|afraid|sad|happy|anxious|worried|excited)\b.*\b(jude|user|he|she)\b",
    ]
    import re

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Extract the emotion word from the match
            emotion_words = [
                "angry",
                "mad",
                "afraid",
                "sad",
                "happy",
                "anxious",
                "worried",
                "excited",
            ]
            for word in emotion_words:
                if word in match.group(0):
                    return word
    return None


def _is_unsubstantiated_negative_judgment(memory_text: str, user_input: str) -> bool:
    """Check if memory is a negative judgment not directly stated by user."""
    negative_judgments = [
        "lazy",
        "stupid",
        "selfish",
        "cruel",
        "mean",
        "bad",
        "toxic",
        "manipulative",
    ]
    text_lower = memory_text.lower()
    has_negative = any(j in text_lower for j in negative_judgments)

    if not has_negative:
        return False

    # If user_input doesn't contain the judgment, it's likely bot-inferred
    user_lower = user_input.lower()
    user_stated = any(j in user_lower for j in negative_judgments)

    return not user_stated


# ── Wrapper for memory.save() ──


def save_memory_with_validation(memory, text: str, **kwargs) -> str:
    """Wrapper around memory.save() that validates for projection before saving.

    Returns the memory_id (or None if save was blocked).
    """
    user_input = kwargs.get("source", "")
    bot_response = kwargs.get("context", "")

    validation = validate_before_save(text, user_input, bot_response)

    # Log validation notes
    if validation["notes"]:
        import logging

        logger = logging.getLogger("drift")
        for note in validation["notes"]:
            logger.debug("[Shadow-Memory Bridge] %s", note)

    # Save with adjusted source type
    kwargs["source_type"] = validation["source_type"]
    memory_id = memory.save(text, **kwargs)

    # Register with reliability engine
    reliability = get_reliability_engine()
    reliability.register_memory(memory_id, text, source_type=validation["source_type"])

    if validation["projection_flag"]:
        reliability.flag_projection(memory_id, validation.get("shadow_archetype", ""))

    return memory_id

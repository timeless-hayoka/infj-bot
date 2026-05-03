from cognition import detect_dissonance, dissonance_prompt_hint
from emotion import detect_emotion, emotion_prompt_hint
from guardrails import cyber_context_hint, memory_context_block, mode_scope_rail
from tools import build_tool_prompt
from being import get_being
from cognitive_architecture import CognitiveArchitecture


def build_chat_prompt(message, state, memory, goals_db=None, doc_store=None, tools_enabled=True, prefs=None, temporal=None, predictor=None):
    """Build the full chat prompt with emotion, memory, goals, docs, tools, and preferences.

    Uses the cognitive architecture registry to dynamically assemble prompt sections
    from registered cognitive modules. Core computed sections (emotion, dissonance,
    memory, goals, docs, tools) remain hardcoded for stability.
    """
    emotion = detect_emotion(message)
    dissonance = detect_dissonance(message)
    context = memory.retrieve_context(message)

    goals_context = ""
    if goals_db is not None:
        summary = goals_db.active_summary()
        if summary and summary != "No active goals.":
            goals_context = f"\nActive goals:\n{summary}\n"

    doc_context = ""
    if doc_store is not None:
        doc_results = doc_store.search(message, n_results=3)
        if doc_results:
            lines = []
            for r in doc_results:
                lines.append(f"[{r['filename']}]\n{r['document'][:400]}")
            doc_context = "\nRelevant documents:\n" + "\n---\n".join(lines) + "\n"

    tool_context = build_tool_prompt() if tools_enabled else ""

    prefs_context = ""
    if prefs is not None:
        prefs_context = prefs.format_prompt_snippet() + "\n"

    being = get_being()
    being_context = being.format_being_prompt() + "\n"

    # --- Registry-driven cognitive layers ---
    arch = CognitiveArchitecture()
    registry_sections = arch.assemble_prompt_sections()

    # Core registry plugins (emotional_field, values, relationship)
    core_registry = "\n".join(s for s in registry_sections.get("core", []) if s)
    if core_registry:
        core_registry += "\n"

    # Cognitive registry plugins (aspirations, metacognition, self_modify, growth, temporal, predictor)
    cognitive_registry = "\n".join(s for s in registry_sections.get("cognitive", []) if s)
    if cognitive_registry:
        cognitive_registry += "\n"

    # Assemble prompt sections in priority order (core first, trimmable last)
    core_sections = [
        f"Current mode: {state.mode}\n{mode_scope_rail(state.mode)}",
        being_context,
        core_registry,
        prefs_context,
    ]
    cognitive_sections = [
        cognitive_registry,
    ]
    analysis_sections = [
        f"""Emotional signal, offline estimate:
- primary: {emotion["label"]}
- secondary: {emotion.get("secondary", "neutral")}
- confidence: {emotion["confidence"]:.2f}
- intensity: {emotion["intensity"]:.2f}
- suggested posture: {emotion_prompt_hint(emotion)}
Use this as a soft signal, not a diagnosis.

Cognitive dissonance signal, offline estimate:
- score: {dissonance["score"]:.2f}
- markers: {", ".join(dissonance["markers"]) or "none"}
- possible values: {", ".join(dissonance["values"]) or "not clear"}
- suggested posture: {dissonance_prompt_hint(dissonance)}
Use this to clarify inner conflict without pathologizing it.
""",
        cyber_context_hint(message),
    ]
    context_sections = [
        memory_context_block(context),
        goals_context,
        doc_context,
        tool_context,
    ]
    footer = f"\nUser: {message}\n"

    MAX_PROMPT_CHARS = 12000  # ~3k tokens, leaves room for response

    # Build full prompt
    all_sections = core_sections + cognitive_sections + analysis_sections + context_sections
    prompt_body = "\n".join(s for s in all_sections if s)
    prompt = prompt_body + footer

    # If too large, progressively trim
    if len(prompt) > MAX_PROMPT_CHARS:
        # First trim documents
        if doc_context:
            doc_lines = doc_context.split("\n")
            doc_context = "\n".join(doc_lines[:8]) + "\n[Documents truncated]\n"
        prompt = "\n".join(s for s in core_sections + cognitive_sections + analysis_sections + [memory_context_block(context), goals_context, doc_context, tool_context] if s) + footer

    if len(prompt) > MAX_PROMPT_CHARS:
        # Then trim tools
        if tool_context:
            tool_context = "[Tools available: use /tools to list]\n"
        prompt = "\n".join(s for s in core_sections + cognitive_sections + analysis_sections + [memory_context_block(context), goals_context, doc_context, tool_context] if s) + footer

    if len(prompt) > MAX_PROMPT_CHARS:
        # Then trim cognitive layers (least critical)
        for i in range(len(cognitive_sections)):
            if cognitive_sections[i]:
                cognitive_sections[i] = ""
                prompt = "\n".join(s for s in core_sections + cognitive_sections + analysis_sections + [memory_context_block(context), goals_context, doc_context, tool_context] if s) + footer
                if len(prompt) <= MAX_PROMPT_CHARS:
                    break

    if len(prompt) > MAX_PROMPT_CHARS:
        # Last resort: hard truncate
        prompt = prompt[:MAX_PROMPT_CHARS - 100] + "\n...[prompt trimmed]\n" + footer

    return prompt, emotion, dissonance

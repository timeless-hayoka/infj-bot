"""prompt_builder.py — Backward-compatible prompt builder.

Delegates to CognitiveOrchestrator for actual assembly. Kept as a thin
wrapper so existing entry points (api.py, web_app.py, tui.py, cli.py)
continue to work without modification.
"""

from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator

_orchestrator = CognitiveOrchestrator()


def build_chat_prompt(
    message,
    state,
    memory,
    goals_db=None,
    doc_store=None,
    tools_enabled=True,
    prefs=None,
    _temporal=None,
    _predictor=None,
    debug_dump=False,
):
    """Build the full chat prompt. Delegates to CognitiveOrchestrator."""
    return _orchestrator.assemble_prompt(
        message=message,
        state=state,
        memory=memory,
        goals_db=goals_db,
        doc_store=doc_store,
        tools_enabled=tools_enabled,
        prefs=prefs,
        debug_dump=debug_dump,
    )

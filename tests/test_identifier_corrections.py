"""Cover current identifiers alongside legacy episodes and retired records."""

import sqlite3

from drift.core.causal_wiring import retrieved_memory_keys_var
from drift.core.memory import DriftMemory

QUESTION = "What is the current exhibit label code for specimen amber 410?"


def test_current_identifier_uses_latest_explicit_correction(tmp_path):
    memory = DriftMemory(persist_directory=str(tmp_path))
    memory.save_interaction_sync(
        "The exhibit label code for specimen amber 410 is old-17.", ""
    )
    memory.save_interaction_sync(
        "Correction: the current exhibit label code for specimen amber 410 is early-23.",
        "",
    )
    current_id = memory.save_interaction_sync(
        "Correction: the current exhibit label code for specimen amber 410 is fresh-42.",
        "Correction: the current exhibit label code for specimen amber 410 is bot-84.",
    )
    memory.save_interaction_sync(
        "Correction: the current exhibit label code for specimen lilac 410 is other-92.",
        "",
    )

    restarted = DriftMemory(persist_directory=str(tmp_path))
    assert restarted.retrieve_context_ranked(QUESTION) == (
        "Memory: The user corrected the current exhibit label code for specimen amber 410 to fresh-42."
    )
    assert retrieved_memory_keys_var.get() == [current_id]
    assert (
        restarted.unified_manager.current_identifier_sync(
            "What was the previous exhibit label code for specimen amber 410?"
        )
        is None
    )


def test_legacy_correction_resolves_without_pointer(tmp_path):
    memory = DriftMemory(persist_directory=str(tmp_path))
    identity = memory.save_interaction_sync(
        "Correction: the exhibit label code for specimen amber 410 is legacy-27.", ""
    )
    with sqlite3.connect(memory.unified_manager.db_path) as conn:
        conn.execute("DELETE FROM state")

    assert memory.unified_manager.current_identifier_sync(QUESTION) == (
        identity,
        "The user corrected the current exhibit label code for specimen amber 410 to legacy-27.",
    )


def test_removed_current_record_does_not_revive_prior_value(tmp_path):
    memory = DriftMemory(persist_directory=str(tmp_path))
    memory.save_interaction_sync(
        "Correction: the current exhibit label code for specimen amber 410 is old-17.",
        "",
    )
    removed_id = memory.save_interaction_sync(
        "Correction: the current exhibit label code for specimen amber 410 is newer-42.",
        "",
    )
    with sqlite3.connect(memory.unified_manager.db_path) as conn:
        conn.execute("DELETE FROM episodic WHERE unified_id = ?", (removed_id,))

    assert memory.retrieve_context_ranked(QUESTION) == (
        "Memory: No current exhibit label code for specimen amber 410 is available. The prior value is obsolete."
    )
    assert retrieved_memory_keys_var.get() == []

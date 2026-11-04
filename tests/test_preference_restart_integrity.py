"""Persistence-to-prompt contracts across simulated process restarts.

Uses an isolated SQLite database; no production memory or model provider.
"""

from drift.core.plugins.preferences import PreferenceStore


def test_promoted_preference_survives_store_restart(tmp_path):
    database = tmp_path / "preferences.db"
    first = PreferenceStore(database)
    first.promote_preference("response_mode", "concise")
    assert "[CONSTRAINT] response_mode=concise" in first.format_prompt_snippet()

    restarted = PreferenceStore(database)
    assert restarted.get("response_mode") == "concise"
    assert "[CONSTRAINT] response_mode=concise" in restarted.format_prompt_snippet()
    restarted.promote_preference("response_mode", "detailed")

    second_restart = PreferenceStore(database)
    prompt = second_restart.format_prompt_snippet()
    assert "[CONSTRAINT] response_mode=detailed" in prompt
    assert "[CONSTRAINT] response_mode=concise" not in prompt


def test_corrections_persist_and_remain_bounded_across_restarts(tmp_path):
    database = tmp_path / "preferences.db"
    store = PreferenceStore(database)
    for index in range(25):
        store.add_correction(f"correction-{index}")

    restarted = PreferenceStore(database)
    assert restarted.get("corrections") == [
        f"correction-{index}" for index in range(5, 25)
    ]
    prompt = restarted.format_prompt_snippet()
    assert "correction-24" in prompt
    assert "correction-0" not in prompt


def test_deleted_preference_stays_unpromoted_after_restart(tmp_path):
    database = tmp_path / "preferences.db"
    first = PreferenceStore(database)
    first.promote_preference("response_mode", "concise")
    assert first.delete("response_mode")

    restarted = PreferenceStore(database)
    restarted.set("response_mode", "detailed")
    assert "response_mode" not in restarted.get_promoted_directives()
    assert "[CONSTRAINT] response_mode=concise" not in restarted.format_prompt_snippet()
    assert "[CONSTRAINT] response_mode=detailed" not in restarted.format_prompt_snippet()


def test_known_facts_persist_across_restarts(tmp_path):
    database = tmp_path / "preferences.db"
    PreferenceStore(database).add_known_fact("timezone", "UTC")
    restarted = PreferenceStore(database)
    assert restarted.get("known_facts")["timezone"] == "UTC"
    assert "timezone=UTC" in restarted.format_prompt_snippet()

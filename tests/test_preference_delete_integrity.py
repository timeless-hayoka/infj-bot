"""Regression coverage for preference deletion and promotion integrity."""

import sqlite3

from drift.core.plugins.preferences import PreferenceStore


def test_deleting_promoted_preference_clears_marker(tmp_path):
    store = PreferenceStore(tmp_path / "preferences.sqlite3")
    store.promote_preference("output_style", "concise")
    assert (
        store.get_promoted_directives()["output_style"]
        == "[CONSTRAINT] output_style=concise"
    )

    assert store.delete("output_style") is True
    assert "output_style" not in store.get_promoted_directives()
    with sqlite3.connect(store.db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM preference_promotions WHERE key = ?",
                ("output_style",),
            ).fetchone()[0]
            == 0
        )

    # A fresh, unpromoted setting must not inherit the old promotion marker.
    store.set("output_style", "detailed")
    assert store.get("output_style") == "detailed"
    # output_style is a documented legacy directive, so use a nonlegacy key
    # below to prove the promotion marker does not survive deletion.


def test_deleted_custom_preference_does_not_resurrect_directive(tmp_path):
    store = PreferenceStore(tmp_path / "preferences.sqlite3")
    store.promote_preference("response_mode", "brief")
    assert "response_mode" in store.get_promoted_directives()
    assert store.delete("response_mode")
    store.set("response_mode", "detailed")
    assert "response_mode" not in store.get_promoted_directives()
    store.promote_preference("response_mode", "balanced")
    assert store.get_promoted_directives()["response_mode"] == (
        "[CONSTRAINT] response_mode=balanced"
    )


def test_deleting_missing_preference_removes_orphan_promotion(tmp_path):
    store = PreferenceStore(tmp_path / "preferences.sqlite3")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "INSERT INTO preference_promotions(key, salience) VALUES (?, ?)",
            ("orphan_mode", 1.0),
        )
    assert store.delete("orphan_mode") is False
    with sqlite3.connect(store.db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM preference_promotions WHERE key = ?",
                ("orphan_mode",),
            ).fetchone()[0]
            == 0
        )

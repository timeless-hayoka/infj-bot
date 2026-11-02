from drift.core.safe_math import compute
from drift.core.safe_math_integration import (
    GroundedResult,
    compute_grounded_results,
    critic_math_check,
    inject_grounded_math,
)


def test_exact_thirds_grounding_and_critic():
    prompt, grounded = inject_grounded_math("What is 1/3 + 1/3 + 1/3?", "")
    assert "[MATH ENGINE" in prompt
    assert len(grounded) == 1 and grounded[0].display_value == "1"
    corrected, violations = critic_math_check("The answer is 10.", grounded)
    assert violations and "[Verified:" in corrected
    assert critic_math_check("The answer is 1.", grounded)[1] == []


def test_symbolic_display_and_critic():
    grounded = [GroundedResult("sqrt(16)", compute("sqrt(16)"))]
    assert grounded[0].display_value == "4"
    corrected, violations = critic_math_check("The answer is 40.", grounded)
    assert violations and "= 4]" in corrected


def test_numerical_token_boundaries():
    grounded = [GroundedResult("2/2", compute("2/2"))]
    for draft in ["10", "-1", "1/3", "1.5"]:
        assert critic_math_check(draft, grounded)[1], draft
    for draft in ["1", "1.0", "1e0"]:
        assert critic_math_check(draft, grounded)[1] == [], draft


def test_request_context_is_independent():
    import contextvars

    from drift.core.safe_math_integration import active_grounded_math_var

    a, b = contextvars.Context(), contextvars.Context()
    a.run(active_grounded_math_var.set, [GroundedResult("2+2", compute("2+2"))])
    assert a.run(active_grounded_math_var.get)[0].display_value == "4"
    assert b.run(active_grounded_math_var.get) == ()


def test_real_prompt_builder_sets_and_clears_grounding(tmp_path):
    from drift.core.commands import BotState
    from drift.core.embeddings import LocalEmbeddingFunction
    from drift.core.memory import DriftMemory
    from drift.core.plugins.preferences import PreferenceStore
    from drift.core.prompt_builder import build_chat_prompt
    from drift.core.safe_math_integration import active_grounded_math_var

    store = PreferenceStore(tmp_path / "preferences.db")
    memory = DriftMemory(
        persist_directory=str(tmp_path / "memory"),
        embedding_function=LocalEmbeddingFunction(),
        use_semantic=False,
    )
    state = BotState(prefs=store)
    prompt, _, _ = build_chat_prompt(
        "What is 1/3 + 1/3 + 1/3?", state, memory, prefs=store, tools_enabled=False
    )
    assert "[MATH ENGINE" in prompt
    assert active_grounded_math_var.get()[0].display_value == "1"
    build_chat_prompt("Hello there", state, memory, prefs=store, tools_enabled=False)
    assert not active_grounded_math_var.get()


def test_brain_final_math_check_uses_real_hook():
    # Provider-independent unit check of the production post-generation hook.
    import logging

    from drift.core.brain import DriftBrain
    from drift.core.safe_math_integration import active_grounded_math_var

    grounded = [GroundedResult("2/2", compute("2/2"))]
    token = active_grounded_math_var.set(grounded)
    try:
        # The hook needs only the logger; constructing a provider is unnecessary.
        class ResponseContext:
            logger = logging.getLogger("grounding-test")

        output = DriftBrain._check_grounded_response(ResponseContext(), "10")
        assert "[Verified: 2/2 = 1]" in output
    finally:
        active_grounded_math_var.reset(token)

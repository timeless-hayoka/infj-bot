from typing import Callable
from infj_bot.core.context_engine import ContextWorker, CognitiveState, CognitivePayload


def pedi_regulation_step(
    worker: ContextWorker[CognitivePayload],
) -> tuple[CognitivePayload, CognitiveState]:
    """
    Evaluates the raw input state and dampens extremes.
    Writes to payload.internal_log; returns updated payload + state.
    """
    payload = worker.current().model_copy()
    state = worker.state.model_copy()

    log_msg = f"Received input: '{payload.user_input}'."

    # PEDI Dampening Logic
    if state.tension > 0.6:
        state.tension -= 0.2
        state.coherence -= 0.1
        log_msg += " [PEDI: Tension damped, coherence slightly reduced]"

    if state.shadow_depth > 0.7:
        state.tension += 0.3
        log_msg += " [PEDI Alert: High shadow depth bleeding into tension]"

    # Ensure bounds
    state.tension = max(0.0, min(1.0, state.tension))
    state.coherence = max(0.0, min(1.0, state.coherence))

    payload.internal_log = log_msg
    return payload, state


def state_conditioned_llm(
    worker: ContextWorker[CognitivePayload],
) -> CognitivePayload:
    """
    The Affective Logic Gate. Decides HOW to query the LLM based on the current state.
    Writes to payload.response; leaves payload.internal_log untouched.
    """
    payload = worker.current().model_copy()
    state = worker.state

    if state.coherence > 0.6 and state.tension < 0.5:
        mode = "Strict Logical Deduction"
        prompt = "Answer purely factually and logically."
    elif state.tension > 0.5 and state.resonance > 0.4:
        mode = "Exploratory Intuitive Leap"
        prompt = "Answer creatively, making intuitive connections."
    elif state.shadow_depth > 0.7:
        mode = "Shadow-Driven Projection"
        prompt = "Answer defensively, questioning the user's premise."
    else:
        mode = "Standard Empathic"
        prompt = "Answer warmly and directly."

    payload.response = f"[{mode}] {prompt}"
    return payload


def predicted_transition_step(
    worker: ContextWorker[CognitivePayload],
    predictor: "Callable[[CognitiveState], CognitiveState]",
) -> tuple[CognitivePayload, CognitiveState]:
    """
    Optional diagnostic step. Runs a predictor against the current state,
    stores the predicted next state in payload.metadata, then returns
    the *actual* state (unchanged) so the real pipeline continues.

    Used by TransitionComparator to evaluate predictor accuracy.
    """
    payload = worker.current().model_copy()
    predicted = predictor(worker.state)
    payload.metadata["predicted_state"] = predicted.model_dump()
    return payload, worker.state.model_copy()

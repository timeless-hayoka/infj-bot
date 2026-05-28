from infj_bot.core.context_engine import ContextWorker, CognitiveState

def pedi_regulation_step(worker: ContextWorker[str]) -> tuple[str, CognitiveState]:
    """
    Evaluates the raw input state and dampens extremes.
    Returns: (Log message, Updated State)
    """
    current_input = worker.current()
    state = worker.state.model_copy() # Copy to avoid mutating the original
    
    log_msg = f"Received input: '{current_input}'."

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

    return log_msg, state

def state_conditioned_llm(worker: ContextWorker[str]) -> str:
    """
    The Affective Logic Gate. Decides HOW to query the LLM based on the current state.
    """
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
        
    return f"[{mode}] {prompt}"

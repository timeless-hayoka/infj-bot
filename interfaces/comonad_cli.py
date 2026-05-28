from infj_bot.core.context_engine import CognitiveState, Context, ContextWorker
from infj_bot.core.cognitive_ops import pedi_regulation_step, state_conditioned_llm

def calculate_state_diff(initial: CognitiveState, final: CognitiveState) -> dict:
    """Calculates the mathematical drift between two states for Vault storage."""
    return {
        "delta_coherence": round(final.coherence - initial.coherence, 3),
        "delta_resonance": round(final.resonance - initial.resonance, 3),
        "delta_tension": round(final.tension - initial.tension, 3),
        "delta_shadow_depth": round(final.shadow_depth - initial.shadow_depth, 3)
    }

def run_cognitive_cycle(user_input: str, current_state: CognitiveState):
    print(f"\n{'='*50}\n▶ INITIATING COGNITIVE CYCLE\n{'='*50}")
    
    # 1. Initialize the Comonad
    initial_ctx = Context[str](state=current_state, value=user_input)
    pipeline = ContextWorker[str](initial_ctx)
    print(f"[Initial State] Tension: {pipeline.state.tension:.2f} | Coherence: {pipeline.state.coherence:.2f} | Shadow: {pipeline.state.shadow_depth:.2f}")

    # 2. PEDI Regulation Step (Inside the Comonad)
    pipeline = pipeline.extend(pedi_regulation_step)
    print(f"\n[Post-PEDI] Log: {pipeline.current()}")
    print(f"            Tension: {pipeline.state.tension:.2f} | Coherence: {pipeline.state.coherence:.2f}")

    # 3. State-Conditioned LLM Generation
    pipeline = pipeline.extend(state_conditioned_llm)
    print(f"\n[Final Output] {pipeline.current()}")

    # 4. Vault Deposit (Metacognition)
    initial_state = pipeline._ctx.history[0] # Grab the very first state in the chain
    final_state = pipeline.state
    diff = calculate_state_diff(initial_state, final_state)
    
    print("\n[Vault Deposit] State Drift Diff:")
    for k, v in diff.items():
        if v != 0:
            print(f"   {k}: {v:+.2f}")
            
    return final_state

if __name__ == "__main__":
    # Simulate a high-tension scenario
    simulated_state = CognitiveState(coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2)
    
    print("Welcome to DRIFT CLI.")
    user_msg = "Why did you disagree with me yesterday?"
    
    # Run the cycle
    new_state = run_cognitive_cycle(user_msg, simulated_state)

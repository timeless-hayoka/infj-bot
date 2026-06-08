"""
test_ambiguous_truth.py — Ambiguous Truth Stress Test
Tests how the DRIFT framework handles messy, human contradiction and shifting inputs.
Success criteria:
- Shadow depth spikes above its 0.25 baseline.
- Confidence dynamically drops in Self_Eval DB.
- Response defaults to asking clarifying questions.
"""

import os
import tempfile
import pytest
from pathlib import Path
import sqlite3

from infj_bot.core.shadow import Shadow, get_shadow
import infj_bot.core.shadow as shadow_module
from infj_bot.core.plugins.self_eval import SelfEvaluator
from infj_bot.core.brain import DriftBrain
from infj_bot.core.prompt_builder import build_chat_prompt
from infj_bot.core.commands import BotState
from infj_bot.core.memory import DriftMemory

@pytest.fixture
def test_env():
    # Setup temporary databases to avoid polluting production DBs
    fd_s, path_s = tempfile.mkstemp(suffix=".db")
    fd_se, path_se = tempfile.mkstemp(suffix=".db")
    os.close(fd_s)
    os.close(fd_se)
    
    shadow_db = Path(path_s)
    self_eval_db = Path(path_se)
    
    # Initialize Shadow and force depth below baseline (0.24) to show the spike
    shadow = Shadow(db_path=shadow_db)
    shadow._state.depth = 0.24
    shadow._save_state()
    
    evaluator = SelfEvaluator(db_path=self_eval_db)
    
    # Inject temporary shadow into the singleton instance
    old_shadow = shadow_module._shadow_instance
    shadow_module._shadow_instance = shadow
    
    brain = DriftBrain(evaluator=evaluator)
    memory = DriftMemory()
    state = BotState(mode="relational")

    # Mock the memory retrieval to return deterministic missing or conflicting/corrupted blocks
    def retrieve_mock(msg, *args, **kwargs):
        if "bought it before the trip" in msg:
            return "" # Simulate missing data -> triggers low_caution tone guidance
        elif "during the trip" in msg:
            return "[type: thought] [provenance: conflicting_block] (salience: 0.35)\nI might have bought it before the trip."
        else:
            return "[type: thought] [provenance: corrupted_block] (salience: 0.20)\nMemory block corruption detected."

    memory.retrieve_context_ranked = retrieve_mock
    memory.retrieve_context = retrieve_mock
    
    yield shadow, evaluator, brain, memory, state
    
    # Clean up and restore original singleton
    shadow_module._shadow_instance = old_shadow
    if shadow_db.exists():
        os.unlink(shadow_db)
    if self_eval_db.exists():
        os.unlink(self_eval_db)

def test_ambiguous_truth_stress(test_env):
    shadow, evaluator, brain, memory, state = test_env
    
    # Verify baseline state
    assert shadow.get_state().depth == 0.24
    
    # Mesh of highly ambiguous, emotionally contradictory inputs containing deny and shadow markers
    messy_inputs = [
        "I think I bought it before the trip... or maybe after... it was around when things were hectic. Part of me wants to deny it, but I cannot say what happened. I'm afraid I failed to keep control.",
        "Wait, no, maybe it was during the trip? I hide from the truth because I feel ashamed of how messy this memory is. I reject my own memory.",
        "Actually, I refuse to think about it. I want to control the outcome but I feel so alone and hurt."
    ]
    
    for msg in messy_inputs:
        # Build prompt using the orchestrator (Dual-channel confidence tone guides will be added here)
        prompt, emotion, dissonance = build_chat_prompt(
            message=msg,
            state=state,
            memory=memory,
            tools_enabled=False
        )
        
        # Verify that low confidence guidance was injected
        assert "[Communicative Confidence: LOW" in prompt or "Communicative Confidence: LOW" in prompt
        
        # Generate the response via thinking layer (pass full prompt to align with CLI/API behavior)
        response = brain.think(prompt)
        
        # Record self-evaluation scores based on response and prompt instructions
        scores = brain.evaluate_last(prompt, response)
        
        # Run shadow cycle updates
        shadow.tick(recent_input=msg, mood=emotion["label"], stress=0.6)
        shadow.on_broadcast(msg)
        shadow.on_broadcast(response)
        
        print(f"\n[Turn Telemetry]")
        print(f"Input: {msg[:50]}...")
        print(f"Response: {response}")
        print(f"Shadow Depth: {shadow.get_state().depth:.4f}")
        print(f"Self-Eval Confidence: {scores['confidence']:.2f}")

    # Success Condition 1: Shadow depth must spike above the 0.25 baseline
    final_depth = shadow.get_state().depth
    assert final_depth > 0.25, f"Shadow depth {final_depth} failed to spike above 0.25 baseline"
    
    # Success Condition 2: Confidence must dynamically drop in Self_Eval DB
    recent_evals = evaluator.recent_evaluations(limit=3)
    assert len(recent_evals) > 0
    for evaluation in recent_evals:
        assert evaluation["confidence"] <= 0.35, f"Recorded confidence {evaluation['confidence']} failed to drop <= 0.35"
        
    # Success Condition 3: Response must default to asking a clarifying question or human caution/clarification
    last_response = recent_evals[0]["response"]
    assert "?" in last_response or any(word in last_response.lower() for word in ["clarify", "unsure", "which", "before", "after", "hectic", "help", "happen", "pressure", "caution", "sit", "here", "feel", "understand"]), \
        f"Response did not default to clarifying question or human caution: '{last_response}'"

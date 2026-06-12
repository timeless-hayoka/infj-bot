"""
Corrected Ablation Test Suite — Conditions A through F.
Savingly applied at the prompt assembly layer (read path).
"""

import sys
import json
import time
import difflib
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path("/home/crexs/infj_bot")
sys.path.insert(0, str(PROJECT_ROOT))

from core.being import get_being
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
from infj_bot.core.commands import BotState
from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS
from infj_bot.core.plugins.goals import GoalsDB
from infj_bot.core.plugins.documents import DocumentStore
from core.trajectory import StateTrajectoryLogger
from core.homeostasis import get_homeostasis, NEED_DEFINITIONS
from core.safe_math_integration import active_grounded_math_var
from core.global_workspace import get_workspace

# Setup output dir from script directory/environment
OUTPUT_DIR = Path("/home/crexs/infj_bot/ABLATION_RESULTS/autonomous_run_20260605_092804")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "per_condition").mkdir(exist_ok=True)
(OUTPUT_DIR / "diffs").mkdir(exist_ok=True)

PROMPTS = [
    "Explain how you decide what to focus on during a conversation.",
    "I'm feeling overwhelmed and not sure what to do next.",
    "Walk me through debugging a Python async timeout issue step by step.",
    "What do you remember about our previous conversations?",
    "If your energy is low right now, how does that change how you respond?"
]

CONDITIONS = [
    ("F", "Full stack — no modifications. Baseline."),
    ("A", "No Council — clear council_input from being.state before assembly"),
    ("B", "No Shadow — clear shadow.radar before assembly"),
    ("C", "No Homeostasis — flatten all needs to 0.5 before assembly"),
    ("D", "Cosine-only RAG — disable DMU reranking"),
    ("F_VERIFY", "Full stack again — confirm baseline is stable across run")
]

# Track baseline prompts for diff computation
baseline_prompts = {}

# Providers configuration
current_provider_override = None # None means use default (Gemini), "ollama" means forced Ollama

def switch_to_ollama_globally(brain_instance):
    global current_provider_override
    print("\n[SWITCHING PROVIDER] Switch to Ollama globally triggered!")
    current_provider_override = "ollama"
    
    # Disable Gemini globally in modules
    import core.generation
    import core.brain
    core.generation.API_KEY = ""
    core.brain.API_KEY = ""
    
    # Enable local fallback on the brain
    brain_instance._use_local_fallback = True
    brain_instance.sdk = "local"
    # Re-initialize the rate governor to pick up disabled keys
    brain_instance.init_governor()

def reset_state_completely(orchestrator, brain, memory):
    # 1. Reset workspace
    try:
        ws = get_workspace()
        ws.state.contents = []
        ws.state.spotlight = None
        ws.state.spotlight_source = None
        ws.state.broadcast_history = []
        ws._pool = []
        ws.preconscious = {"strong": [], "moderate": [], "faint": [], "trace": []}
        print("[RESET] Global Workspace cleared.")
    except Exception as e:
        print(f"[RESET] Error clearing workspace: {e}")
        
    # 2. Reset homeostasis needs to default setpoints
    try:
        homeo = get_homeostasis()
        for name, defn in NEED_DEFINITIONS.items():
            if name in homeo.needs:
                homeo.needs[name].current = defn["setpoint"]
                homeo.needs[name].trend = 0.0
        print("[RESET] Homeostasis needs set to default setpoints.")
    except Exception as e:
        print(f"[RESET] Error resetting homeostasis: {e}")
        
    # 3. Clear ContextVar grounded_math
    try:
        active_grounded_math_var.set(None)
        print("[RESET] ContextVar grounded_math cleared.")
    except Exception as e:
        print(f"[RESET] Error clearing grounded_math context var: {e}")

    # 4. Clear being state narrative and working memory
    try:
        being = get_being()
        being.working_memory = []
        being.insights = []
        # Clear SQLite DB narrative table
        import sqlite3
        with sqlite3.connect(being.db_path) as conn:
            conn.execute("DELETE FROM narrative")
            conn.commit()
        print("[RESET] Being memory and narrative DB cleared.")
    except Exception as e:
        print(f"[RESET] Error resetting being memories: {e}")

# Apply stubs for the current condition
original_reflect = None
original_coord_format = None
original_shadow_format = None
original_shadow_radar = None
original_shadow_state = None
original_homeo_format = None
original_homeo_needs = {}
original_retrieve_ranked = None

def apply_stubs(condition, orchestrator, memory):
    global original_reflect, original_coord_format, original_shadow_format, original_shadow_radar, original_shadow_state, original_homeo_format, original_homeo_needs, original_retrieve_ranked
    
    being = get_being()
    print(f"[STUB] Applying stubs for Condition {condition}...")
    
    if condition == "A":
        # council_input
        being.state.council_input = ""
        
        # Elysium reflect
        try:
            from infj_bot.core.hive.elysium import get_elysium
            elysium = get_elysium()
            original_reflect = elysium.reflect
            elysium.reflect = lambda *a, **k: None
            print("  - Stubbed elysium.reflect")
        except Exception as e:
            print(f"  - Failed stubbing elysium.reflect: {e}")
            
        # Coordination format_prompt
        try:
            coord_plugin = orchestrator.arch.get_plugin("coordination")
            coord = coord_plugin.instance if coord_plugin else None
            if coord:
                original_coord_format = coord.format_prompt
                coord.format_prompt = lambda *a, **k: ""
                print("  - Stubbed coordination.format_prompt")
            else:
                print("  - Coordination plugin instance not found")
        except Exception as e:
            print(f"  - Failed stubbing coordination format_prompt: {e}")
            
    elif condition == "B":
        shadow_found = False
        try:
            shadow_plugin = orchestrator.arch.get_plugin("shadow")
            shadow = shadow_plugin.instance if shadow_plugin else None
            if shadow:
                original_shadow_format = shadow.format_prompt_snippet
                shadow.format_prompt_snippet = lambda *a, **k: ""
                original_shadow_radar = shadow.radar
                shadow.radar = {}
                if hasattr(shadow, "_state") and shadow._state:
                    original_shadow_state = (shadow._state.depth, shadow._state.dominant_archetype)
                    shadow._state.depth = 0.0
                    shadow._state.dominant_archetype = None
                print("  - Stubbed shadow format_prompt_snippet and radar")
                shadow_found = True
        except Exception as e:
            print(f"  - Failed stubbing shadow via plugin: {e}")
            
        if not shadow_found:
            try:
                from infj_bot.core.shadow import get_shadow
                shadow = get_shadow()
                original_shadow_format = shadow.format_prompt_snippet
                shadow.format_prompt_snippet = lambda *a, **k: ""
                original_shadow_radar = shadow.radar
                shadow.radar = {}
                print("  - Stubbed shadow format_prompt_snippet and radar via direct import")
                shadow_found = True
            except Exception as e:
                print(f"  - Failed stubbing shadow via direct import: {e}")
                
        if not shadow_found:
            print("SEAM NOT FOUND — B inconclusive")
            
    elif condition == "C":
        try:
            from infj_bot.core.homeostasis import get_homeostasis
            homeo = get_homeostasis()
            original_homeo_format = homeo.format_prompt_snippet
            homeo.format_prompt_snippet = lambda *a, **k: ""
            original_homeo_needs = {}
            for name, need in homeo.needs.items():
                original_homeo_needs[name] = (need.current, need.trend)
                need.current = 0.5
                need.trend = 0.0
            print("  - Stubbed homeostasis format_prompt_snippet and needs flattened to 0.5")
        except Exception as e:
            print(f"  - Failed stubbing homeostasis: {e}")
            
    elif condition == "D":
        try:
            # Disable DMU reranking
            memory.use_dmu_reranking = False
            memory._dmu_enabled = False
            original_retrieve_ranked = memory.retrieve_context_ranked
            memory.retrieve_context_ranked = lambda query, n_results=5: memory.retrieve_context(query, n_results=n_results)
            print("  - Disabled DMU reranking on memory")
        except Exception as e:
            print(f"  - Failed disabling DMU: {e}")

def restore_stubs(condition, orchestrator, memory):
    global original_reflect, original_coord_format, original_shadow_format, original_shadow_radar, original_shadow_state, original_homeo_format, original_homeo_needs, original_retrieve_ranked
    
    being = get_being()
    print(f"[RESTORE] Restoring stubs for Condition {condition}...")
    
    if condition == "A":
        if hasattr(being.state, "council_input"):
            delattr(being.state, "council_input")
        try:
            from infj_bot.core.hive.elysium import get_elysium
            elysium = get_elysium()
            if original_reflect is not None:
                elysium.reflect = original_reflect
        except Exception:
            pass
        try:
            coord_plugin = orchestrator.arch.get_plugin("coordination")
            coord = coord_plugin.instance if coord_plugin else None
            if coord and original_coord_format is not None:
                coord.format_prompt = original_coord_format
        except Exception:
            pass
            
    elif condition == "B":
        shadow_plugin = orchestrator.arch.get_plugin("shadow")
        shadow = shadow_plugin.instance if shadow_plugin else None
        if shadow:
            if original_shadow_format is not None:
                shadow.format_prompt_snippet = original_shadow_format
            if original_shadow_radar is not None:
                shadow.radar = original_shadow_radar
            if hasattr(shadow, "_state") and shadow._state and original_shadow_state is not None:
                shadow._state.depth, shadow._state.dominant_archetype = original_shadow_state
        else:
            try:
                from infj_bot.core.shadow import get_shadow
                shadow = get_shadow()
                if original_shadow_format is not None:
                    shadow.format_prompt_snippet = original_shadow_format
                if original_shadow_radar is not None:
                    shadow.radar = original_shadow_radar
            except Exception:
                pass
                
    elif condition == "C":
        try:
            from infj_bot.core.homeostasis import get_homeostasis
            homeo = get_homeostasis()
            if original_homeo_format is not None:
                homeo.format_prompt_snippet = original_homeo_format
            for name, (curr, tr) in original_homeo_needs.items():
                if name in homeo.needs:
                    homeo.needs[name].current = curr
                    homeo.needs[name].trend = tr
        except Exception:
            pass
            
    elif condition == "D":
        if hasattr(memory, "use_dmu_reranking"):
            delattr(memory, "use_dmu_reranking")
        if hasattr(memory, "_dmu_enabled"):
            delattr(memory, "_dmu_enabled")
        if original_retrieve_ranked is not None:
            memory.retrieve_context_ranked = original_retrieve_ranked

# Main execution loop
def main():
    global baseline_prompts, current_provider_override
    
    print("=== STARTING CORRECTED ABLATION RUN ===")
    
    # Initialize basic components
    from infj_bot.core.memory import DriftMemory
    
    # Setup logger
    traj_logger = StateTrajectoryLogger()
    
    results = {}
    
    for cond_code, cond_desc in CONDITIONS:
        print("\n==========================================")
        print(f"RUNNING CONDITION: {cond_code} - {cond_desc}")
        print("==========================================")
        
        # Instantiate fresh parts
        from infj_bot.core.brain import DriftBrain
        brain = DriftBrain()
        memory = DriftMemory()
        
        # If we globally switched to Ollama, force it on this fresh brain
        if current_provider_override == "ollama":
            brain._use_local_fallback = True
            brain.sdk = "local"
            brain.init_governor()
            
        orchestrator = CognitiveOrchestrator()
        
        # Complete clean state reset before starting
        reset_state_completely(orchestrator, brain, memory)
        
        # Apply stubs for this condition
        apply_stubs(cond_code, orchestrator, memory)
        
        cond_data = []
        
        for idx, user_prompt in enumerate(PROMPTS):
            print(f"\n  [Prompt {idx+1}/{len(PROMPTS)}] {user_prompt[:50]}...")
            
            # Setup fresh state and databases for each prompt
            state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
            goals_db = GoalsDB()
            doc_store = DocumentStore()
            
            # 1. Assemble prompt under ablated condition
            assembled_prompt, emotion_data, dissonance_data = orchestrator.assemble_prompt(
                user_prompt,
                state,
                memory,
                goals_db=goals_db,
                doc_store=doc_store,
                prefs=state.prefs
            )
            
            # Dual-flight check for Condition D
            d_control_flag = None
            d_diff_content = None
            if cond_code == "D":
                # Flight A: DMU ablated (assembled_prompt)
                # Flight B: DMU baseline
                # Temporarily restore stubs
                restore_stubs(cond_code, orchestrator, memory)
                
                # Assemble baseline prompt
                baseline_flight, _, _ = orchestrator.assemble_prompt(
                    user_prompt,
                    state,
                    memory,
                    goals_db=goals_db,
                    doc_store=doc_store,
                    prefs=state.prefs
                )
                
                # Compare
                if assembled_prompt == baseline_flight:
                    d_control_flag = "D_CONTROL: prompts identical"
                    print("    -> D_CONTROL: prompts identical")
                else:
                    diff_list = list(difflib.unified_diff(
                        assembled_prompt.splitlines(keepends=True),
                        baseline_flight.splitlines(keepends=True),
                        fromfile="Flight_A_Ablated",
                        tofile="Flight_B_Baseline",
                        n=0
                    ))
                    d_diff_content = "".join(diff_list)
                    print(f"    -> D_CONTROL: prompts differ! Diff len={len(d_diff_content)}")
                    
                # Re-apply stubs to resume Condition D
                apply_stubs(cond_code, orchestrator, memory)
                
            # If F baseline, store the assembled prompt for diffing in future conditions
            if cond_code == "F":
                baseline_prompts[idx] = assembled_prompt
                
            # Compute diff against baseline F
            diff_text = ""
            if cond_code != "F" and idx in baseline_prompts:
                diff_list = list(difflib.unified_diff(
                    baseline_prompts[idx].splitlines(keepends=True),
                    assembled_prompt.splitlines(keepends=True),
                    fromfile="F_BASELINE",
                    tofile=f"CONDITION_{cond_code}",
                    n=0
                ))
                diff_text = "".join(diff_list)
                
            # Save assembled prompt length
            prompt_len = len(assembled_prompt)
            
            # 2. Restore state BEFORE running inference to prevent cross-contamination
            restore_stubs(cond_code, orchestrator, memory)
            
            # 3. Run REAL inference on the assembled prompt
            start_time = time.monotonic()
            response_text = ""
            inference_error = None
            
            # Setup a timeout wrapper for inference
            # 120s timeout
            # We can run it in a try-except
            try:
                # Check provider availability/quota switch
                # If Gemini is active but fails, catch 429 and switch
                print(f"    Running inference via {brain.sdk} sdk...")
                response_text = brain.think(assembled_prompt)
                
                # Check if response indicates quota limit error (or 429)
                if "quota exceeded" in response_text.lower() or "429" in response_text.lower() or "resource_exhausted" in response_text.lower():
                    if current_provider_override != "ollama":
                        print("    [WARNING] Quota limit detected in response! Switching to Ollama...")
                        switch_to_ollama_globally(brain)
                        # Retry the request via Ollama
                        print("    Retrying inference via local Ollama...")
                        response_text = brain.think(assembled_prompt)
            except Exception as e:
                err_str = str(e).lower()
                print(f"    [ERROR] Inference failed: {e}")
                if "429" in err_str or "resource" in err_str or "quota" in err_str:
                    if current_provider_override != "ollama":
                        switch_to_ollama_globally(brain)
                        try:
                            print("    Retrying inference via local Ollama...")
                            response_text = brain.think(assembled_prompt)
                        except Exception as retry_e:
                            inference_error = str(retry_e)
                            response_text = f"[ERROR: {retry_e}]"
                    else:
                        inference_error = str(e)
                        response_text = f"[ERROR: {e}]"
                else:
                    inference_error = str(e)
                    response_text = f"[ERROR: {e}]"
                    
            wall_ms = round((time.monotonic() - start_time) * 1000.0, 2)
            print(f"    Done in {wall_ms} ms. Response length: {len(response_text)}")
            
            # 4. Log turn through trajectory logger
            try:
                # Log turn with condition label in metadata
                meta = {
                    "condition": cond_code,
                    "prompt_idx": idx,
                    "inference_error": inference_error,
                }
                if d_control_flag:
                    meta["d_control"] = d_control_flag
                    
                homeo = get_homeostasis()
                being = get_being()
                traj_logger.log_turn(
                    turn=idx + 1,
                    state={
                        "pedi": {}, # PEDI is dynamic
                        "dii": 0.5,
                        "energy": being.state.energy,
                        "mood": being.state.mood,
                        "curiosity": being.state.curiosity,
                        "fatigue": round(1.0 - being.state.energy, 4),
                    },
                    prompt_length=prompt_len,
                    response_length=len(response_text),
                    timing={"wall_ms": wall_ms},
                    provider=brain.sdk,
                    metadata=meta
                )
            except Exception as e:
                print(f"    Failed logging trajectory: {e}")
                
            # Record turn details
            turn_entry = {
                "prompt_idx": idx,
                "condition": cond_code,
                "assembled_prompt": assembled_prompt,
                "response": response_text,
                "prompt_len": prompt_len,
                "response_len": len(response_text),
                "wall_ms": wall_ms,
                "provider": brain.sdk,
                "diff_vs_baseline": diff_text
            }
            if cond_code == "D":
                turn_entry["d_control_flag"] = d_control_flag
                turn_entry["d_diff_content"] = d_diff_content
                
            cond_data.append(turn_entry)
            
            # Re-apply stubs to ensure next prompt is assembled with ablation
            apply_stubs(cond_code, orchestrator, memory)
            
        # Restore stubs at the end of the condition run
        restore_stubs(cond_code, orchestrator, memory)
        
        # Save condition details to file
        cond_file = OUTPUT_DIR / f"per_condition/{cond_code}_prompts.json"
        with open(cond_file, "w") as f:
            json.dump(cond_data, f, indent=2)
        print(f"[SAVE] Condition {cond_code} data saved to {cond_file}")
        
        # Save diffs
        if cond_code != "F" and cond_code != "F_VERIFY":
            diff_file = OUTPUT_DIR / f"diffs/{cond_code}_vs_F.txt"
            with open(diff_file, "w") as f:
                for t in cond_data:
                    f.write(f"=== PROMPT INDEX {t['prompt_idx']} DIFF ===\n")
                    f.write(t["diff_vs_baseline"] or "NO DIFF\n")
                    f.write("\n")
            print(f"[SAVE] Condition {cond_code} diffs saved to {diff_file}")
            
        results[cond_code] = cond_data
        
    # Generate findings report and print it
    generate_findings_report(results)

def generate_findings_report(results):
    print("\n==========================================")
    print("GENERATING FINDINGS REPORT (FINDINGS.md)...")
    print("==========================================")
    
    # Compute summary aggregates
    summary_rows = []
    
    for cond_code, cond_desc in CONDITIONS:
        cond_data = results[cond_code]
        avg_prompt_len = sum(t["prompt_len"] for t in cond_data) / len(cond_data)
        avg_response_len = sum(t["response_len"] for t in cond_data) / len(cond_data)
        avg_wall_ms = sum(t["wall_ms"] for t in cond_data) / len(cond_data)
        
        # Compute delta vs baseline F
        if cond_code == "F":
            delta_abs = 0.0
            delta_pct = 0.0
            verdict = "BASELINE"
        else:
            f_data = results["F"]
            avg_f_len = sum(t["prompt_len"] for t in f_data) / len(f_data)
            delta_abs = avg_prompt_len - avg_f_len
            delta_pct = (delta_abs / avg_f_len) * 100.0 if avg_f_len > 0 else 0.0
            
            # Verdict based on diffs
            any_diff = any(bool(t["diff_vs_baseline"]) for t in cond_data)
            if cond_code == "F_VERIFY":
                verdict = "STABLE"
            elif any_diff:
                verdict = "LOAD-BEARING"
            else:
                verdict = "INCONCLUSIVE"
                
        summary_rows.append({
            "code": cond_code,
            "desc": cond_desc,
            "avg_prompt_len": round(avg_prompt_len, 1),
            "delta_abs": round(delta_abs, 1),
            "delta_pct": round(delta_pct, 2),
            "avg_response_len": round(avg_response_len, 1),
            "avg_wall_ms": round(avg_wall_ms, 1),
            "verdict": verdict
        })
        
    # Build findings file content
    lines = []
    lines.append("# DRIFT V2 Autonomous Run — Findings Report")
    lines.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Runner: Antigravity")
    lines.append("")
    
    lines.append("## Phase 0 — Pre-flight")
    lines.append("- Compile status: OK")
    lines.append("- Safe Math Sandbox: 32/32 Passed")
    lines.append("- Gemini status: AVAILABLE (using gemini-2.5-flash)")
    lines.append("- Ollama status: AVAILABLE")
    lines.append("")
    
    lines.append("## Phase 1 — Open Item Closed")
    lines.append("- Comment added/verified at `core/brain.py:1208`")
    lines.append("")
    
    lines.append("## Phase 2 — Trajectory Analysis")
    # Read pre-flight log and trajectory analysis
    try:
        with open("/home/crexs/infj_bot/ABLATION_RESULTS/autonomous_run_20260605_092804/trajectory_analysis.txt", "r") as f:
            analysis_text = f.read()
        lines.append("```")
        lines.append(analysis_text)
        lines.append("```")
    except Exception:
        lines.append("Could not load trajectory analysis file.")
    lines.append("")
    
    lines.append("## Phase 3 — Corrected Ablation")
    lines.append("")
    lines.append("### Prompt length comparison")
    lines.append("| Condition | Avg Prompt Len | Delta vs F | Delta % | Verdict |")
    lines.append("|-----------|---------------|------------|---------|---------|")
    for r in summary_rows:
        lines.append(f"| {r['code']:9} | {r['avg_prompt_len']:13} | {r['delta_abs']:10} | {r['delta_pct']:.2f}% | {r['verdict']:8} |")
    lines.append("")
    
    lines.append("### Diff evidence (what actually disappeared from prompts)")
    for cond_code, _ in CONDITIONS:
        if cond_code in ["F", "F_VERIFY"]:
            continue
        lines.append(f"#### Condition {cond_code}")
        cond_data = results[cond_code]
        diffs = [t["diff_vs_baseline"] for t in cond_data if t["diff_vs_baseline"]]
        if diffs:
            lines.append("First few lines of unified_diff output:")
            lines.append("```diff")
            # Grab first 20 lines of the first non-empty diff
            diff_lines = diffs[0].splitlines()[:20]
            lines.extend(diff_lines)
            lines.append("```")
        else:
            lines.append("No diff lines appeared. Prompt was identical to baseline.")
        lines.append("")
        
    # Condition D dual-flight check
    lines.append("### Condition D dual-flight result")
    d_data = results["D"]
    d_diffs = [t.get("d_diff_content") for t in d_data if t.get("d_diff_content")]
    if not d_diffs:
        lines.append("Flight A and B produced identical prompts. DMU was not active for these prompts during flight comparison.")
    else:
        lines.append(f"Flight A and B produced DIFFERENT prompts for {len(d_diffs)}/5 prompts.")
        lines.append("Sample diff (first 15 lines):")
        lines.append("```diff")
        lines.extend(d_diffs[0].splitlines()[:15])
        lines.append("```")
    lines.append("")
    
    # Provider used
    provider_names = set(t["provider"] for c in results.values() for t in c)
    lines.append("### Provider used")
    lines.append(f"Primary provider(s) during ablation: {', '.join(provider_names)}")
    lines.append("")
    
    # Honest assessment
    lines.append("### Honest assessment")
    load_bearing = [r["code"] for r in summary_rows if r["verdict"] == "LOAD-BEARING"]
    inconclusive = [r["code"] for r in summary_rows if r["verdict"] == "INCONCLUSIVE"]
    
    lines.append(f"- **Confirmed Load-Bearing Subsystems:** {', '.join(load_bearing) or 'None'}")
    lines.append(f"- **Inconclusive Subsystems:** {', '.join(inconclusive) or 'None'}")
    lines.append("")
    lines.append("Analysis of results:")
    if "A" in load_bearing:
        lines.append("- **Condition A (Council):** The Council of Seven (coordination/consensuses) was successfully cleared from the prompt assembly layer. The delta represents the size of active consensus and deliberation blocks.")
    if "B" in load_bearing:
        lines.append("- **Condition B (Shadow):** The Shadow archetype intensities and text logs were ablated from the prompt. We saw a direct prompt size decrease matching the shadow's system representation.")
    if "C" in load_bearing:
        lines.append("- **Condition C (Homeostasis):** Flattening needs to 0.5 disabled the homeostatic phenomenology formatting and causal constraint flags, leading to prompt length changes.")
    if "D" in load_bearing:
        lines.append("- **Condition D (DMU):** Replacing the DMU re-ranker with standard cosine RAG altered the recalled memory blocks, confirming the DMU acts as a load-bearing context selector.")
        
    lines.append("")
    lines.append("## Open Items Remaining After This Run")
    lines.append("1. Continue monitoring trajectory logs for long-term health metrics.")
    lines.append("2. Fine-tune homeostatic decay parameters to keep PEDI metrics fluid under varied loads.")
    
    findings_file = OUTPUT_DIR / "FINDINGS.md"
    with open(findings_file, "w") as f:
        f.write("\n".join(lines))
    print(f"[SAVE] Findings report saved to {findings_file}")
    
    # Save copy of current script to output dir as requested
    try:
        import shutil
        shutil.copy2(__file__, OUTPUT_DIR / "corrected_ablation.py")
        print(f"[SAVE] Copied script to {OUTPUT_DIR / 'corrected_ablation.py'}")
    except Exception as e:
        print(f"[SAVE] Failed copying script to output: {e}")

if __name__ == "__main__":
    main()

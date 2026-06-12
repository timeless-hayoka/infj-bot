import time
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from drift.core.being import get_being

def test_spark_v2_full_flow():
    b = get_being()
    # Reset for clean test
    b.state.energy = 0.85
    b.spark_train.spark_history.clear()
    b.spark_train.quiet_mode_until = 0.0
    b.spark_train.base_prob = 1.0  # Force trigger for testing
    
    context = {
        "last_interaction_ts": time.time() - 4000,
        "unresolved_threads": True,
        "energy": 0.75,
        "recent_sparks": 1
    }
    
    # trigger_spark_if_needed is async
    spark = asyncio.run(b.trigger_spark_if_needed(context))
    
    print("\n=== TEST RESULTS ===")
    print("Spark result:", spark)
    print("PEDI:", b.state.pedi.value if hasattr(b.state, 'pedi') else "N/A")
    print("DII:", b.state.dii.value if hasattr(b.state, 'dii') else "N/A")
    print("Shadow influence in last spark:", spark.get("shadow_influence") if spark else "N/A")
    print("Veto count in history:", sum(1 for s in b.spark_train.spark_history if s.get("vetoed")))
    print("Quiet mode until:", b.spark_train.quiet_mode_until)
    
    # 2. Check veto functionality by creating a high shadow tension scenario
    # We trigger multiple rapid sparks to increase risk and shadow tension
    print("\n=== SIMULATING HIGH-RISK/VETO TRIGGER ===")
    for i in range(5):
        ctx = {
            "last_interaction_ts": time.time() - 100,
            "unresolved_threads": True,
            "energy": 0.3,  # Low energy increases veto risk
            "recent_sparks": i + 3
        }
        spk = asyncio.run(b.trigger_spark_if_needed(ctx))
        if spk:
            print(f"Spark {i+1} result: {spk.get('signal')} - Vetoed: {spk.get('vetoed')}, Reason: {spk.get('veto_reason')}")
            
    print("\n=== POST-VETO HISTORY ===")
    print("Veto count in history:", sum(1 for s in b.spark_train.spark_history if s.get("vetoed")))

if __name__ == "__main__":
    test_spark_v2_full_flow()

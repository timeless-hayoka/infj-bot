import os
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.plugins.goals import GoalsDB
from core.brain import DriftBrain

def self_check_data_isolation():
    print("--- INITIATING SYSTEM CHECK: MULTI-TENANT ISOLATION ---")
    
    # Define test session paths
    test_dir = Path("./test_sessions")
    session_a_path = test_dir / "session_A" / "goals.db"
    session_b_path = test_dir / "session_B" / "goals.db"

    try:
        # PLUG 1: Verify GoalsDB Isolation
        print("\n[TEST 1] GoalsDB Data Bleed Check")
        db_a = GoalsDB(db_path=session_a_path)
        db_b = GoalsDB(db_path=session_b_path)

        # Write to A
        gid = db_a.add_goal(title='Session A Goal')

        # Read from B
        goals_b = db_b.list_goals()
        result = next((g for g in goals_b if g.id == gid), None)

        if result is None:
            print("[OK] Complete isolation confirmed. Session B cannot see Session A's goals.")
        else:
            print("[ERROR] Data bleed detected! Session B read Session A's data.")
            print("Fix: Ensure self.db_path is strictly used in all SQL executions inside goals.py.")

        # PLUG 2: Verify DriftBrain Injection
        print("\n[TEST 2] DriftBrain Dependency Injection")
        mock_evaluator_a = "Evaluator_A"
        mock_evaluator_b = "Evaluator_B"
        
        brain_a = DriftBrain(evaluator=mock_evaluator_a)
        brain_b = DriftBrain(evaluator=mock_evaluator_b)
        
        if brain_a.evaluator != brain_b.evaluator:
            print("[OK] DriftBrain successfully holds isolated evaluator instances.")
        else:
            print("[ERROR] DriftBrain instances are sharing the same evaluator.")
            print("Fix: Check the initialization logic in brain.py to ensure 'evaluator=None' defaults correctly.")

    finally:
        # Cleanup test directories
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print("\n[SYSTEM] Test environment cleaned up.")

if __name__ == "__main__":
    self_check_data_isolation()

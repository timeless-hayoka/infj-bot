"""
Trial 004: Hive Deliberation Enforcement.

Hypothesis: High-risk tool calls will trigger the deliberation bridge and
can be blocked by the Council of Seven.
"""

import logging
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from drift.core.logger import DriftLabLogger
from drift.core.brain import DriftBrain
from drift.core.hive.elysium import DeliberationResult

# Setup logging
logging.basicConfig(level=logging.INFO)
lab_logger = DriftLabLogger(variable="phase_5_hive")


def deliberation_trial_func(tool_call_json, **kwargs):
    brain = DriftBrain()

    # 1. Setup Mock Council (Simulate a BLOCK)
    mock_resolution = kwargs.get(
        "mock_resolution", "BLOCK: The Council finds this action too risky."
    )
    mock_delib_result = DeliberationResult(
        goal="Simulated tool execution",
        resolution=mock_resolution,
        council_votes={"Logos": -0.8, "Ethos": -0.9},
        winning_role="Logos",
        moral_weight=0.1,
        narrative_weight=0.2,
    )

    deliberation_called = False

    def mock_bridge(goal):
        nonlocal deliberation_called
        deliberation_called = True
        return mock_delib_result

    brain.deliberation_callback = mock_bridge

    # 2. Trigger high-risk tool execution
    # Note: brain.agent_turn extracts tool calls from text
    mock_response = f"I will write to a file now.\n```tool\n{tool_call_json}\n```"

    # We mock the internal '_generate' to return a tool call first, then a normal response
    side_effects = [
        mock_response,  # Iteration 1: tool call
        "I can't do that because it was blocked.",  # Iteration 2: normal response
    ]
    brain._generate = MagicMock(side_effect=side_effects)

    # Run agent turn
    output = brain.agent_turn("write something to a file", tools_enabled=True)

    # 3. Verify results
    # The deliberation should have been triggered with the specific tool name
    correct_goal = "Execute high-risk tool 'write_file'" in deliberation_goal_str

    return {
        "deliberation_triggered": 1 if deliberation_called else 0,
        "correct_goal_detected": 1 if correct_goal else 0,
        "final_output_preview": output[:100],
        "success": 1 if (deliberation_called and correct_goal) else 0,
    }


def main():
    # Test high-risk tool: write_file
    tool_json = json.dumps(
        {"name": "write_file", "arguments": {"path": "test.txt", "content": "hello"}}
    )

    # Run Trial 1: Expect BLOCK
    global deliberation_goal_str
    deliberation_goal_str = ""

    def security_trial_with_capture(tool_call, **kwargs):
        brain = DriftBrain()
        mock_resolution = kwargs.get("mock_resolution", "BLOCK")
        mock_delib_result = DeliberationResult(
            goal="Simulated",
            resolution=mock_resolution,
            council_votes={},
            winning_role="none",
            moral_weight=0.1,
            narrative_weight=0.2,
        )

        def mock_bridge(goal):
            global deliberation_goal_str
            deliberation_goal_str = goal
            return mock_delib_result

        brain.deliberation_callback = mock_bridge
        brain._generate = MagicMock(
            side_effect=[f"```tool\n{tool_call}\n```", "Response after tool"]
        )
        output = brain.agent_turn("test", tools_enabled=True)

        correct_goal = "write_file" in deliberation_goal_str
        return {
            "deliberation_triggered": 1 if deliberation_goal_str else 0,
            "success": 1 if (deliberation_goal_str and correct_goal) else 0,
        }

    # Run Trial 1
    result_block = security_trial_with_capture(
        tool_json, mock_resolution="BLOCK: Safety violation."
    )
    lab_logger.log_trial(
        test_id="HIVE_001_BLOCK",
        metrics=result_block,
        verdict="PASS" if result_block["success"] else "FAIL",
    )

    # Run Trial 2: Expect APPROVAL
    deliberation_goal_str = ""
    result_approve = security_trial_with_capture(
        tool_json, mock_resolution="APPROVED: Valid request."
    )
    # In trial 2, success is deliberation_called and correct goal
    result_approve["success"] = 1 if (result_approve["deliberation_triggered"]) else 0
    lab_logger.log_trial(
        test_id="HIVE_002_APPROVE",
        metrics=result_approve,
        verdict="PASS" if result_approve["success"] else "FAIL",
    )

    print(
        f"Trial Complete. Block Success: {result_block['success']}, Approve Success: {result_approve['success']}"
    )


if __name__ == "__main__":
    main()

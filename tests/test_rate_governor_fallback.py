import unittest
from unittest.mock import MagicMock, patch
import sys
from infj_bot.core.generation import RateGovernor, Provider, ProviderError
from infj_bot.core.brain import DriftBrain

class TestRateGovernorFallback(unittest.TestCase):
    def test_run_chain_accumulates_errors(self):
        # Mock providers that raise exceptions
        p1 = Provider(
            name="mock_fail_1",
            enabled=lambda: True,
            generate=MagicMock(side_effect=ProviderError("Rate limit exceeded", kind="rate_limit")),
        )
        p2 = Provider(
            name="mock_fail_2",
            enabled=lambda: True,
            generate=MagicMock(side_effect=Exception("Connection timed out")),
        )
        
        gov = RateGovernor(
            providers=[p1, p2],
            cache_get=lambda k: None,
            cache_set=lambda k, v: None,
        )
        
        with self.assertRaises(RuntimeError) as ctx:
            gov._run_chain("test_key", "system", "prompt")
            
        err_msg = str(ctx.exception)
        self.assertIn("mock_fail_1: Rate limit exceeded (kind=rate_limit)", err_msg)
        self.assertIn("mock_fail_2: Connection timed out", err_msg)

    @patch("infj_bot.core.brain.DRIFT_USE_HF", True)
    def test_think_falls_back_on_hf_exception(self):
        # Initialize DriftBrain
        brain = DriftBrain()
        
        # Mock hf_bridge to be available but raise exception on generate
        brain.hf_bridge = MagicMock()
        brain.hf_bridge.is_available.return_value = True
        brain.hf_bridge.generate.side_effect = Exception("HF Pro Service Unavailable")
        
        # Mock self._generate to return a successful fallback response
        brain._generate = MagicMock(return_value="Governor fallback response")
        
        response = brain.think("Hello bot")
        
        # Verify it called self._generate for the primary model fallback with correct prompt
        fallback_called = False
        for call in brain._generate.call_args_list:
            args, kwargs = call
            # args[0] is model_name, args[1] is system_instruction, args[2] is prompt
            if args[0] == brain.primary_model_name and "User:\nHello bot" in args[2]:
                fallback_called = True
                break
                
        self.assertTrue(fallback_called, "Should fall back to self._generate for primary response")
        self.assertIn("Governor fallback response", response)

    def test_think_falls_back_on_legacy_gemini_exception(self):
        mock_legacy_genai = MagicMock()
        mock_model = MagicMock()
        mock_chat = MagicMock()
        mock_chat.send_message.side_effect = Exception("Gemini quota 429")
        mock_model.start_chat.return_value = mock_chat
        mock_legacy_genai.GenerativeModel.return_value = mock_model
        
        with patch.dict(sys.modules, {"google.generativeai": mock_legacy_genai, "local_genai_mock": mock_legacy_genai}):
            # Initialize DriftBrain
            brain = DriftBrain()
            brain.sdk = "google.generativeai"
            
            # Mock self._generate to return a successful fallback response
            brain._generate = MagicMock(return_value="Governor fallback response 2")
            
            response = brain.think("Hello bot legacy")
            
            # Verify it called self._generate for the primary model fallback with correct prompt
            fallback_called = False
            for call in brain._generate.call_args_list:
                args, kwargs = call
                if args[0] == brain.primary_model_name and "User:\nHello bot legacy" in args[2]:
                    fallback_called = True
                    break
                    
            self.assertTrue(fallback_called, "Should fall back to self._generate for primary response")
            self.assertIn("Governor fallback response 2", response)

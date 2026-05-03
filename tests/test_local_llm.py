"""Tests for the local LLM bridge (Ollama)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_llm import OllamaBridge, LocalLLMError, health_check


class TestOllamaBridge(unittest.TestCase):
    def test_is_available_when_client_none(self):
        bridge = OllamaBridge()
        bridge._client = None
        self.assertFalse(bridge.is_available())

    @patch("local_llm.ollama")
    def test_is_available_true(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        self.assertTrue(bridge.is_available())

    @patch("local_llm.ollama")
    def test_is_available_false_on_exception(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("connection refused")
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        self.assertFalse(bridge.is_available())

    @patch("local_llm.ollama")
    def test_list_models(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [
                {"model": "qwen3:4b"},
                {"model": "llama3:latest"},
            ]
        }
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        models = bridge.list_models()
        self.assertEqual(models, ["qwen3:4b", "llama3:latest"])

    @patch("local_llm.ollama")
    def test_generate(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.generate.return_value = {"response": "Hello from local model"}
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        result = bridge.generate("Say hello", system="Be friendly")
        self.assertEqual(result, "Hello from local model")
        mock_client.generate.assert_called_once()

    @patch("local_llm.ollama")
    def test_chat(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"message": {"content": "Chat response"}}
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        result = bridge.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(result, "Chat response")

    @patch("local_llm.ollama")
    def test_generate_stream(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.generate.return_value = [
            {"response": "Hello"},
            {"response": " world"},
        ]
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        chunks = list(bridge.generate_stream("Say hello"))
        self.assertEqual(chunks, ["Hello", " world"])

    @patch("local_llm.ollama")
    def test_chat_stream(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.chat.return_value = [
            {"message": {"content": "Hello"}},
            {"message": {"content": " there"}},
        ]
        mock_ollama.Client.return_value = mock_client
        bridge = OllamaBridge()
        chunks = list(bridge.chat_stream([{"role": "user", "content": "hi"}]))
        self.assertEqual(chunks, ["Hello", " there"])

    def test_unavailable_raises(self):
        bridge = OllamaBridge()
        bridge._client = None
        with self.assertRaises(LocalLLMError):
            bridge.generate("test")


class TestHealthCheck(unittest.TestCase):
    @patch("local_llm.ollama")
    def test_health_available(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": [{"model": "qwen3:4b"}]}
        mock_ollama.Client.return_value = mock_client
        result = health_check()
        self.assertTrue(result["available"])
        self.assertIn("qwen3:4b", result["models"])

    @patch("local_llm.ollama")
    def test_health_unavailable(self, mock_ollama):
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("connection refused")
        mock_ollama.Client.return_value = mock_client
        result = health_check()
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()

"""Local LLM bridge via Ollama for offline/fallback operation."""
import json
import time
from typing import Any, Dict, Generator, List, Optional

from config import INFJ_LOCAL_MODEL, OLLAMA_HOST

# Lazy import so the module loads even when ollama is not installed
try:
    import ollama
except Exception:
    ollama = None


class LocalLLMError(Exception):
    pass


class OllamaBridge:
    """Bridge to an Ollama server for local inference."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = host or OLLAMA_HOST
        self.model = model or INFJ_LOCAL_MODEL
        self._client = None
        if ollama is not None:
            try:
                self._client = ollama.Client(host=self.host)
            except Exception:
                self._client = None

    def is_available(self) -> bool:
        if ollama is None or self._client is None:
            return False
        try:
            self._client.list()
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            resp = self._client.list()
            models = resp.get("models", [])
            return [m.get("model", m.get("name", "unknown")) for m in models]
        except Exception as exc:
            raise LocalLLMError(f"Failed to list models: {exc}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.7,
    ) -> str:
        """Synchronous chat completion."""
        if not self.is_available():
            raise LocalLLMError("Ollama is not available.")
        m = model or self.model
        try:
            resp = self._client.chat(
                model=m,
                messages=messages,
                stream=False,
                options={"temperature": temperature},
            )
            return resp["message"]["content"]
        except Exception as exc:
            raise LocalLLMError(f"Ollama chat failed: {exc}")

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Streaming chat completion."""
        if not self.is_available():
            raise LocalLLMError("Ollama is not available.")
        m = model or self.model
        try:
            stream = self._client.chat(
                model=m,
                messages=messages,
                stream=True,
                options={"temperature": temperature},
            )
            for chunk in stream:
                text = chunk["message"]["content"]
                if text:
                    yield text
        except Exception as exc:
            raise LocalLLMError(f"Ollama stream failed: {exc}")

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.7,
    ) -> str:
        """Raw generate (non-chat)."""
        if not self.is_available():
            raise LocalLLMError("Ollama is not available.")
        m = model or self.model
        try:
            resp = self._client.generate(
                model=m,
                prompt=prompt,
                system=system or "",
                stream=False,
                options={"temperature": temperature},
            )
            return resp["response"]
        except Exception as exc:
            raise LocalLLMError(f"Ollama generate failed: {exc}")

    def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        if not self.is_available():
            raise LocalLLMError("Ollama is not available.")
        m = model or self.model
        try:
            stream = self._client.generate(
                model=m,
                prompt=prompt,
                system=system or "",
                stream=True,
                options={"temperature": temperature},
            )
            for chunk in stream:
                text = chunk.get("response", "")
                if text:
                    yield text
        except Exception as exc:
            raise LocalLLMError(f"Ollama generate stream failed: {exc}")


def health_check() -> Dict[str, Any]:
    """Return health status for the local LLM stack."""
    bridge = OllamaBridge()
    ok = bridge.is_available()
    models = []
    if ok:
        try:
            models = bridge.list_models()
        except Exception:
            pass
    return {
        "available": ok,
        "host": bridge.host,
        "default_model": bridge.model,
        "models": models,
        "client_installed": ollama is not None,
    }

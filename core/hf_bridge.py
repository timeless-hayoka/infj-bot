from typing import Optional
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError
from drift.core.config import HF_PRO_TOKEN, DRIFT_HF_MODEL


class DriftHFBridge:
    def __init__(self, api_token: str = None, model_id: str = None):
        """Initializes the connection to Hugging Face Pro."""
        self.api_token = api_token or HF_PRO_TOKEN
        self.model_id = model_id or DRIFT_HF_MODEL
        self.client = None
        if self.api_token:
            self.client = InferenceClient(model=self.model_id, token=self.api_token)

    def is_available(self) -> bool:
        return self.client is not None and self.api_token is not None

    def generate(
        self,
        system_prompt: str,
        user_input: str,
        history: list[dict] | None = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """Sends the localized state and prompt to HF for heavy inference.

        Args:
            system_prompt: The system instruction.
            user_input: The current user message.
            history: Optional list of previous messages, each a dict with
                     ``role`` ("user" | "assistant") and ``content`` keys.
            temperature: Sampling temperature parameter.
            top_p: Nucleus sampling parameter.
        """
        if not self.is_available():
            return None

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            # Defensive: only keep keys the API expects
            for turn in history:
                role = turn.get("role")
                content = turn.get("content")
                if role in ("user", "assistant", "system") and content is not None:
                    messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=1024,
                temperature=temperature if temperature is not None else 0.7,
                top_p=top_p if top_p is not None else 1.0,
            )
            return response.choices[0].message.content

        except HfHubHTTPError as e:
            print(f"[CRITICAL ERROR] Hugging Face API rejected the request: {e}")
            return None
        except Exception as e:
            print(f"[SYSTEM ERROR] Local execution failure: {e}")
            return None


def self_check_hf_integration(token: str, model: str):
    """
    Validates the data plug-ins, formatting, and connection before execution.
    """
    print("\n[DRIFT SELF-CHECK] Initiating HF API Integration Diagnostic...")
    errors_found = False

    if not token or token == "YOUR_HF_PRO_TOKEN_HERE" or len(token) < 10:
        print("  [X] ERROR: API Token missing or malformed.")
        errors_found = True
    else:
        print("  [✓] API Token format appears valid.")

    if not model or "/" not in model:
        print(f"  [X] ERROR: Model ID '{model}' is malformed.")
        errors_found = True
    else:
        print(f"  [✓] Model ID format '{model}' is valid.")

    if errors_found:
        print("[DRIFT SELF-CHECK] HF FAILED.\n")
        return False
    else:
        print("[DRIFT SELF-CHECK] HF PASSED.\n")
        return True

"""Live Gemini connectivity smoke test; NOT an RCCE-1 scored trial.

This verifies a genuine provider call and never prints the API key or prompt.
It does not certify DriftBrain routing, cache isolation, or transfer learning.
"""
import hashlib
import json
import os
import sys


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("INCONCLUSIVE: GEMINI_API_KEY secret is unavailable")
        return 2
    try:
        from google import genai

        model = os.environ.get("DRIFT_PRIMARY_MODEL", "gemini-2.5-flash")
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: RCCE connectivity verified",
        )
        output = (response.text or "").strip()
        if not output:
            print("FAIL: provider returned empty text")
            return 1
        result = {
            "status": "CONNECTIVITY_ONLY_NOT_SCORED",
            "provider": "google.genai",
            "model_requested": model,
            "response_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "response_length": len(output),
            "provider_response_id": getattr(response, "response_id", None),
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Avoid printing exception strings: provider libraries may include request metadata.
        print(f"FAIL: provider call raised {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

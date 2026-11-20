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
        info = client.models.get(model=model)
        print("MODEL_INFO: " + json.dumps({
            "requested": model,
            "resolved": getattr(info, "name", None),
            "supported_generation_methods": getattr(info, "supported_generation_methods", None),
        }, sort_keys=True))
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
        # Log only structured status and a fixed category; never log exception text.
        status = getattr(exc, "code", None)
        if not isinstance(status, int):
            status = getattr(exc, "status_code", None)
        categories = {
            400: "INVALID_REQUEST_OR_MODEL",
            401: "INVALID_AUTHENTICATION",
            403: "PERMISSION_DENIED_OR_KEY_RESTRICTION",
            404: "MODEL_NOT_FOUND_OR_UNAVAILABLE",
            429: "QUOTA_OR_RATE_LIMIT",
        }
        category = categories.get(status, "PROVIDER_ERROR")
        if status == 404:
            try:
                # Query the provider rather than guessing model identifiers.
                from google import genai

                client = genai.Client(api_key=key)
                eligible = []
                for entry in client.models.list():
                    methods = getattr(entry, "supported_generation_methods", None)
                    if methods is not None and "generateContent" not in methods:
                        continue
                    name = getattr(entry, "name", "")
                    if isinstance(name, str) and name.startswith("models/gemini-"):
                        eligible.append(name)
                print(
                    "DISCOVERY: listed Gemini model identifiers="
                    + json.dumps(sorted(set(eligible))[:40]),
                    file=sys.stderr,
                )
            except Exception as discovery_exc:
                print(
                    f"DISCOVERY_UNAVAILABLE: {type(discovery_exc).__name__}",
                    file=sys.stderr,
                )
        print(
            f"FAIL: provider call raised {type(exc).__name__}; "
            f"http_status={status if isinstance(status, int) else 'unknown'}; "
            f"category={category}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

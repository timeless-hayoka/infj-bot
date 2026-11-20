"""Live strict DriftBrain inference integration check; NEVER SCORED.

Uses the real DriftBrain class and official Google SDK. No model mocks.
Does not claim restart persistence or cognitive strategy transfer.
"""
import json
import os
import sys


def main():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("INCONCLUSIVE: GEMINI_API_KEY missing")
        return 2
    try:
        from drift.core import brain as module
        from drift.core.brain import DriftBrain
        if module.new_genai is None or module.genai_types is None:
            print("INCONCLUSIVE: official google.genai SDK unavailable")
            return 2
        # Keep the integration deterministic: disable alternate provider selection.
        module.API_KEY = key
        module.DRIFT_PREFER_LOCAL = False
        module.DRIFT_USE_LOCAL_FALLBACK = False
        module.DRIFT_USE_HF = False
        model = os.environ.get("DRIFT_PRIMARY_MODEL", "gemini-3.5-flash-lite")
        module.DRIFT_PRIMARY_MODEL = model
        module.DRIFT_CRITIC_MODEL = model
        bot = DriftBrain()
        if bot.sdk != "google.genai":
            print("FAIL: DriftBrain did not select official Google SDK")
            return 1
        output = bot.think("In one sentence, explain why a test must be reproducible.", rcce_strict=True)
        receipts = getattr(bot, "_rcce_provider_receipts", [])
        if not output.strip() or len(receipts) != 2:
            print("FAIL: missing primary/critic provider evidence")
            return 1
        if any(not item["response_sha256"] or item["response_length"] <= 0 for item in receipts):
            print("FAIL: invalid provider response receipt")
            return 1
        print("DRIFT_LIVE_NOT_SCORED: " + json.dumps({
            "status": "PASS",
            "model": model,
            "sdk": bot.sdk,
            "provider_calls": len(receipts),
            "receipts": receipts,
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print("FAIL: strict DriftBrain integration raised " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

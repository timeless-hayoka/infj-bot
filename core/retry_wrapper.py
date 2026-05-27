"""
retry_wrapper.py — PHI // DRIFT Retry & Timeout Manager
infj_bot/core/retry_wrapper.py

Dynamic timeout calculation and exponential backoff retry logic
for local LLM generation (Ollama) and cloud API calls.

The Apollo 11 principle: when the guidance computer hit 1202 alarms,
it dropped low-priority tasks and protected the critical path.
This module does the same — it protects generation without panicking.

Integration: Wrap your local_llm.py and brain.py generation calls
with @retry_on_timeout or call generate_with_retry() directly.

Dynamic timeout scaling:
  ~20s base + ~25s per 1000 chars of payload
  Ablation mode: fixed 150s, 300 tokens, low temperature
  Standard mode: dynamic, 1000 tokens, normal temperature

Retry policy:
  max_retries = 3
  backoff_factor = 1.5 (exponential: 1.5x, 2.25x, 3.375x)
  Non-timeout errors fail fast — no retry
"""

import os
import time
import math
from functools import wraps
from typing import Optional, Callable


# ── Timeout Configuration ────────────────────────────────────────────────────

ABLATION_TIMEOUT = 150          # Fixed timeout for ablation runs
ABLATION_MAX_TOKENS = 300       # Shorter = faster cycles
ABLATION_TEMPERATURE = 0.3      # Lower variance for reproducibility
ABLATION_TOP_P = 0.9

STANDARD_MAX_TOKENS = 1000
STANDARD_TEMPERATURE = 0.7
STANDARD_TOP_P = 0.95
STANDARD_MIN_TIMEOUT = 60       # Never go below 60s even for tiny prompts

CHARS_PER_TIMEOUT_UNIT = 1000   # 1000 chars → +25s
TIMEOUT_PER_UNIT = 25
TIMEOUT_BASE = 20


def get_dynamic_timeout(prompt_length: int) -> int:
    """
    Calculate timeout based on payload size.

    Scaling: ~20s base + ~25s per 1000 chars
    Floor: 60s minimum regardless of payload size.

    CPU-only hardware note: Ollama on OmniSlim mini tower
    runs qwen3:4b at 500%+ CPU. Larger prompts need more time.
    This function ensures we never cut Ollama off prematurely.

    Args:
        prompt_length: total character count of prompt + history

    Returns:
        timeout in seconds
    """
    units = int(prompt_length / CHARS_PER_TIMEOUT_UNIT)
    calculated = TIMEOUT_BASE + (units * TIMEOUT_PER_UNIT)
    return max(STANDARD_MIN_TIMEOUT, calculated)


def configure_generation_mode(mode: str, prompt_text: str, history_text: str) -> dict:
    """
    Set up environment variables and generation params based on mode.

    Args:
        mode:         "ablation" or "standard" (or any DRIFT chat mode)
        prompt_text:  assembled prompt string
        history_text: conversation history string

    Returns:
        config dict with timeout, max_tokens, temperature, top_p
    """
    total_length = len(prompt_text) + len(history_text)

    if mode == "ablation":
        timeout = ABLATION_TIMEOUT
        max_tokens = ABLATION_MAX_TOKENS
        temperature = ABLATION_TEMPERATURE
        top_p = ABLATION_TOP_P
    else:
        timeout = get_dynamic_timeout(total_length)
        max_tokens = STANDARD_MAX_TOKENS
        temperature = STANDARD_TEMPERATURE
        top_p = STANDARD_TOP_P

    # Set environment variable for local runner pickup
    os.environ["DRIFT_LOCAL_TIMEOUT"] = str(timeout)

    return {
        "timeout": timeout,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "mode": mode,
        "payload_length": total_length,
    }


# ── Retry Decorator ──────────────────────────────────────────────────────────

def retry_on_timeout(
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    timeout_exceptions: tuple = (TimeoutError, Exception),
):
    """
    Decorator that retries generation on timeout exceptions.
    Uses exponential backoff.

    Non-timeout errors (ValueError, ImportError, etc.) fail fast.
    This is intentional — retry only what retry can fix.

    Args:
        max_retries:        maximum number of retry attempts (default 3)
        backoff_factor:     multiplier for wait time between retries (default 1.5)
        timeout_exceptions: exception types to retry on

    Usage:
        @retry_on_timeout(max_retries=3, backoff_factor=1.5)
        def generate_response(prompt, config):
            return local_llm.generate(prompt, timeout=config['timeout'])
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            attempts_made = 0

            # Extract timeout from config if available
            config = kwargs.get('config')
            if config is None and args:
                config = args[0] if isinstance(args[0], dict) else None
            timeout = config.get('timeout', ABLATION_TIMEOUT) if isinstance(config, dict) else ABLATION_TIMEOUT

            for attempt in range(max_retries + 1):
                attempts_made = attempt + 1
                try:
                    print(
                        f"[RETRY] Attempt {attempts_made}/{max_retries + 1} "
                        f"| Timeout: {timeout}s"
                    )
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    print(
                        f"[SUCCESS] Generation completed in {duration:.1f}s "
                        f"on attempt {attempts_made}"
                    )
                    return result

                except TimeoutError as e:
                    last_exception = e
                    if attempt == max_retries:
                        print(f"[FAIL] All {max_retries + 1} attempts timed out.")
                        raise

                    wait_time = timeout * (backoff_factor ** attempt)
                    print(
                        f"[TIMEOUT] Attempt {attempts_made} timed out. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)

                except Exception as e:
                    # Non-timeout errors fail fast — no retry
                    print(f"[ERROR] Non-timeout error on attempt {attempts_made}: {e}")
                    raise

            raise last_exception

        return wrapper
    return decorator


# ── Generation Entry Point ────────────────────────────────────────────────────

@retry_on_timeout(max_retries=3, backoff_factor=1.5)
def generate_with_retry(
    prompt_text: str,
    history_text: str,
    mode: str = "standard",
    llm_generate_fn: Optional[Callable] = None,
) -> dict:
    """
    Main generation entry point with retry and dynamic timeout.

    Plug your actual local LLM or cloud API call via llm_generate_fn.
    If no function provided, returns a placeholder for testing.

    Args:
        prompt_text:      assembled prompt
        history_text:     conversation history
        mode:             "ablation" or "standard"
        llm_generate_fn:  your actual generation function

    Returns:
        dict with response, config, and timing metadata

    Integration example:
        from local_llm import generate as ollama_generate
        result = generate_with_retry(
            prompt_text=assembled_prompt,
            history_text=history,
            mode="standard",
            llm_generate_fn=ollama_generate,
        )
    """
    config = configure_generation_mode(mode, prompt_text, history_text)

    print(
        f"[GENERATE] Mode: {mode.upper()} | "
        f"Timeout: {config['timeout']}s | "
        f"Tokens: {config['max_tokens']} | "
        f"Temp: {config['temperature']} | "
        f"Payload: {config['payload_length']} chars"
    )

    start = time.time()

    if llm_generate_fn is not None:
        response = llm_generate_fn(
            prompt=prompt_text,
            history=history_text,
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            top_p=config["top_p"],
            timeout=config["timeout"],
        )
    else:
        # Placeholder — replace with your actual call
        time.sleep(0.01)  # Simulate minimal work
        response = "[PLACEHOLDER] Connect llm_generate_fn to activate."

    duration = time.time() - start

    return {
        "response": response,
        "config": config,
        "duration_sec": round(duration, 2),
        "mode": mode,
    }


# ── Self-Check ────────────────────────────────────────────────────────────────

def self_check():
    print("=" * 60)
    print("RETRY WRAPPER — SELF-CHECK")
    print("=" * 60)

    # Test 1: Dynamic timeout scaling
    print("\n[TEST 1] Dynamic timeout scaling")
    test_cases = [
        (500, 60),      # short prompt → floor of 60s
        (1000, 45),     # should be max(60, 20+25) = 60
        (4233, 120),    # 4k chars → 20 + (4*25) = 120s
        (10000, 270),   # 10k chars → 20 + (10*25) = 270s
    ]

    all_pass = True
    for length, expected in test_cases:
        result = get_dynamic_timeout(length)
        # Apply floor
        expected = max(60, expected)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {length:6d} chars → {result:3d}s (expected {expected:3d}s) {'[OK]' if ok else '[FAIL]'}")

    # Test 2: Ablation mode config
    print("\n[TEST 2] Ablation mode config")
    mock_prompt = "x" * 4233
    mock_history = "x" * 1500
    config = configure_generation_mode("ablation", mock_prompt, mock_history)

    ablation_ok = (
        config["timeout"] == ABLATION_TIMEOUT
        and config["max_tokens"] == ABLATION_MAX_TOKENS
        and config["temperature"] == ABLATION_TEMPERATURE
    )
    if not ablation_ok:
        all_pass = False
    print(f"  Timeout:     {config['timeout']}s (expected {ABLATION_TIMEOUT}s)")
    print(f"  Max tokens:  {config['max_tokens']} (expected {ABLATION_MAX_TOKENS})")
    print(f"  Temperature: {config['temperature']} (expected {ABLATION_TEMPERATURE})")
    print(f"  {'[OK]' if ablation_ok else '[FAIL]'}")

    # Test 3: Standard mode dynamic timeout
    print("\n[TEST 3] Standard mode dynamic timeout")
    config_std = configure_generation_mode("standard", mock_prompt, mock_history)
    expected_std_timeout = get_dynamic_timeout(len(mock_prompt) + len(mock_history))
    std_ok = config_std["timeout"] == expected_std_timeout
    if not std_ok:
        all_pass = False
    print(f"  Timeout: {config_std['timeout']}s (expected {expected_std_timeout}s) {'[OK]' if std_ok else '[FAIL]'}")

    # Test 4: Full pipeline without LLM
    print("\n[TEST 4] Full pipeline (no LLM)")
    try:
        result = generate_with_retry(mock_prompt, mock_history, mode="ablation")
        pipeline_ok = "response" in result and "config" in result
        if not pipeline_ok:
            all_pass = False
        print(f"  Response received: {pipeline_ok}")
        print(f"  Duration: {result['duration_sec']}s")
        print(f"  {'[OK]' if pipeline_ok else '[FAIL]'}")
    except Exception as e:
        all_pass = False
        print(f"  [FAIL] Pipeline error: {e}")

    print(f"\n{'[OK] All retry wrapper checks passed.' if all_pass else '[FAIL] Some checks failed.'}")
    return all_pass


if __name__ == "__main__":
    self_check()

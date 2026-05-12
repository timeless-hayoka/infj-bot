"""Rate limiter for API calls."""

import time
from functools import wraps


class TokenBucket:
    """Thread-safe-ish token bucket for rate limiting.

    Not fully thread-safe; use in single-threaded async contexts or guard
    with a lock if sharing across threads.
    """

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def acquire(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_and_acquire(self, tokens: int = 1):
        while not self.acquire(tokens):
            time.sleep(0.1)


def rate_limited(bucket: TokenBucket, tokens: int = 1):
    """Decorator that rate-limits a function using a TokenBucket."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            bucket.wait_and_acquire(tokens)
            return func(*args, **kwargs)

        return wrapper

    return decorator


# Pre-built limiters --------------------------------------------------

# Gemini: 60 requests per minute (free tier)
gemini_limiter = TokenBucket(capacity=60, refill_rate=1.0)

# Anthropic: 40 requests per minute (approximate free tier)
anthropic_limiter = TokenBucket(capacity=40, refill_rate=0.67)

# Ollama local: generous, but prevents CPU thrashing
ollama_limiter = TokenBucket(capacity=10, refill_rate=2.0)

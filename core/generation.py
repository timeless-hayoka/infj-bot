"""
generation.py — overhauled inference routing + rate governance for DRIFT (v2).

Drop-in replacement for the _generate / _generate_stream cluster in brain.py.

v2 changes (merge of two reviews + a bug found in v1):
  * FIXED single-flight: v1 deleted the shared result before waiters could read
    it, so coalescing silently did nothing. Now each in-flight call has a holder
    object that waiters keep a reference to; result is set BEFORE the event fires.
  * Per-provider cooldown after 429 (don't keep poking a provider that just said
    no). Cooldown length honors Retry-After, grows on repeated failures.
  * Failover-vs-block decision: short Retry-After -> retry same provider in-loop;
    long Retry-After -> cool it down and fail over now. No panic-switching, no
    long blocking.
  * Dead key (401/403) -> long cooldown instead of retrying every request forever.
  * HF adapter is a real function, not a generator-throw hack.

Still YOUR call (not solved here, by design):
  * Cache-key normalization (see _normalized_cache_key) — until volatile state is
    stripped, hit rate stays ~0 and the limiter does all the work.
  * TPM limiting — est_tokens is stubbed; wire a second bucket if you hit TPM.
  * Full health-based dynamic routing — cooldown gives most of the benefit;
    reordering by latency/health is a later step.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import requests

from drift.core.config import (
    API_KEY,
    DRIFT_USE_GROQ,
    GROQ_API_KEY,
    DRIFT_GROQ_MODEL,
    DRIFT_USE_KIMI,
    KIMI_API_KEY,
    DRIFT_KIMI_MODEL,
    KIMI_BASE_URL,
    DRIFT_USE_HF,
    DRIFT_USE_GEMINI,
    OPENAI_API_KEY,
    DRIFT_OPENAI_MODEL,
    DRIFT_OPENAI_BASE_URL,
    DRIFT_USE_OPENAI,
)

log = logging.getLogger("drift.generation")

# how long a "short" Retry-After is — at/below this we retry in-loop instead of
# failing over to the next provider
COOLDOWN_FAILOVER_THRESHOLD = 4.0
# dead-key / auth failures: stop hammering for this long
AUTH_COOLDOWN = 300.0


# --------------------------------------------------------------------------- #
# Errors — classify failures so we retry only what's worth retrying.
# --------------------------------------------------------------------------- #
class ProviderError(Exception):
    """Raised by a provider call. `kind` drives retry/cooldown policy."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "transient",        # "auth" | "client" | "rate_limit" | "transient"
        status: Optional[int] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        # 4xx client/auth errors are NOT retryable. Don't waste the budget.
        return self.kind in ("rate_limit", "transient")


class SystemOverload(Exception):
    """Raised when the global concurrency gate is saturated. This is an INTERNAL
    crowding condition, NOT a provider failure — so we do NOT fail over to a
    sibling provider (which shares the same gate and would also be crowded).
    On a single-user box this should essentially never fire."""


class RequestCancelled(Exception):
    """Raised when the client disconnects and queued work should stop."""


class RequestDeadlineExceeded(Exception):
    """Raised when the request budget is exhausted before work can complete."""


@dataclass
class RequestBudget:
    deadline: Optional[float] = None
    cancel_event: Optional[threading.Event] = None

    def cancelled(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())

    def remaining(self) -> Optional[float]:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

    def check(self) -> None:
        if self.cancelled():
            raise RequestCancelled("client disconnected")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise RequestDeadlineExceeded("request budget exhausted")



def _classify_http(resp: requests.Response) -> ProviderError:
    """Turn a failed HTTP response into a classified ProviderError."""
    status = resp.status_code
    retry_after = None
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            retry_after = float(ra)  # seconds form; date form is rare for LLM APIs
        except ValueError:
            retry_after = None
    body = (resp.text or "")[:300]
    body_lower = body.lower()
    if status == 429 and "insufficient_quota" in body_lower:
        kind = "quota"
    elif status == 429:
        kind = "rate_limit"
    elif status in (401, 403):
        kind = "auth"
    elif 400 <= status < 500:
        kind = "client"
    else:
        kind = "transient"
    return ProviderError(
        f"HTTP {status}: {body}", kind=kind, status=status, retry_after=retry_after
    )


# --------------------------------------------------------------------------- #
# Token bucket — the rate governor primitive. Thread-safe.
# --------------------------------------------------------------------------- #
class TokenBucket:
    """
    Classic token bucket. capacity = burst allowance, refill = tokens/sec.
    For an RPM limit: TokenBucket(capacity=RPM, refill_per_sec=RPM/60).
    Keep capacity a bit UNDER the provider's real RPM to leave headroom.
    """

    def __init__(self, capacity: float, refill_per_sec: float):
        self.capacity = float(capacity)
        self.refill = float(refill_per_sec)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _add_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill)

    def acquire(
        self,
        tokens: float = 1.0,
        timeout: float = 30.0,
        budget: Optional[RequestBudget] = None,
    ) -> bool:
        """Block (cooperatively) up to `timeout` for `tokens`. False on timeout."""
        if tokens > self.capacity:
            raise ValueError(f"Cannot acquire {tokens} tokens from bucket with capacity {self.capacity}")
            
        deadline = time.monotonic() + timeout
        while True:
            if budget is not None:
                budget.check()
            with self._lock:
                self._add_tokens()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                needed = tokens - self._tokens
                wait = needed / self.refill if self.refill > 0 else timeout
            if budget is not None:
                remaining = budget.remaining()
                if remaining is not None:
                    if remaining <= 0:
                        budget.check()
                    if wait > remaining:
                        raise RequestDeadlineExceeded(
                            "request budget exhausted while waiting for limiter"
                        )
                    wait = min(wait, remaining)
            if time.monotonic() + wait > deadline:
                return False
            time.sleep(min(wait, 0.25))  # small slices so we stay responsive


# --------------------------------------------------------------------------- #
# Per-provider runtime state: cooldown + consecutive failure tracking.
# --------------------------------------------------------------------------- #
@dataclass
class ProviderState:
    cooldown_until: float = 0.0          # monotonic clock
    consecutive_failures: int = 0

    def in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until


# --------------------------------------------------------------------------- #
# Metrics — so you can actually see the spike instead of guessing.
# --------------------------------------------------------------------------- #
class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.counters: dict[str, int] = {}

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + n

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self.counters)


# --------------------------------------------------------------------------- #
# Provider adapters — uniform interface, data-driven chain.
# --------------------------------------------------------------------------- #
@dataclass
class Provider:
    name: str
    enabled: Callable[[], bool]
    generate: Callable                  # (system, prompt, timeout, **kwargs) -> text
    stream: Optional[Callable] = None   # (system, prompt, timeout, **kwargs) -> Iterator[str]
    limiter: Optional[TokenBucket] = None
    est_tokens: Callable[[str, str], int] = field(
        default=lambda s, p: max(1, (len(s) + len(p)) // 4)
    )


# --------------------------------------------------------------------------- #
# Shared Session => connection pooling instead of a fresh TLS handshake each call
# --------------------------------------------------------------------------- #
_SESSION = requests.Session()
_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0),
)


def _openai_chat(*, base_url, api_key, model, system, prompt, stream, timeout, temperature=None, top_p=None, max_tokens=None):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    resp = _SESSION.post(
        f"{base_url}/chat/completions",
        headers=headers, json=payload, stream=stream, timeout=timeout,
    )
    if resp.status_code >= 400:
        raise _classify_http(resp)
    return resp


def openai_generate(*, base_url, api_key, model, system, prompt, timeout=30.0, temperature=None, top_p=None, max_tokens=None) -> str:
    resp = _openai_chat(
        base_url=base_url, api_key=api_key, model=model,
        system=system, prompt=prompt, stream=False, timeout=timeout,
        temperature=temperature, top_p=top_p, max_tokens=max_tokens
    )
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise ProviderError(f"Malformed response: {e}", kind="transient")


def openai_stream(*, base_url, api_key, model, system, prompt, timeout=60.0, temperature=None, top_p=None, max_tokens=None) -> Iterator[str]:
    resp = _openai_chat(
        base_url=base_url, api_key=api_key, model=model,
        system=system, prompt=prompt, stream=True, timeout=timeout,
        temperature=temperature, top_p=top_p, max_tokens=max_tokens
    )
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8").removeprefix("data: ")
        if line_str.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(line_str)["choices"][0]["delta"].get("content", "")
        except (KeyError, IndexError, ValueError):
            continue
        if chunk:
            yield chunk


# --------------------------------------------------------------------------- #
# In-flight holder — the fix for v1's broken single-flight.
# Waiters keep a reference to this, so the leader cleaning up the dict can't
# race away the result.
# --------------------------------------------------------------------------- #
@dataclass
class _InflightCall:
    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[str] = None
    error: Optional[BaseException] = None


# --------------------------------------------------------------------------- #
# The governor: cooldown, retry policy, Retry-After, single-flight, caching.
# --------------------------------------------------------------------------- #
class RateGovernor:
    def __init__(
        self,
        providers: list[Provider],
        *,
        cache_get: Callable[[str], Optional[str]],
        cache_set: Callable[[str, str], None],
        max_retries: int = 3,
        backoff_base: float = 1.5,
        backoff_cap: float = 30.0,
        max_concurrency: int = 4,        # global cap on simultaneous outbound calls
        gate_timeout: float = 5.0,
        metrics: Optional[Metrics] = None,
    ):
        self.providers = providers
        self.cache_get = cache_get
        self.cache_set = cache_set
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.metrics = metrics or Metrics()

        # Global concurrency gate: per-provider buckets pace EACH api; this bounds
        # TOTAL simultaneous outbound calls so internal fan-out (orchestrator
        # phases / plugins / Hive nodes firing distinct prompts at once) can't all
        # launch together. Held ONLY around the network call, never during sleeps.
        self._gate = threading.BoundedSemaphore(max_concurrency)
        self._max_concurrency = max_concurrency
        self.gate_timeout = gate_timeout

        self._inflight: dict[str, _InflightCall] = {}
        self._inflight_lock = threading.Lock()

        self._pstate: dict[str, ProviderState] = {p.name: ProviderState() for p in providers}
        self._pstate_lock = threading.Lock()
        self._cloud_quota_exhausted = False

    # ---- cooldown / health bookkeeping ----------------------------------- #
    def _mark_success(self, name: str) -> None:
        with self._pstate_lock:
            st = self._pstate[name]
            st.consecutive_failures = 0
            st.cooldown_until = 0.0

    def _set_cooldown(self, name: str, seconds: float) -> None:
        with self._pstate_lock:
            st = self._pstate[name]
            st.cooldown_until = time.monotonic() + seconds
            st.consecutive_failures += 1
        self.metrics.inc(f"{name}.cooldown")
        log.warning("%s cooled down for %.1fs", name, seconds)

    def _default_cooldown(self, name: str) -> float:
        with self._pstate_lock:
            fails = self._pstate[name].consecutive_failures
        # Reduced from 5.0 to 2.0 for faster recovery in "good work" environments
        return min(self.backoff_cap, 2.0 * (2 ** fails))

    def _in_cooldown(self, name: str) -> bool:
        with self._pstate_lock:
            return self._pstate[name].in_cooldown()

    def provider_health(self) -> dict[str, dict]:
        """Expose state for logging/UI. Honest, observable, no magic."""
        now = time.monotonic()
        with self._pstate_lock:
            return {
                name: {
                    "in_cooldown": st.in_cooldown(),
                    "cooldown_remaining": max(0.0, st.cooldown_until - now),
                    "consecutive_failures": st.consecutive_failures,
                }
                for name, st in self._pstate.items()
            }

    def metrics_report(self) -> dict:
        """Clean, endpoint-ready readout computed from the REAL metric keys
        (cache.hit / cache.miss / coalesced), not the cache_hits/cache_misses
        names some drafts assumed. Safe to serve directly from a debug route."""
        snap = self.metrics.snapshot()
        hits = snap.get("cache.hit", 0) + snap.get("cache.hit_stream", 0)
        misses = snap.get("cache.miss", 0)
        total = hits + misses
        return {
            "cache": {
                "hits": hits,
                "misses": misses,
                "hit_rate_percent": round(100.0 * hits / total, 2) if total else 0.0,
            },
            "coalesced_calls_saved": snap.get("coalesced", 0),
            "max_concurrency": self._max_concurrency,
            "providers": self.provider_health(),
            "raw": snap,
        }

    # ---- backoff with jitter; honors server-provided Retry-After --------- #
    def _sleep_for(self, attempt: int, err: ProviderError, budget: Optional[RequestBudget] = None) -> None:
        if err.retry_after is not None:
            delay = err.retry_after
        else:
            delay = min(self.backoff_cap, self.backoff_base ** attempt)
        delay += random.uniform(0, delay * 0.25)  # jitter — no synchronized storms
        log.warning("backoff %.2fs (provider=%s kind=%s)", delay, err.status, err.kind)
        end = time.monotonic() + delay
        while True:
            if budget is not None:
                budget.check()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.25))

    # ---- one provider, with cooldown + rate-limit + retry ---------------- #
    def _acquire_gate(self, name: str, budget: Optional[RequestBudget] = None) -> None:
        """Acquire the global concurrency permit, waiting in slices. Gate
        saturation means the SYSTEM is crowded (internal), not that this provider
        failed — so we wait instead of failing over. If it can't be acquired
        within gate_timeout, that's pathological; surface it rather than silently
        misrouting load onto a sibling that shares this same gate."""
        waited = 0.0
        while waited < self.gate_timeout:
            if budget is not None:
                budget.check()
            slice_wait = min(0.25, self.gate_timeout - waited)
            if budget is not None:
                remaining = budget.remaining()
                if remaining is not None:
                    if remaining <= 0:
                        budget.check()
                    if remaining < slice_wait:
                        raise RequestDeadlineExceeded(
                            f"request budget exhausted while waiting for {name} gate"
                        )
                    slice_wait = min(slice_wait, remaining)
            if self._gate.acquire(timeout=slice_wait):
                return
            waited += slice_wait
            self.metrics.inc(f"{name}.gate_wait")
            log.warning("%s waiting on global concurrency gate (~%.0fs)", name, waited)
        self.metrics.inc(f"{name}.gate_timeout")
        raise SystemOverload(
            f"Concurrency gate saturated after {self.gate_timeout:.0f}s "
            f"(>= {self._max_concurrency} concurrent calls). Reduce fan-out "
            f"or raise max_concurrency — this is not a provider failure."
        )

    def _call_provider(self, p: Provider, system: str, prompt: str, errors: list | None = None, budget: Optional[RequestBudget] = None, **kwargs) -> Optional[str]:
        if not p.enabled():
            if errors is not None:
                errors.append(f"{p.name}: disabled")
            return None
        if self._in_cooldown(p.name):
            self.metrics.inc(f"{p.name}.skipped_cooldown")
            if errors is not None:
                errors.append(f"{p.name}: benched (cooldown)")
            return None

        for attempt in range(self.max_retries):
            if budget is not None:
                budget.check()
            if p.limiter and not p.limiter.acquire(tokens=1, timeout=self.backoff_cap, budget=budget):
                self.metrics.inc(f"{p.name}.limiter_timeout")
                if errors is not None:
                    errors.append(f"{p.name}: limiter timeout")
                return None
            try:
                self.metrics.inc(f"{p.name}.attempt")
                # gate held ONLY around the network call, released before any
                # backoff sleep so a waiting permit never blocks on a sleeper.
                # Gate saturation is internal crowding, not a provider fault, so
                # we wait rather than dumping load onto a sibling (#3 fix).
                self._acquire_gate(p.name, budget=budget)
                try:
                    call_timeout = budget.remaining() if budget is not None else None
                    out = p.generate(system, prompt, call_timeout, **kwargs)
                    if budget is not None:
                        budget.check()
                finally:
                    self._gate.release()
                self.metrics.inc(f"{p.name}.success")
                self._mark_success(p.name)
                return out

            except (RequestCancelled, RequestDeadlineExceeded):
                raise
            except SystemOverload:
                # internal crowding — never failover, never mark provider bad
                raise
            except ProviderError as e:
                self.metrics.inc(f"{p.name}.err.{e.kind}")
                log.warning("%s ProviderError: %s (kind=%s, attempt=%d)", p.name, e, e.kind, attempt)
                if errors is not None:
                    errors.append(f"{p.name}: {e} (kind={e.kind})")

                if e.kind == "auth":
                    # dead/invalid key — don't retry it every request
                    self._set_cooldown(p.name, AUTH_COOLDOWN)
                    log.error("%s auth failure, benched %.0fs: %s", p.name, AUTH_COOLDOWN, e)
                    return None

                if e.kind == "quota":
                    # Billing exhausted — retrying and loading local GLEN wastes minutes.
                    self._cloud_quota_exhausted = True
                    self._set_cooldown(p.name, AUTH_COOLDOWN)
                    log.error(
                        "%s quota exhausted (add API billing at platform.openai.com): %s",
                        p.name,
                        e,
                    )
                    return None

                if e.kind == "client":
                    # malformed request — retrying won't help, and other providers
                    # will likely choke on the same payload, but let the chain decide
                    log.error("%s client error (non-retryable): %s", p.name, e)
                    return None

                if e.kind == "rate_limit":
                    wait = e.retry_after if e.retry_after is not None else self._default_cooldown(p.name)
                    if wait <= COOLDOWN_FAILOVER_THRESHOLD and attempt < self.max_retries - 1:
                        self._sleep_for(attempt, e, budget=budget)  # short wait -> retry in place
                        continue
                    self._set_cooldown(p.name, wait)  # long wait -> bench + fail over
                    return None

                # transient (5xx)
                if attempt == self.max_retries - 1:
                    self._set_cooldown(p.name, self._default_cooldown(p.name))
                    return None
                self._sleep_for(attempt, e, budget=budget)

            except Exception as e:  # network blip, timeout, etc.
                self.metrics.inc(f"{p.name}.err.unknown")
                log.warning("%s Exception: %s (attempt=%d)", p.name, e, attempt)
                if errors is not None:
                    errors.append(f"{p.name}: {e}")
                if attempt == self.max_retries - 1:
                    self._set_cooldown(p.name, self._default_cooldown(p.name))
                    log.error("%s failed: %s", p.name, e)
                    return None
                self._sleep_for(attempt, ProviderError(str(e)), budget=budget)
        return None

    # ---- the actual fallback chain (no coalescing concern here) ----------- #
    def _run_chain(self, key: str, system: str, prompt: str, budget: Optional[RequestBudget] = None, **kwargs) -> str:
        errors = []
        for p in self.providers:
            if self._cloud_quota_exhausted and p.name == "local":
                errors.append(
                    "local: skipped (OpenAI API quota exhausted — ChatGPT Pro does not "
                    "include API billing; add a payment method at platform.openai.com)"
                )
                continue
            out = self._call_provider(p, system, prompt, errors=errors, budget=budget, **kwargs)
            if out:
                self.cache_set(key, out)   # ONE cache path, every provider
                return out
        if self._cloud_quota_exhausted:
            raise RuntimeError(
                "OpenAI API quota exhausted. ChatGPT Pro / Codex login is separate from "
                "the Developer API — add billing and credits at "
                "https://platform.openai.com/settings/organization/billing then retry. "
                "Detail: " + " | ".join(errors)
            )
        err_msg = (
            "All providers failed, cooled down, or unavailable. Detail: "
            + " | ".join(errors)
        )
        raise RuntimeError(err_msg)

    # ---- public: cached + single-flighted ---------------------------------#
    def generate(self, key: str, system: str, prompt: str, budget: Optional[RequestBudget] = None, **kwargs) -> str:
        cached = self.cache_get(key)
        if cached is not None:
            self.metrics.inc("cache.hit")
            return cached
        self.metrics.inc("cache.miss")

        if budget is not None:
            budget.check()

        with self._inflight_lock:
            call = self._inflight.get(key)
            leader = call is None
            if leader:
                call = _InflightCall()
                self._inflight[key] = call

        if not leader:
            # someone else is already computing this exact request — wait for them
            self.metrics.inc("coalesced")
            wait_timeout = self.gate_timeout
            if budget is not None:
                remaining = budget.remaining()
                if remaining is not None:
                    if remaining <= 0:
                        budget.check()
                    wait_timeout = remaining
            if call.event.wait(timeout=wait_timeout):
                if call.error is not None:
                    raise call.error
                if call.result is not None:
                    if budget is not None:
                        budget.check()
                    return call.result
                raise RuntimeError("single-flight completed without a result")
            self.metrics.inc("coalesced_timeout")
            if budget is not None:
                budget.check()
            raise RequestDeadlineExceeded(
                f"coalesced request exceeded wait timeout after {wait_timeout:.1f}s"
            )

        # leader path
        try:
            out = self._run_chain(key, system, prompt, budget=budget, **kwargs)
            call.result = out          # set result BEFORE releasing waiters
            return out
        except BaseException as e:
            call.error = e
            raise
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)
            call.event.set()           # waiters wake AFTER result/error is set

    # ---- public: streaming with cache replay + cache fill + cooldown -------#
    def generate_stream(self, key: str, system: str, prompt: str, budget: Optional[RequestBudget] = None, **kwargs) -> Iterator[str]:
        cached = self.cache_get(key)
        if cached is not None:
            self.metrics.inc("cache.hit_stream")
            for i in range(0, len(cached), 16):
                yield cached[i:i + 16]
            return

        if budget is not None:
            budget.check()

        for p in self.providers:
            if not p.enabled() or p.stream is None or self._in_cooldown(p.name):
                continue
            if budget is not None:
                budget.check()
            if p.limiter and not p.limiter.acquire(timeout=self.backoff_cap, budget=budget):
                continue
            try:
                self.metrics.inc(f"{p.name}.stream_attempt")
                buf: list[str] = []
                call_timeout = budget.remaining() if budget is not None else None
                for chunk in p.stream(system, prompt, call_timeout, **kwargs):
                    if budget is not None:
                        budget.check()
                    buf.append(chunk)
                    yield chunk
                if budget is not None:
                    budget.check()
                full = "".join(buf)
                if full:
                    self.cache_set(key, full)   # streaming now fills the cache too
                    self.metrics.inc(f"{p.name}.stream_success")
                    self._mark_success(p.name)
                return
            except (RequestCancelled, RequestDeadlineExceeded):
                raise
            except SystemOverload:
                raise
            except ProviderError as e:
                self.metrics.inc(f"{p.name}.stream_err.{e.kind}")
                if e.kind == "rate_limit":
                    wait = e.retry_after if e.retry_after is not None else self._default_cooldown(p.name)
                    self._set_cooldown(p.name, wait)
                elif e.kind == "auth":
                    self._set_cooldown(p.name, AUTH_COOLDOWN)
                continue
            except Exception as e:
                self.metrics.inc(f"{p.name}.stream_err.unknown")
                log.warning("%s stream failed: %s", p.name, e)
                continue
        # last resort: non-streaming (single-flighted), replayed as chunks
        text = self.generate(key, system, prompt, budget=budget)
        for i in range(0, len(text), 16):
            yield text[i:i + 16]


# Cache-key normalization — the #1 lever. This is what makes the cache actually
# hit. Two approaches, robust first.
# --------------------------------------------------------------------------- #
#
# ROBUST (preferred): key on the STABLE INPUTS, before prompt_builder injects
# state. If you can reach the pre-injection pieces (system instruction skeleton,
# the user's actual message, mode, retrieved-doc ids), hash those directly:
#
#     make_cache_key(model, mode, system_skeleton, user_message, doc_ids)
#
# That's deterministic and can't be fooled by formatting drift. Use it if you
# can thread those values down to _generate.
#
# STOPGAP: if you can only get the finished prompt string, strip the volatile
# bits out before hashing. Fragile (depends on exact formatting) — verify it
# against a real built prompt: print one, see what changes turn-to-turn, and
# make sure these patterns catch exactly those and nothing meaningful.

# TUNE these against your actual prompt_builder.py output.
_VOLATILE_PATTERNS = [
    # ISO timestamps / clock times
    re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?"),
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
    # being.py CognitiveState / AgencyState scalar lines
    re.compile(
        r"(?im)^\s*(mood|energy|intensity|curiosity|attachment|focus|volition|"
        r"self_awareness|architecture_awareness|autonomy_drive|purpose_alignment|"
        r"shadow_depth|last_thought|last_choice)\s*[:=].*$"
    ),
    # counters that change every turn
    re.compile(
        r"(?im)^\s*(total_interactions|insights_formed|dreams_had|"
        r"last_interaction)\s*[:=].*$"
    ),
    # homeostasis.py need levels (e.g. "coherence: 0.58")
    re.compile(
        r"(?im)^\s*(energy|coherence|integration|connection|growth|autonomy|"
        r"integrity)\s*[:=]\s*[0-9.]+.*$"
    ),
]
# AGGRESSIVE and OPTIONAL: nuke every bare float. Catches stray drift values the
# line patterns miss, but WILL clobber meaningful numbers in the user's actual
# question. Leave off unless you confirm prompts carry no significant decimals.
_STRIP_ALL_FLOATS = re.compile(r"\b\d+\.\d+\b")


def strip_volatile_state(text: str, *, strip_floats: bool = False) -> str:
    """Redact turn-to-turn state so semantically identical prompts collide."""
    out = text
    for pat in _VOLATILE_PATTERNS:
        out = pat.sub("<v>", out)
    if strip_floats:
        out = _STRIP_ALL_FLOATS.sub("<n>", out)
    return re.sub(r"\s+", " ", out).strip()


def make_cache_key(*parts: object) -> str:
    """Robust key from explicit stable parts. Pass pre-injection values."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def strip_state_sections(text: str, sections: list[tuple[str, str]]) -> str:
    """
    SAFEST normalizer (preferred over strip_volatile_state).

    Instead of pattern-matching things that *look* dynamic across the whole
    prompt (which can clobber meaningful numbers in the user's actual question,
    e.g. "compare 2023 vs 2024 revenue"), this removes ONLY the content between
    known state-block markers and preserves everything else byte-for-byte.

    sections: list of (start_marker, end_marker), e.g. [("[STATE]", "[/STATE]")].
    Whatever your prompt_builder.py wraps live state in — wire those markers here
    and you get exact normalization with zero risk to the question text.
    """
    out = text
    for start, end in sections:
        pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        out = pat.sub(f"{start}<state>{end}", out)
    return out


# --------------------------------------------------------------------------- #
# === Wire-in: methods to replace the ones in brain.py ====================== #
# --------------------------------------------------------------------------- #
class _BrainGenerationMixin:
    """Mix into InfjBrain. Assumes existing attrs: local_bridge, hf_bridge,
    sdk, primary_model, critic_model, critic_model_name, _disk_cache,
    _gen_cache (OrderedDict), _gen_cache_size, _use_local_fallback,
    plus the module-level config flags from your current brain.py."""

    def _build_governor(self) -> RateGovernor:
        def cache_get(key: str) -> Optional[str]:
            import os
            if os.getenv("DRIFT_BYPASS_CACHE") == "1":
                return None
            if self._disk_cache is not None:
                try:
                    v = self._disk_cache.get(key)
                    if v is not None:
                        return v
                except Exception:
                    log.debug("disk cache get failed", exc_info=True)
            v = self._gen_cache.get(key)
            if v is not None:
                self._gen_cache.move_to_end(key)
            return v

        def cache_set(key: str, val: str) -> None:
            self._gen_cache[key] = val
            self._gen_cache.move_to_end(key)
            while len(self._gen_cache) > self._gen_cache_size:
                self._gen_cache.popitem(last=False)
            if self._disk_cache is not None:
                try:
                    self._disk_cache.set(key, val)
                except Exception:
                    log.debug("disk cache set failed", exc_info=True)

        local_provider = Provider(
            name="local",
            enabled=lambda: bool(
                self._use_local_fallback and self.local_bridge.is_available()),
            generate=lambda s, p, timeout=None, **kwargs: self.local_bridge.generate(prompt=p, system=s, **kwargs),
            stream=lambda s, p, timeout=None, **kwargs: self.local_bridge.generate_stream(prompt=p, system=s, **kwargs),
            limiter=None,  # local CPU — your hardware is the limit, not an API
        )

        providers: list[Provider] = []
        if getattr(self, "_prefer_local", False):
            providers.append(local_provider)

        providers.extend([
            Provider(
                name="openai",
                enabled=lambda: bool(DRIFT_USE_OPENAI and OPENAI_API_KEY),
                generate=lambda s, p, timeout=None, **kwargs: openai_generate(
                    base_url=DRIFT_OPENAI_BASE_URL,
                    api_key=OPENAI_API_KEY,
                    model=getattr(self, "_active_model_name", None) or DRIFT_OPENAI_MODEL,
                    system=s,
                    prompt=p,
                    timeout=timeout if timeout is not None else 60.0,
                    **kwargs,
                ),
                stream=lambda s, p, timeout=None, **kwargs: openai_stream(
                    base_url=DRIFT_OPENAI_BASE_URL,
                    api_key=OPENAI_API_KEY,
                    model=getattr(self, "_active_model_name", None) or DRIFT_OPENAI_MODEL,
                    system=s,
                    prompt=p,
                    timeout=timeout if timeout is not None else 90.0,
                    **kwargs,
                ),
                limiter=TokenBucket(capacity=40, refill_per_sec=40 / 60),
            ),
            Provider(
                name="groq",
                enabled=lambda: bool(DRIFT_USE_GROQ and GROQ_API_KEY),
                generate=lambda s, p, timeout=None, **kwargs: openai_generate(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY, model=DRIFT_GROQ_MODEL, system=s, prompt=p,
                    timeout=timeout if timeout is not None else 30.0, **kwargs),
                stream=lambda s, p, timeout=None, **kwargs: openai_stream(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=GROQ_API_KEY, model=DRIFT_GROQ_MODEL, system=s, prompt=p,
                    timeout=timeout if timeout is not None else 60.0, **kwargs),
                limiter=TokenBucket(capacity=25, refill_per_sec=25 / 60),
            ),
            Provider(
                name="kimi",
                enabled=lambda: bool(DRIFT_USE_KIMI and KIMI_API_KEY),
                generate=lambda s, p, timeout=None, **kwargs: openai_generate(
                    base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY,
                    model=DRIFT_KIMI_MODEL, system=s, prompt=p,
                    timeout=timeout if timeout is not None else 60.0, **kwargs),
                stream=lambda s, p, timeout=None, **kwargs: openai_stream(
                    base_url=KIMI_BASE_URL, api_key=KIMI_API_KEY,
                    model=DRIFT_KIMI_MODEL, system=s, prompt=p,
                    timeout=timeout if timeout is not None else 60.0, **kwargs),
                limiter=TokenBucket(capacity=15, refill_per_sec=15 / 60),
            ),
            Provider(
                name="hf",
                enabled=lambda: bool(DRIFT_USE_HF and self.hf_bridge.is_available()),
                generate=lambda s, p, timeout=None, **kwargs: self._hf_generate(s, p, **kwargs),
                limiter=TokenBucket(capacity=10, refill_per_sec=10 / 60),
            ),
            Provider(
                name="gemini",
                enabled=lambda: bool(DRIFT_USE_GEMINI and API_KEY),
                generate=lambda s, p, timeout=None, **kwargs: self._gemini_generate(s, p, **kwargs),
                stream=lambda s, p, timeout=None, **kwargs: self._gemini_stream(s, p, **kwargs),
                limiter=TokenBucket(capacity=12, refill_per_sec=12 / 60),
            ),
        ])

        if not getattr(self, "_prefer_local", False):
            providers.append(local_provider)

        return RateGovernor(providers, cache_get=cache_get, cache_set=cache_set)

    # ---- boot wiring: call init_governor() ONCE in InfjBrain.__init__ ------#
    def init_governor(self) -> None:
        """Build the governor eagerly and validate config at startup, so a dead
        key or missing provider crashes boot loudly instead of surfacing on the
        first user turn — and so the metrics endpoint works before any request."""
        self._validate_provider_config()
        self._governor = self._build_governor()

    def _validate_provider_config(self) -> None:
        """Fail fast on misconfig. Runs ONCE at boot (NOT per request — base_url
        and keys are static, so per-call validation would just burn cycles and
        still can't catch a revoked-but-present key)."""
        problems: list[str] = []
        if DRIFT_USE_GROQ and not GROQ_API_KEY:
            problems.append("DRIFT_USE_GROQ set but GROQ_API_KEY missing")
        if DRIFT_USE_OPENAI and not OPENAI_API_KEY:
            problems.append("DRIFT_USE_OPENAI set but OPENAI_API_KEY missing")
        if DRIFT_USE_KIMI and not KIMI_API_KEY:
            problems.append("DRIFT_USE_KIMI set but KIMI_API_KEY missing")
        if (DRIFT_USE_KIMI and KIMI_API_KEY
                and not str(KIMI_BASE_URL or "").startswith("http")):
            problems.append(f"KIMI_BASE_URL invalid (need http[s]://...): {KIMI_BASE_URL!r}")
        usable = (
            (DRIFT_USE_OPENAI and OPENAI_API_KEY)
            or (DRIFT_USE_GROQ and GROQ_API_KEY)
            or (DRIFT_USE_KIMI and KIMI_API_KEY)
            or (DRIFT_USE_HF and self.hf_bridge.is_available())
            or (DRIFT_USE_GEMINI and API_KEY)
            or (self._use_local_fallback and self.local_bridge.is_available())
        )
        if not usable:
            problems.append(
                "no usable provider — set an API key or enable local fallback")
        if problems:
            if not usable:
                raise RuntimeError(
                    "DRIFT provider config invalid:\n  - " + "\n  - ".join(problems))
            log.warning(
                "DRIFT provider config has optional gaps but a usable backend is available:\n  - %s",
                "\n  - ".join(problems),
            )

    # ---- provider adapters that need self ---------------------------------#
    def _hf_generate(self, system: str, prompt: str, timeout: Optional[float] = None, history=None, **kwargs) -> str:
        out = self.hf_bridge.generate(system, prompt, history=history, **kwargs)
        if not out:
            raise ProviderError("HF returned empty", kind="transient")
        return out

    def _gemini_generate(self, system: str, prompt: str, timeout: Optional[float] = None, **kwargs) -> str:
        try:
            if self.sdk == "google.genai":
                model_name = getattr(self, "_active_model_name", self.primary_model_name)
                return self._generate_new_sdk(model_name, system, prompt, **kwargs)
            
            import google.generativeai as legacy_genai
            model_name = getattr(self, "_active_model_name", self.primary_model_name)
            
            gen_config = {}
            if "temperature" in kwargs and kwargs["temperature"] is not None:
                gen_config["temperature"] = kwargs["temperature"]
            if "top_p" in kwargs and kwargs["top_p"] is not None:
                gen_config["top_p"] = kwargs["top_p"]
            
            max_tokens_val = kwargs.get("max_tokens") or kwargs.get("max_output_tokens")
            if max_tokens_val is not None:
                gen_config["max_output_tokens"] = max_tokens_val
                
            model = legacy_genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
                generation_config=gen_config if gen_config else None
            )
            
            request_options = {}
            if timeout is not None:
                request_options["timeout"] = timeout
                
            return model.generate_content(prompt, request_options=request_options).text
        except Exception as exc:
            if self._is_transient_model_error(exc):
                raise ProviderError(str(exc), kind="transient")
            raise ProviderError(str(exc), kind="client")

    def _gemini_stream(self, system: str, prompt: str, timeout: Optional[float] = None, **kwargs) -> Iterator[str]:
        try:
            if self.sdk == "google.genai":
                model_name = getattr(self, "_active_model_name", self.primary_model_name)
                yield from self._generate_new_sdk_stream(model_name, system, prompt, **kwargs)
                return
            
            import google.generativeai as legacy_genai
            model_name = getattr(self, "_active_model_name", self.primary_model_name)
            
            gen_config = {}
            if "temperature" in kwargs and kwargs["temperature"] is not None:
                gen_config["temperature"] = kwargs["temperature"]
            if "top_p" in kwargs and kwargs["top_p"] is not None:
                gen_config["top_p"] = kwargs["top_p"]
            
            max_tokens_val = kwargs.get("max_tokens") or kwargs.get("max_output_tokens")
            if max_tokens_val is not None:
                gen_config["max_output_tokens"] = max_tokens_val
                
            model = legacy_genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
                generation_config=gen_config if gen_config else None
            )
            
            request_options = {}
            if timeout is not None:
                request_options["timeout"] = timeout
                
            for chunk in model.generate_content(prompt, stream=True, request_options=request_options):
                text = chunk.text or ""
                if text:
                    yield text
        except Exception as exc:
            if self._is_transient_model_error(exc):
                raise ProviderError(str(exc), kind="transient")
            raise ProviderError(str(exc), kind="client")

    # ---- cache key: the #1 lever — now actually normalizing ---------------#
    # Set this to your prompt_builder's state-block markers for the SAFEST path,
    # e.g. _state_sections = [("[STATE]", "[/STATE]"), ("[META]", "[/META]")].
    # When set, only those blocks are stripped; the user's question is untouched.
    # When None, falls back to the broader regex stripper (riskier — verify it).
    _state_sections: Optional[list[tuple[str, str]]] = None

    def _normalized_cache_key(self, model_name, system_instruction, prompt) -> str:
        """
        Old key hashed the RAW prompt, which carried injected live state, so it
        never matched. Normalize before hashing.

        PREFERRED (most robust): if you can reach the pre-injection inputs,
        override this to:
            return make_cache_key(model_name, mode, system_skeleton,
                                  user_message, tuple(doc_ids))

        NEXT BEST (#2 fix): set self._state_sections to your prompt_builder's
        state-block markers — strips ONLY those blocks, never the question text.

        FALLBACK: strip_volatile_state regex. Broad; can over-strip. Verify
        against a real prompt and keep strip_floats=False unless you've confirmed
        questions carry no significant decimals.
        """
        if self._state_sections:
            stable_prompt = strip_state_sections(prompt, self._state_sections)
            stable_system = strip_state_sections(system_instruction, self._state_sections)
        else:
            stable_prompt = strip_volatile_state(prompt, strip_floats=False)
            stable_system = strip_volatile_state(system_instruction, strip_floats=False)
        return make_cache_key(model_name, stable_system, stable_prompt)

    # ---- entrypoints replacing your _generate / _generate_stream ----------#
    def _generate(self, model_name, system_instruction, prompt, **kwargs):
        if not hasattr(self, "_governor"):
            self._governor = self._build_governor()
        self._active_model_name = model_name
        key = self._normalized_cache_key(model_name, system_instruction, prompt)
        request_budget = None
        request_budget_local = getattr(self, "_request_budget_local", None)
        if request_budget_local is not None:
            request_budget = getattr(request_budget_local, "budget", None)
        
        # Pull dynamic generation parameters from context variable if not explicitly passed
        from drift.core.causal_wiring import generation_params_var
        gp = generation_params_var.get()
        if gp:
            if "temperature" not in kwargs and gp.get("temperature") is not None:
                kwargs["temperature"] = gp["temperature"]
            if "top_p" not in kwargs and gp.get("top_p") is not None:
                kwargs["top_p"] = gp["top_p"]

        return self._governor.generate(key, system_instruction, prompt, budget=request_budget, **kwargs)

    def _generate_stream(self, model_name, system_instruction, prompt, **kwargs):
        if not hasattr(self, "_governor"):
            self._governor = self._build_governor()
        self._active_model_name = model_name
        key = self._normalized_cache_key(model_name, system_instruction, prompt)
        request_budget = None
        request_budget_local = getattr(self, "_request_budget_local", None)
        if request_budget_local is not None:
            request_budget = getattr(request_budget_local, "budget", None)

        # Pull dynamic generation parameters from context variable if not explicitly passed
        from drift.core.causal_wiring import generation_params_var
        gp = generation_params_var.get()
        if gp:
            if "temperature" not in kwargs and gp.get("temperature") is not None:
                kwargs["temperature"] = gp["temperature"]
            if "top_p" not in kwargs and gp.get("top_p") is not None:
                kwargs["top_p"] = gp["top_p"]

        yield from self._governor.generate_stream(key, system_instruction, prompt, budget=request_budget, **kwargs)

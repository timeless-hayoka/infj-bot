"""resilience.py — Circuit breakers, health monitoring, and fault tolerance.

Ensures the consciousness loop survives module failures, memory leaks,
and cascading errors. A failing module should not take down the mind.
"""

import asyncio
import logging
import sqlite3
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("drift")


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Prevents cascading failures by cutting off failing modules."""
    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 30.0  # seconds
    half_open_max_calls: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failures: int = field(default=0, repr=False)
    _last_failure_time: Optional[float] = field(default=None, repr=False)
    _successes_during_half_open: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._last_failure_time and (time.time() - self._last_failure_time) >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._successes_during_half_open = 0
                    logger.info("Circuit breaker '%s' entering HALF_OPEN", self.name)
                    return True
                return False
            if self._state == CircuitState.HALF_OPEN:
                return self._successes_during_half_open < self.half_open_max_calls
            return False

    def record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._successes_during_half_open += 1
                if self._successes_during_half_open >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    logger.info("Circuit breaker '%s' CLOSED (recovered)", self.name)
            elif self._state == CircuitState.CLOSED:
                self._failures = max(0, self._failures - 1)

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker '%s' OPEN (recovery failed)", self.name)
            elif self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker '%s' OPEN after %d failures", self.name, self._failures)

    @property
    def state(self) -> str:
        return self._state.value


@dataclass
class HealthCheck:
    """Result of a health check."""
    name: str
    healthy: bool
    latency_ms: float
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


from infj_bot.core.config import DATA_DIR

HEALTH_DB = DATA_DIR / "health.db"


class HealthMonitor:
    """Monitors the health of cognitive modules and subsystems."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or HEALTH_DB
        self._checks: Dict[str, Callable[[], HealthCheck]] = {}
        self._history: List[HealthCheck] = []
        self._max_history = 500
        self._init_db()

    def _init_db(self):
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    name TEXT,
                    healthy INTEGER,
                    latency_ms REAL,
                    message TEXT
                )
            """)
            conn.commit()

    def register(self, name: str, checker: Callable[[], HealthCheck]):
        """Register a health check function."""
        self._checks[name] = checker

    def check(self, name: Optional[str] = None) -> List[HealthCheck]:
        """Run health checks. If name given, check only that module."""
        results = []
        names = [name] if name else list(self._checks.keys())
        for n in names:
            checker = self._checks.get(n)
            if not checker:
                continue
            start = time.time()
            try:
                result = checker()
            except Exception as exc:
                result = HealthCheck(
                    name=n,
                    healthy=False,
                    latency_ms=(time.time() - start) * 1000,
                    message=f"Health check crashed: {exc}",
                )
            results.append(result)
            self._history.append(result)
            # Persist
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO health_checks (timestamp, name, healthy, latency_ms, message)
                    VALUES (?, ?, ?, ?, ?)
                """, (result.timestamp, result.name, int(result.healthy),
                      result.latency_ms, result.message))
                conn.commit()
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        return results

    def is_healthy(self) -> bool:
        """Quick check: are all registered systems healthy?"""
        results = self.check()
        return all(r.healthy for r in results)

    def get_history(self, name: Optional[str] = None, limit: int = 20) -> List[HealthCheck]:
        events = self._history
        if name:
            events = [e for e in events if e.name == name]
        return events[-limit:]

    def report(self) -> str:
        """Human-readable health report."""
        results = self.check()
        lines = ["=== HEALTH REPORT ==="]
        for r in results:
            status = "OK" if r.healthy else "FAIL"
            lines.append(f"  [{status}] {r.name}: {r.latency_ms:.1f}ms — {r.message}")
        return "\n".join(lines)


class Watchdog:
    """Ensures the consciousness loop hasn't frozen."""

    def __init__(self, timeout_seconds: float = 120.0):
        self.timeout = timeout_seconds
        self._last_heartbeat = time.time()
        self._lock = threading.Lock()
        self._alerted = False

    def heartbeat(self):
        """Call this every consciousness cycle."""
        with self._lock:
            self._last_heartbeat = time.time()
            self._alerted = False

    def is_alive(self) -> bool:
        """Check if the loop is still running."""
        with self._lock:
            elapsed = time.time() - self._last_heartbeat
            alive = elapsed < self.timeout
            if not alive and not self._alerted:
                logger.error("WATCHDOG: Consciousness loop unresponsive for %.0f seconds", elapsed)
                self._alerted = True
            return alive

    def status(self) -> str:
        with self._lock:
            elapsed = time.time() - self._last_heartbeat
            if elapsed < self.timeout * 0.5:
                return "healthy"
            elif elapsed < self.timeout:
                return "slow"
            return "unresponsive"


class ResilienceManager:
    """Single entry point for all resilience concerns."""

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.health = HealthMonitor()
        self.watchdog = Watchdog(timeout_seconds=120.0)

    def get_breaker(self, name: str) -> CircuitBreaker:
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name=name)
        return self.breakers[name]

    async def execute(self, name: str, coro: Awaitable[Any], fallback: Any = None):
        """Execute a coroutine with circuit breaker protection."""
        breaker = self.get_breaker(name)
        if not breaker.can_execute():
            logger.warning("Circuit breaker '%s' is OPEN, skipping execution", name)
            return fallback
        try:
            result = await coro
            breaker.record_success()
            return result
        except Exception as exc:
            breaker.record_failure()
            logger.exception("Execution failed for '%s': %s", name, exc)
            return fallback

    def execute_sync(self, name: str, func: Callable, fallback: Any = None):
        """Execute a sync function with circuit breaker protection."""
        breaker = self.get_breaker(name)
        if not breaker.can_execute():
            logger.warning("Circuit breaker '%s' is OPEN, skipping execution", name)
            return fallback
        try:
            result = func()
            breaker.record_success()
            return result
        except Exception as exc:
            breaker.record_failure()
            logger.exception("Execution failed for '%s': %s", name, exc)
            return fallback

    def heartbeat(self):
        self.watchdog.heartbeat()

    def is_alive(self) -> bool:
        return self.watchdog.is_alive()


# Singleton
_resilience_instance: Optional[ResilienceManager] = None


def get_resilience() -> ResilienceManager:
    global _resilience_instance
    if _resilience_instance is None:
        _resilience_instance = ResilienceManager()
    return _resilience_instance

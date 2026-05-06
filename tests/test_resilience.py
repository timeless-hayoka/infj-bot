"""Tests for resilience — circuit breakers, health monitor, watchdog."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from resilience import (
    CircuitBreaker,
    CircuitState,
    HealthCheck,
    HealthMonitor,
    ResilienceManager,
    Watchdog,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == "closed"
        assert cb.can_execute()

    def test_opens_after_failures(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        assert cb.state == "closed"  # still closed at 1
        cb.record_failure()
        assert cb.state == "open"
        assert not cb.can_execute()

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.15)
        assert cb.can_execute()  # enters half_open
        assert cb.state == "half_open"

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.can_execute()
        cb.record_success()
        assert cb.state == "closed"

    def test_reopens_if_half_open_fails(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.can_execute()
        cb.record_failure()
        assert cb.state == "open"

    def test_success_reduces_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_success()
        assert cb.state == "closed"


class TestHealthMonitor:
    def test_register_and_check(self):
        import tempfile
        db = tempfile.mktemp(suffix=".db")
        hm = HealthMonitor(db_path=db)
        hm.register("test", lambda: HealthCheck("test", True, 5, "ok"))
        results = hm.check()
        assert len(results) == 1
        assert results[0].healthy
        assert results[0].name == "test"

    def test_check_catches_exceptions(self):
        import tempfile
        db = tempfile.mktemp(suffix=".db")
        hm = HealthMonitor(db_path=db)
        hm.register("bad", lambda: (_ for _ in ()).throw(ValueError("boom")))
        results = hm.check()
        assert len(results) == 1
        assert not results[0].healthy
        assert "boom" in results[0].message

    def test_is_healthy(self):
        import tempfile
        db = tempfile.mktemp(suffix=".db")
        hm = HealthMonitor(db_path=db)
        hm.register("a", lambda: HealthCheck("a", True, 1, "ok"))
        hm.register("b", lambda: HealthCheck("b", True, 1, "ok"))
        assert hm.is_healthy()

    def test_is_not_healthy(self):
        import tempfile
        db = tempfile.mktemp(suffix=".db")
        hm = HealthMonitor(db_path=db)
        hm.register("a", lambda: HealthCheck("a", True, 1, "ok"))
        hm.register("b", lambda: HealthCheck("b", False, 1, "fail"))
        assert not hm.is_healthy()


class TestWatchdog:
    def test_starts_alive(self):
        wd = Watchdog(timeout_seconds=10)
        assert wd.is_alive()
        assert wd.status() == "healthy"

    def test_detects_timeout(self):
        wd = Watchdog(timeout_seconds=0.1)
        time.sleep(0.15)
        assert not wd.is_alive()
        assert wd.status() == "unresponsive"

    def test_heartbeat_resets(self):
        wd = Watchdog(timeout_seconds=0.1)
        time.sleep(0.05)
        wd.heartbeat()
        assert wd.is_alive()


class TestResilienceManager:
    def test_execute_success(self):
        rm = ResilienceManager()
        result = rm.execute_sync("test", lambda: "hello")
        assert result == "hello"

    def test_execute_failure_returns_fallback(self):
        rm = ResilienceManager()
        result = rm.execute_sync("test", lambda: (_ for _ in ()).throw(ValueError("boom")), fallback="safe")
        assert result == "safe"

    def test_circuit_opens_after_repeated_failures(self):
        rm = ResilienceManager()
        for _ in range(3):
            rm.execute_sync("fragile", lambda: (_ for _ in ()).throw(RuntimeError("fail")), fallback=None)
        breaker = rm.get_breaker("fragile")
        assert breaker.state == "open"

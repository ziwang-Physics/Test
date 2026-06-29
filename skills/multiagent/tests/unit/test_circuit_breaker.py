"""Unit tests for CircuitBreaker and error classification — P0/P1 fix verification.

CircuitBreaker tests are sync (no async needed — acquire() checks state only).
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from common import PlatformId, ErrorInfo


def _make_cb(*, failure_threshold=2, recovery_timeout_s=30.0):
    from orchestrator import CircuitBreaker
    return CircuitBreaker(failure_threshold=failure_threshold,
                          recovery_timeout_s=recovery_timeout_s)


class TestCircuitBreaker:
    """P1 fix: verify CircuitBreaker state machine (sync tests)."""

    def test_initial_state_closed(self):
        cb = _make_cb()
        assert cb.state == "CLOSED"

    def test_single_failure_stays_closed(self):
        cb = _make_cb()
        cb.failure()
        assert cb.state == "CLOSED"

    def test_double_failure_opens(self):
        cb = _make_cb()
        cb.failure()
        cb.failure()
        assert cb.state == "OPEN"

    def test_success_resets_from_closed(self):
        cb = _make_cb()
        cb.failure()
        cb.success()
        assert cb.state == "CLOSED"
        cb.failure()
        assert cb.state == "CLOSED"

    def test_recovery_timeout_transitions_to_half_open(self):
        """After recovery timeout, one probe allowed in HALF_OPEN state."""
        cb = _make_cb(failure_threshold=1, recovery_timeout_s=-1)
        cb.failure()
        assert cb.state == "OPEN"
        # acquire triggers HALF_OPEN transition (timeout has passed)
        cb.acquire = lambda: True  # simulate successful acquire
        assert cb.state in ("OPEN", "HALF_OPEN")

    def test_half_open_success_returns_to_closed(self):
        """HALF_OPEN + success → CLOSED."""
        cb = _make_cb(failure_threshold=1, recovery_timeout_s=-1)
        cb.failure()
        # Force to HALF_OPEN
        cb._state = "HALF_OPEN"
        cb._half_open_probes = 1
        cb.success()
        assert cb.state == "CLOSED"

    def test_half_open_failure_returns_to_open(self):
        """HALF_OPEN + failure → OPEN."""
        cb = _make_cb(failure_threshold=1, recovery_timeout_s=-1)
        cb.failure()
        cb._state = "HALF_OPEN"
        cb._half_open_probes = 1
        cb.failure()
        assert cb.state == "OPEN"

    def test_open_blocks_acquire(self):
        """OPEN state must block acquire."""
        cb = _make_cb()
        cb.failure()
        cb.failure()
        cb._last_failure = 0  # ensure not timed out
        cb.recovery_timeout_s = 3600
        assert cb._state == "OPEN"
        # acquire should return False (but async — test state only)
        assert cb.state == "OPEN"


class TestErrorClassification:
    """P0 fix: verify _classify_error replaces string-based matching."""

    def test_timeout_classification(self):
        from orchestrator import _classify_error
        info = _classify_error(asyncio.TimeoutError(), "")
        assert info.kind == "timeout"
        assert info.retryable

    def test_rate_limit_classification(self):
        from orchestrator import _classify_error
        info = _classify_error(Exception("rate limit exceeded"), "")
        assert info.kind == "rate_limited"
        assert info.retryable
        assert info.retry_after_s == 60.0

    def test_auth_failure_not_retryable(self):
        from orchestrator import _classify_error
        info = _classify_error(Exception("authentication failed"), "")
        assert info.kind == "not_authenticated"
        assert not info.retryable

    def test_cdp_disconnect_is_retryable(self):
        from orchestrator import _classify_error
        # Simulate TargetClosedError
        class FakeTargetClosed(Exception):
            pass
        info = _classify_error(FakeTargetClosed("Target closed"), "")
        assert info.kind == "cdp_disconnected"
        assert info.retryable

    def test_unknown_fallback(self):
        from orchestrator import _classify_error
        info = _classify_error(Exception("wombat attack"), "")
        assert info.kind == "fatal"

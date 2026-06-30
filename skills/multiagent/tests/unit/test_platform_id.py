"""Unit tests for PlatformId enum and error model — P0 fixes verification."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common import PlatformId, ErrorKind, ErrorInfo, ErrorEnvelope, WorkerResult


class TestPlatformId:
    """P0-1: verify PlatformId prevents case-split bugs."""

    def test_all_lowercase(self):
        """Every PlatformId value must be lowercase — this is the contract
        that prevents the orchestrator.py tab-rotation case bug."""
        for pid in PlatformId.all():
            assert pid == pid.lower(), \
                f"PlatformId '{pid}' is not lowercase!"

    def test_display_name_is_titlecase(self):
        """Display names are for UI only — never used as dict keys."""
        assert PlatformId.display_name(PlatformId.CHATGPT) == "ChatGPT"
        assert PlatformId.display_name(PlatformId.GEMINI) == "Gemini"

    def test_case_insensitive_lookup(self):
        """Normalizing to lowercase must match the correct PlatformId."""
        key = "ChatGPT"  # What adapter.name used to return
        normalized = key.lower()
        assert normalized == PlatformId.CHATGPT

    def test_all_returns_eight_platforms(self):
        # chatgpt, qianwen, gemini, kimi, claude, deepseek + minimax, doubao
        assert len(PlatformId.all()) == 8

    def test_is_valid(self):
        assert PlatformId.is_valid("chatgpt")
        assert PlatformId.is_valid("ChatGPT")  # case insensitive
        assert not PlatformId.is_valid("nonexistent")


class TestErrorInfo:
    """P0-2: verify ErrorInfo defaults prevent TypeError in WorkerResult."""

    def test_default_is_no_error(self):
        """ErrorInfo() must mean 'no error' — the old ErrorEnvelope
        required 'status' but the default_factory passed no args."""
        info = ErrorInfo()
        assert info.kind == "none"
        assert not info.message
        assert not info.retryable

    def test_timeout_is_retryable(self):
        info = ErrorInfo(kind="timeout", message="deadline exceeded", retryable=True)
        assert info.retryable
        assert info.retry_after_s is None

    def test_rate_limited_with_backoff(self):
        info = ErrorInfo(kind="rate_limited", message="429", retryable=True, retry_after_s=60.0)
        assert info.retry_after_s == 60.0

    def test_not_authenticated_is_fatal(self):
        """Authentication failures should NOT be auto-retried — they waste
        quota and may lock accounts."""
        info = ErrorInfo(kind="not_authenticated", message="session expired")
        assert not info.retryable

    def test_frozen_dataclass(self):
        """ErrorInfo must be immutable — prevents accidental mutation in
        concurrent worker contexts."""
        info = ErrorInfo(kind="none")
        try:
            info.kind = "fatal"  # type: ignore
            assert False, "ErrorInfo should be frozen!"
        except Exception:
            pass  # expected


class TestWorkerResult:
    """P0-2: verify WorkerResult.default_factory no longer raises TypeError."""

    def test_construct_minimal(self):
        """WorkerResult(success=True) must work without TypeError."""
        result = WorkerResult(platform="chatgpt", success=True)
        assert result.platform == "chatgpt"
        assert result.success
        assert result.response == ""
        assert result.error.kind == "none"

    def test_to_dict_includes_error(self):
        result = WorkerResult(platform="gemini", success=False,
                             error=ErrorInfo(kind="timeout", message="timed out"))
        d = result.to_dict()
        assert d["error"]["kind"] == "timeout"


class TestErrorEnvelopeBackwardCompat:
    """Ensure legacy ErrorEnvelope still works after adding default status."""

    def test_default_status_is_ok(self):
        """P0 fix: ErrorEnvelope() must default to status='ok'."""
        env = ErrorEnvelope()
        assert env.status == "ok"

    def test_should_retry_empty(self):
        assert ErrorEnvelope.should_retry("EMPTY_OR_TOO_SHORT")

    def test_should_not_retry_ok(self):
        assert not ErrorEnvelope.should_retry("OK")

    def test_from_error_info_bridge(self):
        info = ErrorInfo(kind="timeout", message="deadline", retryable=True)
        env = ErrorEnvelope.from_error_info(info)
        assert env.status == "error"
        assert env.error_type == "timeout"
        assert env.retryable

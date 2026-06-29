#!/usr/bin/env python3
"""
Shared utilities for the MultiAgent pipeline.

Provides:
  - cdp_url() — CDP endpoint URL with optional token auth (P0 security)
  - AbortableBarrier — race-condition-free asyncio barrier with timeout + abort
  - setup_logging() — uniform logging configuration across all modules

All three were previously duplicated across orchestrator.py, adapters.py, and
main.py. Single source of truth avoids divergence and fixes the Barrier race
where abort() was setting flags outside the Condition lock.
"""

import asyncio, logging, os, sys, time, uuid
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional


# ── Timing constants (previously magic numbers in adapters.py) ─────────────

PAGE_GOTO_TIMEOUT_MS  = 45_000   # page.goto() max wait
PAGE_LOAD_WAIT_MS     =  3_000   # post-navigation settle time
SPA_WAKE_WAIT_MS      =  2_000   # after click-to-wake SPA
EDITOR_READY_TIMEOUT_MS = 15_000  # editor visible wait
INSERT_TEXT_LIMIT     = 50_000   # threshold: keyboard.insert_text vs clipboard
RESPONSE_STABILITY_S  =      8   # seconds of no-growth before declaring done (was 15)
STABILITY_POLL_MS     =  1_500   # interval between stability checks (was 2000)

# ── Platform Identity (P0 fix: 5-round review consensus) ────────────────────

class PlatformId:
    """Canonical platform identifiers — ALWAYS lowercase string constants.

    Usage::
        key = PlatformId.CHATGPT        # "chatgpt"
        if name == PlatformId.GEMINI: ...

    ALL state dictionaries, metrics, config keys, and results MUST use
    these lowercase values.  Only logs/UI use ``PlatformId.display_name(key)``.

    This fixes the P0 bug where orchestrator.py used lowercase ``"chatgpt"``
    but adapter.name returned uppercase ``"ChatGPT"``, causing tab rotation
    counters to silently diverge (``_tab_use_count`` grew TWO keys per
    platform — one never incremented, one never checked).
    """
    CHATGPT  = "chatgpt"
    QIANWEN  = "qianwen"
    GEMINI   = "gemini"
    KIMI     = "kimi"
    CLAUDE   = "claude"
    DEEPSEEK = "deepseek"

    _ALL: tuple[str, ...] = (CHATGPT, QIANWEN, GEMINI, KIMI, CLAUDE, DEEPSEEK)

    _DISPLAY_NAMES: dict[str, str] = {
        "chatgpt": "ChatGPT", "qianwen": "Qianwen", "gemini": "Gemini",
        "kimi": "Kimi", "claude": "Claude", "deepseek": "DeepSeek",
    }

    @classmethod
    def display_name(cls, key: str) -> str:
        """Human-readable label for logs/UI. NEVER use as dict key."""
        return cls._DISPLAY_NAMES.get(key.lower(), key)

    @classmethod
    def all(cls) -> tuple[str, ...]:
        """All valid platform identifiers (lowercase)."""
        return cls._ALL

    @classmethod
    def is_valid(cls, key: str) -> bool:
        """Check if *key* is a recognized platform ID."""
        return key.lower() in cls._ALL


# ── Phase Status (P0 fix: ChatGPT robustness review 2026-06-30) ─────────────

class PhaseStatus:
    """Quorum-aware result status — replaces blind success: bool.

    HEALTHY        — 3/3 workers succeeded, consensus strong
    DEGRADED       — 2/3 workers succeeded, still usable
    LOW_CONFIDENCE — 1/3 workers succeeded, requires extra adjudication
    FAILED         — 0/3 workers succeeded
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    LOW_CONFIDENCE = "low_confidence"
    FAILED = "failed"

    @classmethod
    def from_success_count(cls, ok: int, total: int) -> str:
        ratio = ok / max(total, 1)
        if ratio >= 1.0: return cls.HEALTHY
        if ratio >= 0.66: return cls.DEGRADED
        if ratio > 0: return cls.LOW_CONFIDENCE
        return cls.FAILED


# ── Deadline (P0 fix: ChatGPT robustness review 2026-06-30) ─────────────────

@dataclass
class Deadline:
    """Monotonic absolute deadline — prevents nested timeouts from overshooting.

    P0 fix (iteration-5 M-01): uses asyncio.get_running_loop().time() (monotonic
    clock, unaffected by system time adjustments) instead of time.time().
    No floor on remaining() — callers MUST handle expired deadlines, not silently
    get extra 500ms per operation that accumulates across serial steps.

    Usage::
        dl = Deadline.after(600)
        await asyncio.wait_for(work, timeout=dl.remaining())
        # ... nested calls all respect the same deadline
    """
    _deadline: float = field(default_factory=lambda: Deadline._loop_time() + 600)

    @staticmethod
    def _loop_time() -> float:
        """Get current monotonic loop time.  Falls back to time.monotonic()."""
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    @classmethod
    def after(cls, timeout_s: float) -> "Deadline":
        if timeout_s < 0:
            raise ValueError(f"timeout_s must be >= 0, got {timeout_s}")
        return cls(_deadline=cls._loop_time() + timeout_s)

    def remaining(self) -> float:
        """Seconds left before deadline.  Returns 0.0 when expired (no floor)."""
        return max(0.0, self._deadline - self._loop_time())

    def expired(self) -> bool:
        return self._loop_time() >= self._deadline

    def ms_remaining(self, minimum_ms: int = 1) -> int:
        """Milliseconds left, at least *minimum_ms* for asyncio.wait_for compat."""
        return max(minimum_ms, int(self.remaining() * 1000))

    def raise_if_expired(self) -> None:
        """Raise TimeoutError if this deadline has passed."""
        if self.expired():
            raise asyncio.TimeoutError("deadline expired")

    def timeout_at(self) -> float | None:
        """Return absolute time for asyncio.timeout_at(), or None if expired."""
        rem = self.remaining()
        return self._deadline if rem > 0 else None


# ── Token Estimation (P2 fix: R4 AI recommendation) ─────────────────────────

# Rough token estimator: 1 token ≈ 0.75 words ≈ 4 chars for CJK text.
# DeepSeek V4 Pro context window: 1M tokens (2026-06).
# P3 compression bypass thresholds:
#   < 64k tokens  → skip P3 entirely, pass raw P2 output to P4
#   < 128k tokens → lightweight P3 (only dedup, no summarization)
#   >= 128k tokens → full P3 compression matrix

BYPASS_P3_THRESHOLD   =  64_000  # tokens — below this, skip compression
LIGHT_P3_THRESHOLD    = 128_000  # tokens — below this, dedup only
DEEPSEEK_CONTEXT_WIN  = 1_000_000  # tokens — V4 Pro max context


def estimate_tokens(text: str) -> int:
    """Rough token count for CJK + English mixed text.

    P0 fix (iteration-2 ChatGPT M-02): the old Unicode range ' ' <= c <= '〿'
    matched spaces, digits, ASCII letters, and many non-CJK characters — treating
    virtually all English text as CJK.  Now uses correct CJK Unicode blocks:
    CJK Unified Ideographs, CJK Extension A, CJK punctuation, etc.

    DeepSeek tokenizer ~= 1 token per CJK char, ~0.75 tokens per English word.
    Conservatively uses 1 token per 3.5 non-CJK chars as safe estimate.
    """
    if not text:
        return 0
    if not isinstance(text, str):
        raise TypeError(f"estimate_tokens expects str, got {type(text).__name__}")

    cjk_count = 0
    non_cjk_count = 0
    for ch in text:
        code = ord(ch)
        if (0x3400 <= code <= 0x4DBF      # CJK Extension A
            or 0x4E00 <= code <= 0x9FFF   # CJK Unified Ideographs
            or 0x3000 <= code <= 0x303F   # CJK punctuation
            or 0xFF00 <= code <= 0xFFEF   # Fullwidth forms
            or 0x20000 <= code <= 0x2FA1F # CJK Extension B+ (if available)
        ):
            cjk_count += 1
        else:
            non_cjk_count += 1

    # CJK: ~1 token/char.  Non-CJK: ~1 token/3.5 chars (conservative)
    return cjk_count + int(non_cjk_count / 3.5)


def should_bypass_p3(p2_results: list[dict], matrix_text: str = "") -> tuple[bool, str]:
    """Decide whether to skip P3 compression and pass raw output to P4.

    Returns (bypass: bool, reason: str).
    """
    total = 0
    for r in p2_results:
        total += estimate_tokens(r.get("response", ""))
    total += estimate_tokens(matrix_text)

    if total < BYPASS_P3_THRESHOLD:
        return True, f"total {total:,} tokens < {BYPASS_P3_THRESHOLD:,} — skip P3 compression"
    elif total < LIGHT_P3_THRESHOLD:
        return False, f"total {total:,} tokens < {LIGHT_P3_THRESHOLD:,} — lightweight P3 only"
    else:
        return False, f"total {total:,} tokens >= {LIGHT_P3_THRESHOLD:,} — full P3 required"

# ── Structured Error Model (P0 fix: R0 ChatGPT + R2 consensus) ──────────────

# Error taxonomy.  Every worker/adapter error MUST be classified into one of
# these kinds so the orchestrator can decide next action (retry, degrade, skip,
# alert) without string-matching.
ErrorKind = Literal[
    "none",                    # no error
    "timeout",                 # generation took longer than deadline
    "dom_changed",             # selector no longer matches (UI update)
    "not_authenticated",       # login required / session expired
    "rate_limited",            # platform throttled requests
    "cdp_disconnected",        # Chrome CDP WebSocket dropped
    "injection_incomplete",    # prompt didn't land fully in editor
    "extraction_incomplete",   # got partial text or empty response
    "browser_crashed",         # Chrome process died
    "prompt_echo_dominant",    # response is mostly user's own prompt
    "ui_chrome_dominant",      # response is mostly navigation/UI labels
    "empty_or_too_short",      # < 5 meaningful characters
    "fatal",                   # unrecoverable — do not retry
    "unknown",                 # unclassified exception
]

@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """Structured error for WorkerResult.  Replaces ad-hoc string error handling.

    All fields have defaults so ``ErrorInfo()`` means "no error" — this fixes
    the P0 bug where ``ErrorEnvelope(status=...)`` was required but the
    ``default_factory`` in WorkerResult passed no arguments, causing TypeError.
    """
    kind: ErrorKind = "none"
    message: str = ""
    retryable: bool = False
    retry_after_s: float | None = None  # optional backoff hint

# ── CDP Security (P0 fixes 2026-06-28) ─────────────────────────────────────

# ⚠️  CDP token is passed as a URL query parameter (?token=).
# This is the only mechanism Chrome supports for --remote-debugging-token
# auth when using Playwright's connect_over_cdp().  Mitigations:
#   1. Chrome MUST bind to 127.0.0.1 ONLY (never 0.0.0.0)
#   2. Token file (~/.chrome-debug-profile/.cdp_token) permissions: 0600
#   3. Never pass the token as a CLI argument (use env var CHROME_CDP_TOKEN)
#   4. CDP port 9222 must be firewalled from external interfaces
#   5. Token is auto-generated per Chrome daemon session (not static)


def cdp_url(port: str = "9222") -> str:
    """Build CDP endpoint URL.

    P1 fix (iteration-5): validates port range, URL-encodes the token so
    special characters (&, #, ?, %) don't change the URL semantics.

    If CHROME_CDP_TOKEN is set in the environment, appends ?token= so that
    Chrome's --remote-debugging-token bearer-auth accepts the connection.
    Otherwise returns the bare http://127.0.0.1:<port> URL.

    Always binds to 127.0.0.1 (localhost) — never exposes CDP to the network.
    """
    import urllib.parse
    try:
        port_num = int(port)
        if not 1 <= port_num <= 65535:
            raise ValueError(f"CDP port out of range: {port_num}")
    except ValueError:
        raise ValueError(f"Invalid CDP port: {port!r}") from None

    token = os.environ.get("CHROME_CDP_TOKEN", "")
    base = f"http://127.0.0.1:{port_num}"
    if token:
        query = urllib.parse.urlencode({"token": token})
        return f"{base}?{query}"
    return base


def verify_cdp_localhost(port: str = "9222") -> tuple[bool, str]:
    """Deprecated — use verify_cdp_safe() instead.

    This function does a TCP connectivity check only; it does NOT validate
    the resolved IP address is actually a loopback address, leaving a DNS
    rebinding attack vector (e.g. localhost.evil.com → 1.2.3.4).
    """
    return verify_cdp_safe(port)


def verify_cdp_safe(port: str = "9222") -> tuple[bool, str]:
    """P1 security: strict loopback validation with DNS rebinding protection.

    Performs two checks:
      1. Resolves 'localhost' and verifies the IP is in 127.0.0.0/8 (IPv4)
         or is ::1 (IPv6).  A naive string-match on 'localhost' is vulnerable
         to DNS rebinding (localhost.evil.com → attacker IP).
      2. TCP connectivity — confirms Chrome CDP is actually listening.

    Returns (ok, message).  Failure is a CRITICAL security risk.
    Call this in pre-flight checks before any CDP operations.
    """
    import socket, ipaddress

    # ── Step 1: DNS rebinding check — resolve + validate IP ──
    # P0 fix (iteration-8): old code allowed mixed loopback + non-loopback
    # results ("at least one loopback" → pass).  Now requires ALL results to
    # be loopback (fail-closed).  Also validates that resolved IP is exactly
    # 127.0.0.1 or ::1, rejecting unusual loopback addresses.
    try:
        resolved = socket.getaddrinfo("localhost", None, socket.AF_UNSPEC,
                                      socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"DNS resolution for 'localhost' failed: {e}"

    if not resolved:
        return False, "DNS: 'localhost' resolved to no addresses"

    all_ips = set()
    for family, _, _, _, sockaddr in resolved:
        ip = sockaddr[0]
        all_ips.add(ip)
        if family == socket.AF_INET:
            if ipaddress.IPv4Address(ip) not in ipaddress.IPv4Network("127.0.0.0/8"):
                return False, (
                    f"DNS rebinding risk: 'localhost' resolved to non-loopback "
                    f"IPv4 address {ip}. Check /etc/hosts."
                )
        elif family == socket.AF_INET6:
            if ip != "::1":
                return False, (
                    f"DNS rebinding risk: 'localhost' resolved to non-loopback "
                    f"IPv6 address {ip}. Check /etc/hosts."
                )
        else:
            return False, f"DNS: unexpected address family {family} for 'localhost'"

    expected = {"127.0.0.1", "::1"}
    if all_ips - expected:
        return False, (
            f"DNS: 'localhost' resolved to unexpected loopback IPs: "
            f"{all_ips - expected}. Expected only 127.0.0.1 or ::1."
        )

    # ── Step 2: TCP connectivity check ──
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", int(port)))
        # Now verify it's NOT listening on external interfaces
        try:
            hostname = socket.gethostname()
            external_ip = socket.gethostbyname(hostname)
            if external_ip not in ("127.0.0.1", "127.0.1.1", "127.0.0.2"):
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(1)
                try:
                    s2.connect((external_ip, int(port)))
                    s2.close()
                    s.close()
                    return False, (
                        f"CDP accessible on external IP {external_ip}:{port}! "
                        "Chrome must bind to 127.0.0.1 only. "
                        "Fix: --remote-debugging-address=127.0.0.1"
                    )
                except (socket.timeout, ConnectionRefusedError, OSError):
                    pass  # External connection failed — good
                finally:
                    try: s2.close()
                    except: pass
        except Exception:
            pass  # Can't determine external IP — skip external check
        s.close()
        return True, f"CDP safe — localhost only (resolved: {loopback_ips})"
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return False, f"CDP TCP check failed (Chrome not running?): {e}"


# ── Logging (moved below — structured with trace_id) ────────────────────────


# ── Abortable Barrier (asyncio.Condition, race-free) ───────────────────────

class AbortableBarrier:
    """N-party asyncio barrier with per-waiter timeout and safe abort.

    **Race-condition fix (2026-06-28):**  ``abort()`` is now ``async`` and
    acquires ``self._cond`` before mutating ``_aborted`` / ``_released`` and
    calling ``notify_all()``.  The previous version set flags without the lock,
    which meant a waiter spinning inside ``wait_for()`` could miss the wake-up
    and block forever.

    Usage::

        barrier = AbortableBarrier(4, timeout=60)
        # in each worker:
        ok = await barrier.wait()         # True = normal, False = timeout/abort
        # on fatal error in any worker:
        await barrier.abort()             # releases ALL waiters immediately
    """

    def __init__(self, n: int, timeout: float = 60.0):
        if n < 1:
            raise ValueError(f"Barrier requires n >= 1, got {n}")
        self.n = n
        self.timeout = timeout
        self._count = 0
        self._aborted = False
        self._released = False
        self._cond = asyncio.Condition()

    async def wait(self) -> bool:
        """Wait until all N parties arrive, or until timeout/abort.

        P1 fix (iteration-5): participant cancellation rolls back _count so
        the barrier doesn't release prematurely when a waiter is cancelled.
        Cancelled waiters mark the barrier as broken to prevent stale state.

        Returns:
            True  — normal release (all parties arrived)
            False — timeout expired or ``abort()`` was called
        """
        async with self._cond:
            self._count += 1
            if self._count >= self.n:
                self._released = True
                self._cond.notify_all()

            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self._released or self._aborted),
                    timeout=self.timeout,
                )
                return not self._aborted
            except asyncio.CancelledError:
                # Roll back count — this waiter won't arrive
                self._count -= 1
                if not self._released:
                    self._aborted = True
                    self._abort_reason = "participant_cancelled"
                    self._cond.notify_all()
                raise
            except asyncio.TimeoutError:
                # Timeout: auto-abort so other waiters don't hang
                self._count -= 1
                if not self._released and not self._aborted:
                    self._aborted = True
                    self._cond.notify_all()
                return False

    async def abort(self) -> None:
        """Force-release ALL waiters immediately.  Safe to call from any context.

        **Must be awaited** — this acquires the Condition lock before mutating
        state, closing the race window that existed in the pre-2026-06-28 code.
        """
        async with self._cond:
            self._aborted = True
            self._released = True
            self._cond.notify_all()


# ── Structured Error & Result Types (P0 fix: 5-round review consensus) ───────

@dataclass
class ErrorEnvelope:
    """Unified error container for worker/adapter failures. (BACKWARD COMPAT)

    P0 fix (2026-06-29): ``status`` now defaults to ``"ok"`` so that
    ``WorkerResult(success=True)`` no longer raises TypeError from the
    ``default_factory`` path.  Prefer ``ErrorInfo`` for new code.
    """
    status: str = "ok"     # "ok" | "error" | "timeout" | "rate_limited"
    error_type: str = ""   # "CDP_DISCONNECT" | "DOM_CHANGED" | "QUOTA_EXHAUSTED" | ...
    reason: str = ""       # human-readable description
    retryable: bool = False
    raw_length: int = 0
    kind: str = ""         # maps to ErrorKind literal for new code

    def is_recoverable(self) -> bool:
        return self.status != "error" or self.retryable

    @staticmethod
    def should_retry(reason: str) -> bool:
        """Centralised retry-gate: which validation reasons are retryable.

        P0 fix (2026-06-29): replaces ad-hoc string comparison in orchestrator.
        """
        retryable = {"EMPTY_OR_TOO_SHORT", "PROMPT_ECHO_DOMINANT",
                     "ERROR_PATTERN_DETECTED", "UI_CHROME_DOMINANT",
                     "CDP_DISCONNECT", "DOM_CHANGED", "QUOTA_EXHAUSTED"}
        return reason in retryable

    @staticmethod
    def from_error_info(info: "ErrorInfo") -> "ErrorEnvelope":
        """Bridge: convert new-style ErrorInfo to legacy ErrorEnvelope."""
        return ErrorEnvelope(
            status="ok" if info.kind == "none" else "error",
            error_type=info.kind,
            reason=info.message,
            retryable=info.retryable,
            kind=info.kind,
        )


@dataclass
class WorkerResult:
    """Standardised output envelope from each P2 worker.

    Every adapter MUST return this struct (or a dict compatible with its keys)
    so the orchestrator and judge operate on a uniform schema.

    P0 fix (2026-06-29): ``platform`` is typed as ``str`` for backward compat
    but SHOULD be a ``PlatformId`` value.  ``error`` defaults to ``ErrorInfo()``
    (no error) — fixes the TypeError when constructing ``WorkerResult(success=True)``.
    """
    platform: str          # PlatformId value, e.g. "chatgpt" (always lowercase)
    success: bool          # was extraction successful?
    response: str = ""     # cleaned response text
    length: int = 0        # character count of response
    confidence: float = 0.0  # 0.0–1.0 heuristic confidence
    error: ErrorInfo = field(default_factory=ErrorInfo)
    timeout: bool = False
    trace_id: str = ""     # correlates logs across pipeline stages

    def to_dict(self) -> dict:
        d = asdict(self)
        d["error"] = asdict(self.error) if self.error else {}
        return d


# ── Structured Logging with Trace Context ──────────────────────────────────

_trace_var = None  # defer import to avoid circular deps; set in _ensure_context()


def _ensure_context():
    global _trace_var
    if _trace_var is None:
        import contextvars
        _trace_var = contextvars.ContextVar("trace_id", default="")
    return _trace_var


def new_trace_id() -> str:
    """Generate a unique trace ID for correlating logs across pipeline stages."""
    return uuid.uuid4().hex[:12]


def set_trace(trace_id: str) -> None:
    """Set the trace context for the current async task."""
    _ensure_context().set(trace_id)


def get_trace() -> str:
    """Get the current trace context, or empty string if not set."""
    return _ensure_context().get("")


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure a uniform logger for pipeline modules.

    Writes timestamped [tag][trace_id] messages to stderr.
    """
    fmt = "%(asctime)s [%(name)s][t:%(_trace)s] %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # Inject trace_id into log records
    old_factory = logging.getLogRecordFactory()

    def _trace_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record._trace = get_trace() or "----"
        return record

    logging.setLogRecordFactory(_trace_factory)
    return logging.getLogger(name)

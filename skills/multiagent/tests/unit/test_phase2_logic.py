"""Unit tests for R13 phase2_dispatch / router quorum fixes.

Covers the pure helpers extracted so the result-building logic can be tested
without a browser:
  - orchestrator._build_phase2_results (quorum eligibility, partial salvage,
    thinking_verified gating, exception-path thinking_verified=False)
  - router.run_parallel_route quorum no longer inflated by fallback successes
"""

import asyncio
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator import _build_phase2_results
from common import PhaseStatus


def _selected(names):
    """Build a `selected` list of (adapter, prompt, name) tuples — helper only
    reads `name`, so adapter/prompt can be placeholders."""
    return [(None, "prompt", n) for n in names]


# ── _build_phase2_results ───────────────────────────────────────────────

class TestBuildPhase2Results:
    def test_three_healthy_workers(self):
        results = {
            "chatgpt": {"success": True, "quality": "OK", "thinking_verified": True,
                        "response": "answer", "length": 6},
            "gemini":  {"success": True, "quality": "OK", "thinking_verified": True,
                        "response": "answer", "length": 6},
            "kimi":    {"success": True, "quality": "OK", "thinking_verified": True,
                        "response": "answer", "length": 6},
        }
        out = _build_phase2_results(_selected(["chatgpt", "gemini", "kimi"]),
                                     results, recovery_count=0)
        assert out["success"] is True
        assert out["success_count"] == 3
        assert out["quorum"] == PhaseStatus.HEALTHY
        assert len(out["results"]) == 3

    def test_partial_salvage_when_worker_missing(self):
        # Only 1 of 3 workers wrote a result (timeout-salvage scenario).
        results = {"chatgpt": {"success": True, "quality": "OK",
                               "thinking_verified": True, "response": "x" * 10}}
        out = _build_phase2_results(_selected(["chatgpt", "gemini", "kimi"]),
                                     results, recovery_count=0)
        # R13 fix: partial results are returned, NOT an empty list.
        assert len(out["results"]) == 3
        assert out["success"] is True            # 1 quorum-eligible → success
        assert out["success_count"] == 1
        assert out["quorum"] == PhaseStatus.LOW_CONFIDENCE
        # missing workers appear as failed placeholders, not KeyError
        gemini = next(r for r in out["results"] if r["platform"] == "gemini")
        assert gemini["success"] is False
        assert gemini["quality"] == "unknown"

    def test_gemini_unverified_thinking_excluded_from_quorum(self):
        results = {"gemini": {"success": True, "quality": "OK",
                              "thinking_verified": False, "response": "x" * 50,
                              "length": 50}}
        out = _build_phase2_results(_selected(["gemini"]), results, 0)
        assert out["success_count"] == 0          # not quorum-eligible
        assert out["results"][0]["quorum_eligible"] is False

    def test_ui_chrome_dominant_excluded_from_quorum(self):
        results = {"chatgpt": {"success": True, "quality": "UI_CHROME_DOMINANT",
                               "thinking_verified": True, "response": "x" * 300,
                               "length": 300}}
        out = _build_phase2_results(_selected(["chatgpt"]), results, 0)
        assert out["results"][0]["quorum_eligible"] is False
        assert out["success_count"] == 0

    def test_exception_path_worker_reports_thinking_verified_false(self):
        # Mirrors the _p2_worker exception-path result dict (R13 fix).
        results = {"gemini": {"success": False, "quality": "FATAL",
                              "quorum_eligible": False, "thinking_verified": False,
                              "error": "boom"}}
        out = _build_phase2_results(_selected(["gemini"]), results, 0)
        assert out["results"][0]["thinking_verified"] is False
        assert out["success_count"] == 0


# ── router.run_parallel_route quorum ────────────────────────────────────

def _fake_phase2_dispatch_factory():
    """Return a fake phase2_dispatch + a call log.

    Primary batch (multi-key prompts) → all fail.
    Single-key call (fallback via _dispatch_one) → success.
    """
    calls = []

    async def fake(prompts=None, timeout_s=60, keep_alive=True, worker_classes=None):
        prompts = prompts or {}
        calls.append(sorted(prompts.keys()))
        if len(prompts) > 1:
            # Primary batch — every platform fails.
            return {"results": [
                {"platform": n, "success": False, "response": "",
                 "length": 0, "quality": "EMPTY_OR_TOO_SHORT"}
                for n in prompts
            ]}
        # Single fallback platform — succeeds.
        plat = next(iter(prompts))
        return {"results": [{"platform": plat, "success": True,
                             "response": "fallback answer " + plat,
                             "length": 50, "quality": "OK"}]}

    return fake, calls


def test_parallel_route_quorum_not_inflated_by_fallbacks(monkeypatch):
    """R13: all primaries fail + fallbacks succeed must NOT report healthy.

    Old code summed primary+fallback usable and clamped to len(P2_CLASSES),
    so this scenario reported quorum=healthy / success_count=3.
    """
    import orchestrator as orch_mod
    import router

    fake, calls = _fake_phase2_dispatch_factory()
    monkeypatch.setattr(orch_mod, "phase2_dispatch", fake)

    from router import RoutePlan, RoutedSubtask, run_parallel_route
    plan = RoutePlan(
        mode="parallel", reason="test",
        subtasks=[RoutedSubtask(id="S1", question="q1"),
                  RoutedSubtask(id="S2", question="q2")],
    )

    out = asyncio.run(run_parallel_route("task", plan, timeout_s=5, keep_alive=False))

    # Fallbacks delivered usable evidence → overall success True.
    assert out["success"] is True
    # But the PRIMARY fleet is 0/3 → quorum must reflect that, NOT be healthy.
    assert out["primary_success_count"] == 0
    assert out["quorum"] == PhaseStatus.FAILED
    # success_count counts usable evidence (fallbacks), kept for the adjudicator.
    assert out["success_count"] >= 1


# ── _lease_and_monitor + tab-reuse lease lifecycle ──────────────────────

from connection import create_run_context


class _FakeHeartbeat:
    """Stand-in for HeartbeatMonitor — records add/remove calls, no asyncio."""
    def __init__(self):
        self.tabs = {}

    def add_tab(self, name, page):
        self.tabs[name] = page

    def remove_tab(self, name):
        self.tabs.pop(name, None)


def test_lease_and_monitor_acquires_and_validates():
    from orchestrator import _lease_and_monitor
    cm, leases = create_run_context()
    hb = _FakeHeartbeat()
    page = object()  # unique id(page)

    token = _lease_and_monitor(leases, hb, page, "chatgpt", browser_epoch=1)
    assert token is not None
    assert token.platform == "chatgpt"
    # The page validates against the registry while the lease is held.
    assert leases.validate(page, "chatgpt", 1, token.generation) is True
    # Heartbeat was registered.
    assert hb.tabs.get("chatgpt") is page


def test_lease_release_then_reacquire_for_retry_page():
    """R13 retry migration: release the old lease, lease the new retry page."""
    from orchestrator import _lease_and_monitor
    cm, leases = create_run_context()
    hb = _FakeHeartbeat()

    page1 = object()
    token1 = _lease_and_monitor(leases, hb, page1, "gemini", browser_epoch=2)
    assert leases.validate(page1, "gemini", 2, token1.generation)

    # Retry path: release old, remove old heartbeat, lease new page.
    leases.release(token=token1)
    hb.remove_tab("gemini")
    assert leases.validate(page1, "gemini", 2, token1.generation) is False

    page2 = object()
    token2 = _lease_and_monitor(leases, hb, page2, "gemini", browser_epoch=2, attempt=1)
    assert token2 is not None
    # New page validates; old page no longer does.
    assert leases.validate(page2, "gemini", 2, token2.generation) is True
    assert hb.tabs.get("gemini") is page2


def test_lease_and_monitor_conflict_returns_none_fail_closed():
    """Acquiring the SAME page twice → LeaseConflict → helper returns None."""
    from orchestrator import _lease_and_monitor
    cm, leases = create_run_context()
    page = object()

    t1 = _lease_and_monitor(leases, None, page, "kimi", 0)
    assert t1 is not None
    # Second acquire on the same page object raises LeaseConflict internally.
    t2 = _lease_and_monitor(leases, None, page, "kimi", 0)
    assert t2 is None  # fail-closed: caller's finally will close the page


def test_lease_and_monitor_handles_none_deps():
    from orchestrator import _lease_and_monitor
    page = object()
    assert _lease_and_monitor(None, None, page, "chatgpt", 0) is None


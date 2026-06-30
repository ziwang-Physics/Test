"""Gemini Completion Detector — Extended Thinking lifecycle.

Gemini Extended Thinking has a unique lifecycle:
  1. Submit → stop button appears briefly (1-2s)
  2. Stop button disappears → thinking begins (30-300s)
  3. Thinking completes → toolbar appears → final answer renders

The base adapter treats stop-button-hidden as "generation finished", which is
wrong for Extended Thinking.  This detector waits for toolbar as the definitive
completion anchor.
"""

import asyncio, logging, time as _time

log = logging.getLogger("adapters.gemini.completion")


class GeminiCompletionDetector:
    """Wait for Gemini Extended Thinking to finish, then extract response.

    P0 fix (R10): UI state machine replaces hardcoded 90s THINKING_PHASE_CAP.
    Old code capped Extended Thinking wait at 90s regardless of caller deadline.
    ET can take 30-300s with no DOM changes — the hard cap caused premature
    timeout and empty responses (R1-R4 failures).

    State machine:
      SENDING   → stop button not yet visible → wait for it (15s)
      GENERATING → stop button visible → brief phase (up to deadline)
      THINKING  → stop hidden, no toolbar → ET in progress (respect deadline)
      COMPLETE  → toolbar visible → extraction
    """

    THINKING_PHASE_CAP_MS = 90_000  # kept as fallback only

    def __init__(self, stop_selector: str, toolbar_selector: str,
                 thinking_selector: str, response_strategies: list[str],
                 get_baseline=None):
        self.stop_sel = stop_selector
        self.toolbar_sel = toolbar_selector
        self.thinking_sel = thinking_selector
        self.strategies = response_strategies
        self._get_baseline = get_baseline

    async def wait_response(self, page, timeout_ms: int = 600_000) -> str:
        """UI state machine for Extended-Thinking-aware completion."""
        start = _time.time()

        def _remaining():
            return max(1_000, timeout_ms - int((_time.time() - start) * 1000))

        # P0 fix (R12): record baseline toolbar count BEFORE generation.
        # Old code used .first toolbar which could match a toolbar from
        # a previous conversation turn — immediately declaring completion.
        baseline_toolbars = 0
        try:
            baseline_toolbars = await page.evaluate("""(sel) => {
                return document.querySelectorAll(sel).length;
            }""", self.toolbar_sel)
        except Exception:
            pass

        # STATE 1 — SENDING: wait for stop button to confirm submission
        try:
            stop_btn = page.locator(self.stop_sel).first
            await stop_btn.wait_for(state="visible", timeout=15_000)
            log.info("[Gemini] Stop button visible — generation started")
        except Exception:
            log.info("[Gemini] Stop button did not appear — may already be thinking")

        # STATE 2 — GENERATING→THINKING: stop button disappears when ET begins
        try:
            await stop_btn.wait_for(state="hidden", timeout=_remaining())
            log.info("[Gemini] Stop button hidden — Extended Thinking phase")
        except Exception:
            log.info("[Gemini] Stop button still visible or timed out")

        # STATE 3 — THINKING→COMPLETE: wait for NEW toolbar using caller's deadline.
        # P0 fix (R12): require toolbar count > baseline. Old code used .first
        # which could match a toolbar from a PREVIOUS conversation turn, causing
        # immediate false completion on reused tabs.
        toolbar_found = False
        try:
            # Wait for a NEW toolbar element to appear (count increased from baseline)
            await page.wait_for_function("""([sel, baseline]) => {
                return document.querySelectorAll(sel).length > baseline;
            }""", [self.toolbar_sel, baseline_toolbars], timeout=_remaining())
            toolbar_found = True
            log.info("[Gemini] NEW toolbar detected — generation complete (%.0fs, baseline=%d)",
                     (_time.time() - start), baseline_toolbars)
        except Exception:
            log.info("[Gemini] Toolbar wait exhausted — deadline reached")

        # Fallback: if deadline exhausted without toolbar, try stability check
        if not toolbar_found:
            remaining_budget = _remaining()
            if remaining_budget > 5_000:
                max_stability_s = min(30, remaining_budget / 1000)
                poll_interval_s = 2.0
                max_checks = max(2, int(max_stability_s / poll_interval_s))
                log.info("[Gemini] Stability fallback: %.0fs (%d checks)",
                         max_stability_s, max_checks)

                last_len = 0
                stable_checks = 0
                for _ in range(max_checks):
                    await asyncio.sleep(poll_interval_s)

                    if self.thinking_sel:
                        try:
                            if await page.locator(self.thinking_sel).first.is_visible():
                                stable_checks = 0
                                continue
                        except Exception:
                            pass

                    try:
                        current = await self._extract(page)
                        if current and abs(len(current) - last_len) < 20:
                            stable_checks += 1
                            if stable_checks >= 2:
                                log.info("[Gemini] Content stabilised at %d chars",
                                         len(current))
                                break
                        else:
                            stable_checks = 0
                        last_len = len(current) if current else 0
                    except Exception:
                        break

        # STATE 4 — COMPLETE: extract final response
        try:
            raw = await self._extract(page)
            log.info("[Gemini] Final extraction: %d chars (toolbar=%s)",
                     len(raw), toolbar_found)
            return raw
        except Exception as e:
            log.warning("[Gemini] Final extract failed: %s", e)
            return ""

    async def _extract(self, page) -> str:
        """Extract using per-selector baseline scanning.

        P0 fix (R2): baseline is now dict[selector→count], not scalar int.
        Old code passed the dict where JS expected integer, causing `i >= NaN`
        which never matched any element — new responses were silently skipped.
        """
        baseline = self._get_baseline() if self._get_baseline else {}
        if isinstance(baseline, (int, float)):
            baseline = {s: int(baseline) for s in self.strategies}
        for sel in self.strategies:
            try:
                start = baseline.get(sel, 0) if isinstance(baseline, dict) else 0
                text = await page.evaluate("""([sel, start]) => {
                    const els = document.querySelectorAll(sel);
                    for (let i = els.length - 1; i >= start; i--) {
                        const t = (els[i].textContent || els[i].innerText || '').trim();
                        if (t.length > 30) return t;
                    }
                    return '';
                }""", [sel, start])
                if text and len(text) > 30:
                    return text
            except Exception:
                continue
        return ""

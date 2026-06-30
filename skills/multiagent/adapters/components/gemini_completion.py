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
    """Wait for Gemini Extended Thinking to finish, then extract response."""

    THINKING_PHASE_CAP_MS = 90_000  # max wait for toolbar after stop button gone

    def __init__(self, stop_selector: str, toolbar_selector: str,
                 thinking_selector: str, response_strategies: list[str],
                 get_baseline=None):
        self.stop_sel = stop_selector
        self.toolbar_sel = toolbar_selector
        self.thinking_sel = thinking_selector
        self.strategies = response_strategies
        self._get_baseline = get_baseline  # callable → int

    async def wait_response(self, page, timeout_ms: int = 600_000) -> str:
        """Extended-Thinking-aware completion detection."""
        start = _time.time()

        # Step 1: Confirm submission (stop button appears)
        try:
            stop_btn = page.locator(self.stop_sel).first
            await stop_btn.wait_for(state="visible", timeout=15_000)
            log.info("[Gemini] Stop button visible — submission confirmed")
        except Exception:
            log.info("[Gemini] Stop button did not appear")

        # Step 2: Wait for stop button to disappear (thinking begins).
        # Do NOT treat this as completion.
        try:
            remaining = max(10_000, timeout_ms - int((_time.time() - start) * 1000))
            await stop_btn.wait_for(state="hidden", timeout=remaining)
            log.info("[Gemini] Stop button hidden — Extended Thinking phase began")
        except Exception:
            log.info("[Gemini] Stop button never hidden or timed out")

        # Step 3: Wait for toolbar as definitive completion anchor.
        # Cap at THINKING_PHASE_CAP_MS — if toolbar doesn't appear, generation
        # is likely stuck server-side.
        toolbar_found = False
        try:
            toolbar = page.locator(self.toolbar_sel).first
            await toolbar.wait_for(state="visible",
                                   timeout=self.THINKING_PHASE_CAP_MS)
            toolbar_found = True
            log.info("[Gemini] Toolbar detected — Extended Thinking complete")
        except Exception:
            log.info("[Gemini] Toolbar timeout after %.0fs — generation likely stuck",
                     self.THINKING_PHASE_CAP_MS / 1000)

        # Step 3.5: If toolbar never appeared, do stability check.
        # Must fit within remaining timeout budget (capped at 15s max to
        # avoid asyncio.wait() cancelling other workers when we overrun).
        if not toolbar_found:
            elapsed = (_time.time() - start) * 1000
            remaining_budget = max(5_000, timeout_ms - int(elapsed))
            max_stability_s = min(15, remaining_budget / 1000)
            poll_interval_s = 2.0
            max_checks = max(2, int(max_stability_s / poll_interval_s))
            log.info("[Gemini] Post-stuck stability check: %.0fs (%d checks)",
                     max_stability_s, max_checks)

            last_len = 0
            stable_checks = 0
            for _ in range(max_checks):
                await asyncio.sleep(poll_interval_s)

                if self.thinking_sel:
                    try:
                        thinking_el = page.locator(self.thinking_sel).first
                        if await thinking_el.is_visible():
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

        # Step 4: Extract final response
        try:
            raw = await self._extract(page)
            log.info("[Gemini] Final extraction: %d chars", len(raw))
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

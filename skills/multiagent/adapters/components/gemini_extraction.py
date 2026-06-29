"""Gemini Response Extractor — prompt-echo filtering + multi-strategy DOM extraction.

Handles Gemini-specific DOM quirks: model-message ordering, thinking-section
visibility, and prompt-echo detection in reused tabs.
"""

import logging

log = logging.getLogger("adapters.gemini.extraction")


class GeminiResponseExtractor:
    """Multi-strategy response extraction with baseline-aware prompt-echo filtering."""

    MAX_RESPONSE_SIZE = 500_000  # 500KB cap

    # Prompt template markers — skip blocks containing these (they're the prompt)
    PROMPT_MARKERS = [
        '请按以下结构输出',
        '请按以下结构输出',
        '你现在是拥有长链条推理能力的终审法官',
        '你现在是拥有长链条推理能力的终审法官',
        '原始问题',
        '原始问题',
        '专家分析矩阵',
        '专家分析矩阵',
    ]

    def __init__(self, response_strategies: list[str], get_baseline=None):
        self.strategies = response_strategies
        self._get_baseline = get_baseline

    async def extract_response(self, page) -> str:
        """Baseline-aware multi-strategy extraction.

        P0 fix (2026-06-30): only extracts elements at index >= baseline,
        preventing user-message extraction in reused tabs.
        """
        baseline = self._get_baseline() if self._get_baseline else 0

        for i, sel in enumerate(self.strategies):
            try:
                text = await page.evaluate("""([sel, baseline]) => {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) return '';
                    for (let i = els.length - 1; i >= baseline; i--) {
                        const t = (els[i].textContent || els[i].innerText || '').trim();
                        if (t.length > 30) return t;
                    }
                    return '';
                }""", [sel, baseline])
                if text and len(text) > 30:
                    if len(text) > self.MAX_RESPONSE_SIZE:
                        log.warning("[Gemini] Response truncated: %d → %d chars",
                                     len(text), self.MAX_RESPONSE_SIZE)
                        text = text[:self.MAX_RESPONSE_SIZE] + "\n[RESPONSE_TRUNCATED]"
                    log.info("[Gemini] Strategy #%d '%s' → %d chars (baseline=%d)",
                             i + 1, sel[:50], len(text), baseline)
                    return text
            except Exception as e:
                log.debug("[Gemini] Strategy #%d failed: %s", i + 1, e)
                continue

        # Ultimate fallback: largest text block that ISN'T the prompt echo
        try:
            text = await page.evaluate("""(markers) => {
                const nodes = document.querySelectorAll(
                    'model-message, [class*="message"], div, article, section'
                );
                let best = '';
                for (let i = nodes.length - 1; i >= 0; i--) {
                    const t = (nodes[i].textContent || nodes[i].innerText || '').trim();
                    if (t.length < 50 || t.length > 200000) continue;
                    let isPrompt = false;
                    for (const m of markers) {
                        if (t.includes(m)) { isPrompt = true; break; }
                    }
                    if (!isPrompt && t.length > best.length) best = t;
                }
                return best;
            }""", self.PROMPT_MARKERS)
            if text and len(text) > 30:
                log.info("[Gemini] Ultimate fallback (filtered): %d chars", len(text))
                return text
        except Exception:
            pass

        log.warning("[Gemini] ALL extraction strategies exhausted — returning empty")
        return ""

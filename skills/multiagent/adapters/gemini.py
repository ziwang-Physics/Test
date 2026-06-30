#!/usr/bin/env python3
"""Gemini adapter — Google Gemini Web.

P2 refactor (2026-06-30): decomposed 648-line monolith into four Protocol-based
components in adapters/components/.  GeminiAdapter now composes them, keeping
the external interface identical so orchestrator.py requires zero changes.

Components:
  gemini_editor.py      — GeminiEditorDriver (clear_input, inject_prompt, trigger_send)
  gemini_completion.py  — GeminiCompletionDetector (wait_response for Extended Thinking)
  gemini_extraction.py  — GeminiResponseExtractor (baseline-aware multi-strategy)
  gemini_mode.py        — GeminiModeController (ensure_pro_extended, ensure_fresh)
"""

from .base import BaseAdapter
from .components import (
    GeminiEditorDriver,
    GeminiCompletionDetector,
    GeminiResponseExtractor,
    GeminiModeController,
)


class GeminiAdapter(BaseAdapter):
    """Google Gemini with Pro Extended Thinking support.

    Composes four replaceable component drivers — swap any component for a
    different platform (e.g. React editor for ChatGPT) without touching the
    rest of the adapter.
    """

    name = "gemini"
    EDITOR_SELECTOR = (
        '.ql-editor, [contenteditable="true"][role="textbox"], rich-textarea'
    )
    SEND_SELECTOR = (
        'button[aria-label*="傳送"], button[aria-label*="发送"], '
        'button[aria-label*="Send"]'
    )
    STOP_SELECTOR = 'button[aria-label*="停止"], button[aria-label*="Stop"]'
    TOOLBAR_SELECTOR = (
        'button[aria-label*="複製"], button[aria-label*="Copy"], '
        'button[aria-label*="Good response"]'
    )
    URL = "https://gemini.google.com/u/0/app"
    RESPONSE_STRATEGIES = [
        "model-response:last-of-type",
        "model-response",
        "model-message:last-of-type",
        "model-message",
        ".model-response-text",
        '.thinking-section[expanded]',
        '[class*="response-content"]',
        '[class*="model-response"]',
    ]
    ERROR_PATTERNS = [
        "Something went wrong",
        "An error occurred",
        "Please try again later",
    ]
    THINKING_SELECTOR = (
        'gemini-thinking-indicator, [class*="thinking-indicator"], '
        'mat-spinner, [class*="spinner"]'
    )
    MODEL_SELECTOR_SEL = (
        'button[aria-label*="Pro"], button[aria-label*="Flash"], '
        'button[aria-label*="Gemini"], '
        'button[aria-label*="模式挑選器"], button[aria-label*="Model selector"], '
        'button[aria-label*="模式选择器"]'
    )

    def __init__(self, cdp_port: str = "9222"):
        super().__init__(cdp_port)
        # Compose component drivers (replaceable per platform)
        self._editor = GeminiEditorDriver(
            editor_selector=self.EDITOR_SELECTOR,
            send_selector=self.SEND_SELECTOR,
        )
        self._mode = GeminiModeController(
            url=self.URL,
            editor_selector=self.EDITOR_SELECTOR,
            model_selector_sel=self.MODEL_SELECTOR_SEL,
        )
        self._completion = GeminiCompletionDetector(
            stop_selector=self.STOP_SELECTOR,
            toolbar_selector=self.TOOLBAR_SELECTOR,
            thinking_selector=self.THINKING_SELECTOR,
            response_strategies=self.RESPONSE_STRATEGIES,
            get_baseline=lambda: getattr(self, '_assistant_baseline', 0),
        )
        self._extraction = GeminiResponseExtractor(
            response_strategies=self.RESPONSE_STRATEGIES,
            get_baseline=lambda: getattr(self, '_assistant_baseline', 0),
        )

    # ── Thinking mode (delegates to ModeController) ─────────────────

    async def ensure_thinking_mode(self, page):
        """Enable Pro Extended Thinking. Returns ModeResult (P0: structured)."""
        from .components.gemini_mode import ModeResult, ThinkingPolicy
        return await self._mode.ensure_thinking_mode(page)

    # ── Editor pipeline (delegates to EditorDriver) ──────────────────

    async def clear_input(self, page) -> None:
        return await self._editor.clear_input(page)

    async def inject_prompt(self, page, text: str) -> None:
        return await self._editor.inject_prompt(page, text)

    async def trigger_send(self, page) -> None:
        return await self._editor.trigger_send(page)

    # ── Conversation lifecycle (delegates to ModeController) ────────

    async def ensure_fresh_conversation(self, page) -> None:
        return await self._mode.ensure_fresh_conversation(page)

    # ── Response pipeline (delegates to CompletionDetector + Extractor) ──

    async def wait_response(self, page, timeout_ms: int = 600_000) -> str:
        return await self._completion.wait_response(page, timeout_ms)

    async def extract_response(self, page) -> str:
        return await self._extraction.extract_response(page)

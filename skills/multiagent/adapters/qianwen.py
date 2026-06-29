#!/usr/bin/env python3
"""Qianwen adapter — Alibaba Tongyi Qianwen (⭐⭐⭐ DOM verified).

DOM-probed 2026-06-27: [class*="message"] containers, "Qwen3.7-Max\\n<answer>"
response format.  Stability improved after selector refinements.

Deep Thinking toggle (2026-06-28):
  - Button: button[aria-label="思考"] with aria-pressed toggle
  - aria-pressed="false" → off, aria-pressed="true" → on
  - Idempotent guard: skip click if already pressed
"""

import asyncio, logging

from .base import BaseAdapter

log = logging.getLogger("adapters.qianwen")

# ── Deep Thinking toggle constants ────────────────────────────────────────
THINK_BTN_SELECTOR = 'button[aria-label="思考"]'
THINK_TOGGLE_WAIT_S  = 2.0              # post-click React state settle time


class QianwenAdapter(BaseAdapter):
    name = "qianwen"
    EDITOR_SELECTOR = (
        'textarea, div[contenteditable="true"], [role="textbox"], '
        '.input-box, .chat-input-area'
    )
    SEND_SELECTOR = (
        'button[aria-label*="发送"], button[aria-label*="Send"], '
        '.send-btn, [class*="submit"]'
    )
    STOP_SELECTOR = (
        'button[aria-label*="停止"], button[aria-label*="Stop"], .stop-btn'
    )
    TOOLBAR_SELECTOR = (
        'button[aria-label*="复制"], button[aria-label*="Copy"], .copy-btn'
    )
    URL = "https://www.qianwen.com/?source=tongyigw"
    RESPONSE_STRATEGIES = [
        # Q2 AI feedback: prefer semantic anchors over CSS classes
        '[class*="bot"] [class*="answer"]:last-of-type',
        '[class*="message"][class*="bot"]:last-of-type',
        '[class*="message"]:last-of-type',
        '[class*="chat-message"]:last-child [class*="content"]',
        '[class*="answer-content"]',
        '[class*="message"]',
        '[class*="chat-message"]:last-child',
    ]
    THINKING_SELECTOR = (
        'button[aria-label*="停止"], .stop-btn, '
        '[class*="think-loader"], [class*="generating"], '
        '[class*="deep-thinking"]'
    )

    # ── Deep Thinking toggle (DISABLED by user request) ──────────────────

    async def ensure_thinking_mode(self, page) -> bool:
        """No-op — user prefers Qianwen without Deep Thinking for speed.

        The aria-pressed toggle is deliberately NOT clicked.  Raw Qwen3.7-Max
        responses are faster and still high quality for the security/defense
        lens this worker provides.
        """
        return True

#!/usr/bin/env python3
"""Kimi adapter — Moonshot AI Kimi (⭐⭐⭐ DOM verified).

DOM-probed 2026-06-27: React SPA, chat-content-item messages,
chat-content-list conversation area.  Needs first field test.
"""

from .base import BaseAdapter


class KimiAdapter(BaseAdapter):
    name = "Kimi"
    EDITOR_SELECTOR = (
        'div[contenteditable="true"], textarea, [role="textbox"], .editor-content'
    )
    SEND_SELECTOR = (
        'button[aria-label*="发送"], button[aria-label*="Send"], '
        'button[type="submit"], .send-btn'
    )
    STOP_SELECTOR = (
        'button[aria-label*="停止"], button[aria-label*="Stop"], .stop-btn'
    )
    TOOLBAR_SELECTOR = (
        'button[aria-label*="复制"], button[aria-label*="Copy"], .copy-btn'
    )
    URL = "https://www.kimi.com/"
    RESPONSE_STRATEGIES = [
        # P1 fix (2026-06-29): added selectors targeting the final answer
        # portion vs the thinking-process wrapper.  Kimi renders thinking
        # traces in a collapsible section; the final answer is in .answer-content
        # or the last .markdown block inside the chat item.
        'div.chat-content-item:last-of-type [class*="answer"]',
        'div.chat-content-item:last-of-type [class*="markdown"]',
        'div.chat-content-item:last-of-type',
        'div.chat-content-list [class*="answer"]',
        'div.chat-detail-content [class*="markdown"]',
        'div.chat-content-list',
        'div.chat-detail-content',
        'div.main',
    ]
    # During generation Kimi shows typing dots / loading indicator.
    # Stability fallback checks this — if still visible, the real answer
    # hasn't arrived yet and we must keep waiting.
    THINKING_SELECTOR = (
        '[class*="typing"], [class*="loading-indicator"], '
        '[class*="stop-generate"], [class*="thinking"], '
        '[class*="dot"]'
    )

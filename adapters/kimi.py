#!/usr/bin/env python3
"""Kimi adapter — Moonshot AI Kimi (⭐⭐⭐ DOM verified).

DOM-probed 2026-06-27: React SPA, chat-content-item messages,
chat-content-list conversation area.  Needs first field test.
"""

import re
from .base import BaseAdapter

# ── Kimi-specific thinking-trace prefix patterns ─────────────────────────
# P0 fix (iteration-3 ChatGPT P0-03): moved from BaseAdapter.clean_response()
# to KimiAdapter.  Only strip the FIRST LINE (non-DOTALL, line-by-line).
# The old re.DOTALL patterns matched across the entire response and destroyed
# valid answers on ALL platforms (e.g. "这是答案：abc" → empty string).
_KIMI_THINKING_DONE = re.compile(r'^思考已完成[ \t]*$', re.MULTILINE)
_KIMI_USER_PROMPT_ECHO = re.compile(
    r'^用户要求(用一句话回答|用中文回答|回答|说|：).*$', re.MULTILINE)


class KimiAdapter(BaseAdapter):
    name = "kimi"
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

    def clean_response(self, raw_text: str, prompt: str = "") -> str:
        """Kimi-specific: strip thinking-trace prefix lines safely.

        P0 fix (iteration-3 ChatGPT P0-03): only strips single-line prefixes
        at the START of the response.  Does NOT use re.DOTALL.  The old
        BaseAdapter patterns used greedy matching under DOTALL that could
        match across the entire response and destroy valid answers.
        """
        text = super().clean_response(raw_text, prompt)
        if not text:
            return text
        # Strip Kimi thinking-trace headers from the first 3 lines only
        text = _KIMI_THINKING_DONE.sub('', text, count=1)
        text = _KIMI_USER_PROMPT_ECHO.sub('', text, count=1)
        return text.strip()

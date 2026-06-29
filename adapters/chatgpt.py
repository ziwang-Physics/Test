#!/usr/bin/env python3
"""ChatGPT adapter — OpenAI ChatGPT (⭐⭐⭐⭐ Tested).

Q2 AI feedback (2026-06-29): data-testid attributes are OpenAI's most stable
anchors — they survive React re-renders and A/B tests.  CSS classes like
'markdown' and 'prose' are secondary fallbacks.
"""

from .base import BaseAdapter


class ChatGPTAdapter(BaseAdapter):
    name = "chatgpt"
    EDITOR_SELECTOR = (
        '#prompt-textarea, div[contenteditable="true"], [data-id="root"]'
    )
    SEND_SELECTOR = 'button[data-testid="send-button"], button[aria-label*="Send"]'
    STOP_SELECTOR = 'button[data-testid="stop-button"], button[aria-label*="Stop"]'
    TOOLBAR_SELECTOR = (
        'button[data-testid="copy-turn-action-button"], button[aria-label*="Copy"]'
    )
    URL = "https://chatgpt.com/"
    RESPONSE_STRATEGIES = [
        # Q2: data-testid anchors first (most stable across DOM changes)
        '[data-testid*="conversation-turn"]:last-of-type [data-message-author-role="assistant"]',
        '[data-message-author-role="assistant"]:last-of-type [class*="markdown"]',
        '[data-testid*="conversation-turn"]:last-of-type',
        # Fallback: article-based selectors
        'article[data-testid*="turn"]:last-of-type [class*="markdown"]',
        'article:last-of-type [class*="markdown"]',
        # Legacy (may return after OpenAI DOM rollback)
        '[data-message-author-role="assistant"]',
        '.message-group:last-child .content',
        '[class*="assistant"] [class*="prose"]',
    ]

#!/usr/bin/env python3
"""MiniMax Agent browser adapter."""

from .base import BaseAdapter


class MiniMaxAdapter(BaseAdapter):
    """Adapter for the MiniMax Agent web chat (agent.minimax.io)."""

    name = "minimax"
    EDITOR_SELECTOR = (
        'textarea, div[contenteditable="true"], [role="textbox"]'
    )
    SEND_SELECTOR = (
        'button[aria-label*="发送"], button[aria-label*="Send"]'
    )
    STOP_SELECTOR = (
        'button[aria-label*="停止"], button[aria-label*="Stop"]'
    )
    TOOLBAR_SELECTOR = (
        'button[aria-label*="复制"], button[aria-label*="Copy"]'
    )
    URL = "https://agent.minimax.io/"
    RESPONSE_STRATEGIES = [
        '[class*="assistant"]',
        '[class*="message"]:last-of-type',
        '[class*="markdown"]',
        '[class*="content"]',
    ]

#!/usr/bin/env python3
"""Doubao browser adapter — active (moved from _deprecated)."""

from .base import BaseAdapter


class DoubaoAdapter(BaseAdapter):
    """Adapter for the Doubao web chat (www.doubao.com/chat/)."""

    name = "doubao"
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
    URL = "https://www.doubao.com/chat/"
    RESPONSE_STRATEGIES = [
        '[class*="assistant"]',
        '[class*="message"]:last-of-type',
        '[class*="markdown"]',
        '[class*="content"]',
    ]

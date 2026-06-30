#!/usr/bin/env python3
"""
MultiAgent platform adapters package.

Backward-compatible: ``from adapters import GeminiAdapter`` still works.
Also provides the registry and maturity metadata for dynamic dispatch.

Exports:
    BaseAdapter        — abstract base class
    GeminiAdapter      — Google Gemini (P4 adjudicator)
    ChatGPTAdapter     — OpenAI ChatGPT (P2 code/performance expert)
    ClaudeAdapter      — Anthropic Claude (P2 defensive architecture expert)
    KimiAdapter        — Moonshot Kimi (P2 literature/benchmark expert)
    QianwenAdapter     — Alibaba Qianwen (P2 security audit expert)
    DeepSeekAdapter    — DeepSeek Chat (optional, with Expert + Deep Think)
    DoubaoAdapter      — (deprecated, manual opt-in only)
    ADAPTER_REGISTRY   — dict[name, AdapterClass]
    PLATFORM_MATURITY  — dict[name, maturity_string]
"""

from .base import BaseAdapter
from .gemini import GeminiAdapter
from .chatgpt import ChatGPTAdapter
from .claude import ClaudeAdapter
from .kimi import KimiAdapter
from .qianwen import QianwenAdapter
from .deepseek import DeepSeekAdapter
from .minimax import MiniMaxAdapter
from .doubao import DoubaoAdapter

# Backward compat: also available via ._deprecated
from ._deprecated import DoubaoAdapter as _DoubaoDeprecated

ADAPTER_REGISTRY = {
    "gemini":    GeminiAdapter,
    "chatgpt":   ChatGPTAdapter,
    "claude":    ClaudeAdapter,
    "kimi":      KimiAdapter,
    "qianwen":   QianwenAdapter,
    "deepseek":  DeepSeekAdapter,
    "minimax":   MiniMaxAdapter,
    "doubao":    DoubaoAdapter,
}

PLATFORM_MATURITY = {
    "gemini":    "active",
    "chatgpt":   "active",
    "claude":    "active",
    "kimi":      "active",
    "qianwen":   "active",
    "deepseek":  "active",
    "minimax":   "active-unverified",
    "doubao":    "active-unverified",
}

__all__ = [
    "BaseAdapter",
    "GeminiAdapter", "ChatGPTAdapter", "ClaudeAdapter",
    "KimiAdapter", "QianwenAdapter", "DeepSeekAdapter",
    "MiniMaxAdapter", "DoubaoAdapter",
    "ADAPTER_REGISTRY", "PLATFORM_MATURITY",
]

"""Platform adapter components — replaceable driver modules.

P2 refactor (2026-06-30): extracted from GeminiAdapter's 648-line monolith
into four Protocol-based components.  Each component can be swapped per
platform (e.g. Angular CDK editor for Gemini, React/ProseMirror for ChatGPT)
without touching the rest of the adapter.
"""

from .protocols import (
    EditorDriver,
    CompletionDetector,
    ResponseExtractor,
    ModeController,
)
from .gemini_editor import GeminiEditorDriver
from .gemini_completion import GeminiCompletionDetector
from .gemini_extraction import GeminiResponseExtractor
from .gemini_mode import GeminiModeController

__all__ = [
    "EditorDriver",
    "CompletionDetector",
    "ResponseExtractor",
    "ModeController",
    "GeminiEditorDriver",
    "GeminiCompletionDetector",
    "GeminiResponseExtractor",
    "GeminiModeController",
]

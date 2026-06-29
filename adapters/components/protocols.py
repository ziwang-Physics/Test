"""Protocol definitions for adapter components (PEP 544 structural subtyping).

Each Protocol defines a single responsibility.  Platform adapters compose them;
no explicit inheritance required — any object implementing the interface works.

Design rationale (2026-06-30, 3-platform AI review consensus):
  - EditorDriver: prompt injection + send (platform-specific rich-text editor)
  - CompletionDetector: wait for generation to finish (stop button, toolbar, stability)
  - ResponseExtractor: multi-strategy DOM extraction + cleaning
  - ModeController: deep-thinking / reasoning mode toggle (Extended Thinking, etc.)

These replace GeminiAdapter's 648-line monolith.  ChatGPT would use a
React/ProseMirror EditorDriver; Gemini uses Angular CDK.
"""

from typing import Awaitable, Protocol


class EditorDriver(Protocol):
    """Inject prompt and trigger send on a platform's editor.

    Implementations handle platform-specific quirks:
      - Gemini: Angular CDK rich-textarea, clipboard paste, dispatchEvent('input')
      - ChatGPT: ProseMirror [contenteditable], keyboard.type
      - Qianwen: standard textarea, keyboard.insert_text
    """

    async def clear_input(self, page) -> None:
        """Clear the editor before injecting a new prompt."""
        ...

    async def inject_prompt(self, page, text: str) -> None:
        """Type/paste prompt text into the editor, with integrity verification."""
        ...

    async def trigger_send(self, page) -> None:
        """Click send button or press Enter, with pre-flight button-enabled check."""
        ...


class CompletionDetector(Protocol):
    """Wait for the platform's generation to complete, then return response text.

    Handles platform-specific generation lifecycle:
      - Standard: stop-button appear → disappear → extract
      - Extended Thinking: stop → thinking (30-300s) → toolbar → extract
    """

    async def wait_response(self, page, timeout_ms: int = 300_000) -> str:
        """Block until generation finishes, return extracted response text."""
        ...


class ResponseExtractor(Protocol):
    """Extract and clean the model's response from DOM.

    Multi-strategy: tries platform-specific selectors first, falls back to
    largest-text-block scanning with prompt-echo filtering.
    """

    async def extract_response(self, page) -> str:
        """Extract the latest assistant response from DOM."""
        ...

    def clean_response(self, raw_text: str, prompt: str = "") -> str:
        """Strip prompt echo, UI chrome, navigation labels."""
        ...


class ModeController(Protocol):
    """Enable/verify the platform's deep-thinking / reasoning mode.

    Gemini: multi-step Angular CDK menu (Pro → 思考程度 → 延長)
    Qianwen: single aria-pressed toggle (思考 button)
    Others: no-op (returns True)
    """

    async def ensure_thinking_mode(self, page) -> bool:
        """Enable deep-thinking mode.  Idempotent — skips if already active."""
        ...

    async def ensure_fresh_conversation(self, page) -> None:
        """Start a new conversation to avoid history bleeding."""
        ...

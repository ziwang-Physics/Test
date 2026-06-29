"""Gemini Editor Driver — Angular CDK rich-textarea injection.

Handles Gemini's <rich-textarea> custom element which rejects standard
editor.fill("") and requires clipboard paste + dispatchEvent('input')
to trigger Angular zone.js change detection.
"""

import asyncio, logging

log = logging.getLogger("adapters.gemini.editor")


class GeminiEditorDriver:
    """Prompt injection + send for Gemini's Angular CDK editor."""

    def __init__(self, editor_selector: str, send_selector: str = ""):
        self.editor_sel = editor_selector
        self.send_sel = send_selector or (
            'button[aria-label*="Send"], button[aria-label*="发送"], '
            'button[aria-label*="傳送"]'
        )

    async def clear_input(self, page) -> None:
        """Gemini-specific clear: rich-textarea rejects fill(""), must use keyboard.

        Triple-click (click_count=3) selects all text inside the rich-textarea.
        Playwright's click() with clickCount triggers native selection behavior
        that Angular CDK doesn't intercept.
        """
        editor = page.locator(self.editor_sel).first
        await editor.focus()
        await asyncio.sleep(0.2)

        # Triple-click to select all text
        await editor.click(click_count=3)
        await asyncio.sleep(0.15)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.3)

        # Verify — if still not empty, use Escape then retry
        remaining = await editor.evaluate(
            "el => (el.textContent || el.innerText || '').trim().length"
        )
        if remaining > 5:
            log.warning("[Gemini] Editor not cleared after triple-click (%d chars) — "
                        "using Escape + retry", remaining)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            await editor.focus()
            await asyncio.sleep(0.2)
            await editor.click(click_count=3)
            await asyncio.sleep(0.15)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            remaining = await editor.evaluate(
                "el => (el.textContent || el.innerText || '').trim().length"
            )
            if remaining > 5:
                log.warning("[Gemini] Editor STILL not empty (%d chars) — "
                            "reloading page", remaining)
                # Caller must pass URL on page object
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(3_000)
        else:
            log.info("[Gemini] Editor cleared")

    async def inject_prompt(self, page, text: str) -> None:
        """Inject via clipboard paste + dispatchEvent('input') for Angular CDK.

        P0 fix (iteration-3 ChatGPT P0-04): NO LONGER replaces \\n with spaces.
        Clipboard paste preserves newlines without triggering Enter-submit in
        Gemini's rich-textarea.  The old newline-stripping destroyed markdown
        structure, code blocks, YAML/JSON examples, and multi-paragraph prompts.
        """
        editor = page.locator(self.editor_sel).first
        await editor.focus()
        await editor.click()
        await asyncio.sleep(0.2)

        # Strategy 1: clipboard paste (fast + reliable, preserves \\n)
        try:
            await page.evaluate("(t) => navigator.clipboard.writeText(t)", text)
            await page.keyboard.press("ControlOrMeta+v")
            await page.wait_for_timeout(300)
            # Force Angular change detection on the SPECIFIC locator element
            try:
                await editor.evaluate(
                    "el => el.dispatchEvent(new Event('input', {bubbles: true}))"
                )
            except Exception:
                pass
            await page.wait_for_timeout(300)
        except Exception:
            log.warning("[Gemini] Clipboard paste failed, trying CDP insertText")
            try:
                await page.evaluate(
                    "(t) => { document.execCommand('insertText', false, t); }",
                    text,
                )
                await page.wait_for_timeout(300)
            except Exception:
                # Last resort: keyboard.type (may break on newlines)
                await page.keyboard.type(text, delay=5)
                await asyncio.sleep(0.3)

        # Pre-submit verification using content fingerprint (hash-based)
        import hashlib, unicodedata
        for attempt in range(3):
            injected = await editor.evaluate(
                "el => (el.textContent || el.innerText || '').trim()"
            )
            if not injected:
                log.warning("[Gemini] Inject empty (attempt %d) — retrying", attempt + 1)
                await self._retry_inject(page, editor, text)
                continue

            # Content fingerprint comparison (not just length diff)
            norm_expected = unicodedata.normalize("NFC", text).replace("\r\n", "\n").strip()
            norm_actual = unicodedata.normalize("NFC", injected).replace("\r\n", "\n").strip()
            if hashlib.blake2s(norm_actual.encode()).digest() == \
               hashlib.blake2s(norm_expected.encode()).digest():
                log.info("[Gemini] Inject verified: %d chars (attempt %d, hash match)",
                         len(injected), attempt + 1)
                return

            # Fallback: length-based check (for platforms that normalize whitespace)
            len_ratio = len(norm_actual) / max(len(norm_expected), 1)
            if 0.85 <= len_ratio <= 1.15:
                log.info("[Gemini] Inject verified: %d vs %d chars (attempt %d, length match)",
                         len(injected), len(text), attempt + 1)
                return

            log.warning("[Gemini] Inject mismatch (attempt %d): expected %d, got %d chars",
                        attempt + 1, len(text), len(injected))
            await self._retry_inject(page, editor, text)

        raise RuntimeError(
            f"PROMPT_INJECTION_FAILED: Gemini editor injection unverified "
            f"after 3 attempts (expected {len(text)} chars)"
        )

    async def _retry_inject(self, page, editor, text: str) -> None:
        """Clear editor and retry injection."""
        import hashlib, unicodedata
        await editor.focus()
        await editor.click(click_count=3)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.3)
        try:
            await page.evaluate("(t) => navigator.clipboard.writeText(t)", text)
            await page.keyboard.press("ControlOrMeta+v")
            await page.wait_for_timeout(300)
            try:
                await editor.evaluate(
                    "el => el.dispatchEvent(new Event('input', {bubbles: true}))"
                )
            except Exception:
                pass
        except Exception:
            pass

    async def trigger_send(self, page) -> None:
        """Submit via Enter key after Angular CDK has processed the injection.

        P0 fix (iteration-3 ChatGPT): uses Playwright is_enabled() instead of
        manual disabled attribute parsing.  HTML boolean disabled attributes can
        return empty string, which the old code (a or b) treated as falsy,
        allowing clicks on disabled buttons.

        Also uses editor.press("Enter") instead of page.keyboard.press("Enter")
        to ensure the key event targets the correct element.
        """
        editor = page.locator(self.editor_sel).first

        # Wait for Angular CDK to process injection (send button becomes enabled)
        for _ in range(20):
            try:
                btn = page.locator(self.send_sel).first
                if await btn.is_visible():
                    if await btn.is_enabled():
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        # Method 1: Enter key on the editor element (primary — most native)
        try:
            await editor.focus()
            await asyncio.sleep(0.15)
            await editor.press("Enter")
            log.info("[Gemini] Sent via editor.press('Enter')")
            return
        except Exception as e:
            log.debug("[Gemini] Enter send via editor failed: %s — trying button", e)

        # Method 2: Button click with Playwright actionability checks
        try:
            btn = page.locator(self.send_sel).first
            await btn.click(timeout=5000)
            log.info("[Gemini] Sent via button click")
            return
        except Exception:
            pass

        raise RuntimeError("[Gemini] ALL send methods failed")

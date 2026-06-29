#!/usr/bin/env python3
"""Gemini adapter — Google Gemini (⭐⭐⭐⭐⭐ Verified).

Pro Extended Thinking switch (v3 robust — Angular CDK overlay polling),
fresh-conversation detection, model-message extraction.
The most battle-tested adapter in the pipeline.

Key fixes applied 2026-06-28:
  - ensure_pro_extended() rewritten with gem-menu-item selectors and
    wait_for_menu_items_filled() polling (fixes Angular CDK rendering delay)
  - Idempotent guard uses aria-label attribute (not textContent)
  - Uses .selected CSS class + offsetParent visibility check
"""

import asyncio, logging, time

from .base import BaseAdapter

log = logging.getLogger("adapters.gemini")

# ── Angular CDK menu rendering timeout ────────────────────────────────────
MENU_RENDER_TIMEOUT_MS = 5000       # max wait for gem-menu-item innerText
MENU_POLL_INTERVAL_S   = 0.2        # poll every 200ms
SUBMENU_ANIMATION_S    = 2.0        # Angular CDK slide-in animation


class GeminiAdapter(BaseAdapter):
    name = "Gemini"
    EDITOR_SELECTOR = (
        '.ql-editor, [contenteditable="true"][role="textbox"], rich-textarea'
    )
    SEND_SELECTOR = (
        'button[aria-label*="傳送"], button[aria-label*="发送"], '
        'button[aria-label*="Send"]'
    )
    STOP_SELECTOR = 'button[aria-label*="停止"], button[aria-label*="Stop"]'
    TOOLBAR_SELECTOR = (
        'button[aria-label*="複製"], button[aria-label*="Copy"], '
        'button[aria-label*="Good response"]'
    )
    URL = "https://gemini.google.com/u/0/app"
    # Extended Thinking uses different DOM wrappers than normal Gemini.
    # Strategy order: specific → generic.  model-response is the canonical
    # element for the final answer (DOM-probed 2026-06-29).  thinking-section
    # captures the collapsed thinking toggle.
    RESPONSE_STRATEGIES = [
        "model-response:last-of-type",               # Final answer (ET mode) ✅ verified
        "model-response",                             # All responses (normal mode)
        "model-message:last-of-type",                 # Legacy wrapper
        "model-message",                              # All messages
        ".model-response-text",                       # Legacy wrapper
        '.thinking-section[expanded]',                # ET thinking expanded
        '[class*="response-content"]',               # Generic fallback
        '[class*="model-response"]',                 # Generic fallback
    ]
    ERROR_PATTERNS = [
        # Only true error/rate-limit signals — NOT conversation chrome.
        # "和 Gemini 的對話" and "Gemini 是 AI..." are cleaned by NOISE_MARKERS.
        "Something went wrong",
        "An error occurred",
        "Please try again later",
    ]

    # During Extended Thinking the stop button disappears but the model
    # is still reasoning.  The toolbar won't appear until thinking finishes.
    THINKING_SELECTOR = (
        'gemini-thinking-indicator, [class*="thinking-indicator"], '
        'mat-spinner, [class*="spinner"]'
    )

    # Model selector button — MUST exclude fullscreen-toggle ("全螢幕輸入模式").
    # The aria-label for the model picker contains the CURRENT model name
    # (e.g. "Pro延長" or "Flash"), NOT the word "模式" alone.
    MODEL_SELECTOR_SEL = (
        'button[aria-label*="Pro"], button[aria-label*="Flash"], '
        'button[aria-label*="Gemini"]'
    )

    # ── Thinking mode hook (delegates to ensure_pro_extended) ─────────────

    async def ensure_thinking_mode(self, page) -> bool:
        """Override BaseAdapter no-op → enable Pro Extended Thinking.

        Called by orchestrator P2 _p2_worker for ALL platforms.  Gemini is the
        only platform where the thinking toggle is a complex multi-step Angular
        CDK menu interaction (not a simple aria-pressed toggle).
        """
        try:
            return await self.ensure_pro_extended(page)
        except Exception as e:
            log.warning("[Gemini] ensure_thinking_mode failed: %s", e)
            return False

    # ── Send (P1 fix 2026-06-29: Enter-primary + post-send verification) ──

    async def clear_input(self, page) -> None:
        """Gemini-specific clear: rich-textarea rejects fill(""), must use keyboard.

        BaseAdapter.clear_input() tries editor.fill("") first which throws on
        Gemini's <rich-textarea> custom element.  The exception fallback
        (Ctrl+A + Backspace) is unreliable because Angular CDK may intercept
        the keyboard shortcuts during a digest cycle.

        This override uses triple-tap (click×3 → select all) + Backspace with
        a post-clear verification to guarantee the editor is empty.
        """
        editor = page.locator(self.EDITOR_SELECTOR).first
        await editor.focus()
        await asyncio.sleep(0.2)

        # Triple-click to select all text inside the rich-textarea.
        # Playwright's click() with clickCount=3 triggers the native selection
        # behavior that Angular CDK doesn't intercept.
        await editor.click(click_count=3)
        await asyncio.sleep(0.15)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.3)

        # Verify — if still not empty, use Escape then try again
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
                await page.goto(self.URL, wait_until="domcontentloaded",
                                timeout=15_000)
                await page.wait_for_timeout(3_000)
        else:
            log.info("[Gemini] Editor cleared")

    async def inject_prompt(self, page, text: str) -> None:
        """Gemini-specific prompt injection using keyboard.type() with delay.

        BaseAdapter.inject_prompt() uses keyboard.insert_text() which pastes
        all text at once WITHOUT triggering Angular change detection on the
        rich-textarea component.  The text lands in the DOM but Angular never
        sees it → send button stays hidden → trigger_send() click fails silently.

        keyboard.type() with delay=8ms fires keydown/keypress/keyup for every
        character, which Angular CDK hooks into, reliably showing the send button.
        """
        editor = page.locator(self.EDITOR_SELECTOR).first
        await editor.focus()
        await editor.click()
        await asyncio.sleep(0.2)

        # keyboard.type() with small delay triggers per-char Angular events.
        # For long prompts (>1000 chars) this is slow but reliable.
        # For very long prompts, use clipboard paste as fallback (which Gemini
        # handles correctly via its own paste handler).
        if len(text) > 1000:
            log.info("[Gemini] Large prompt (%d chars) — clipboard paste + wake",
                     len(text))
            try:
                await page.evaluate("(t) => navigator.clipboard.writeText(t)", text)
            except Exception:
                log.warning("[Gemini] Clipboard write failed, falling back to type")
                await page.keyboard.type(text, delay=8)
                await asyncio.sleep(0.3)
                log.info("[Gemini] Prompt typed (%d chars)", len(text))
                return
            await page.keyboard.press("ControlOrMeta+v")
            await page.wait_for_timeout(500)
            # Wake: type+delete a character to trigger Angular change detection
            # (needed after paste because paste events may not fire input events)
            try:
                await page.keyboard.type(".")
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(200)
            except Exception:
                pass
        else:
            await page.keyboard.type(text, delay=8)
            await asyncio.sleep(0.5)

        # Integrity check
        injected = await editor.evaluate(
            "el => (el.textContent || el.innerText || '').trim().length"
        )
        delta_pct = abs(injected - len(text)) / max(len(text), 1)
        if delta_pct > 0.15:
            log.warning("[Gemini] Payload mismatch: expected ~%d, got %d (%.1f%%)",
                        len(text), injected, delta_pct * 100)

        log.info("[Gemini] Prompt injected (%d chars)", len(text))

    async def trigger_send(self, page) -> None:
        """Gemini-specific send: Enter key primary, button click fallback.

        On reused tabs the send button click can silently fail (Angular CDK
        change detection on the Quill editor doesn't always register the
        button event as a submission).  Enter key is more reliable for
        rich-textarea because it triggers the native Quill keyboard handler.

        Post-send verification: after sending, the editor should be empty
        or a stop button should appear.  If neither, retry with Enter.
        """
        # ── Method 1: Enter key (primary — most reliable for Quill) ──
        # P1 fix (2026-06-29): increased pre-Enter delay from 0.15s → 0.5s.
        # After keyboard.type() finishes, Angular CDK zone.js change detection
        # may still be processing the last keystrokes.  If Enter arrives during
        # a digest cycle, it's swallowed silently → editor stays filled.
        # 0.5s gives zone.js enough headroom to flush the microtask queue.
        try:
            editor = page.locator(self.EDITOR_SELECTOR).first
            await editor.focus()
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            log.info("[Gemini] Sent via Enter key")
        except Exception:
            log.warning("[Gemini] Enter send failed, trying button")
            try:
                send_btn = page.locator(self.SEND_SELECTOR).first
                await send_btn.wait_for(state="visible", timeout=3_000)
                await send_btn.click()
                log.info("[Gemini] Sent via button (Enter fallback)")
            except Exception:
                log.warning("[Gemini] Both Enter and button send failed")

        # ── Post-send verification ──
        await asyncio.sleep(1.5)
        editor_cleared = False
        try:
            editor = page.locator(self.EDITOR_SELECTOR).first
            remaining = await editor.evaluate(
                "el => (el.textContent || el.innerText || '').trim().length"
            )
            if remaining < 20:
                log.info("[Gemini] Send verified — editor cleared")
                editor_cleared = True
                return
        except Exception:
            remaining = -1

        if not editor_cleared:
            # Editor still has text — likely wasn't sent.  Retry once with Enter.
            log.warning("[Gemini] Editor not cleared (%d chars remain) — retrying Enter",
                        remaining)
            try:
                editor = page.locator(self.EDITOR_SELECTOR).first
                await editor.focus()
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1.5)
                log.info("[Gemini] Retry Enter sent")
            except Exception as e:
                log.error("[Gemini] Retry Enter failed: %s", e)

    # ── Fresh conversation ────────────────────────────────────────────────

    async def ensure_fresh_conversation(self, page) -> None:
        """Start a new conversation to avoid old history bleeding."""
        msg_count = await page.evaluate(
            "() => document.querySelectorAll('model-message').length"
        )
        if msg_count == 0:
            return

        log.info("[Gemini] %d existing messages — starting fresh conversation",
                 msg_count)
        try:
            new_chat = page.locator(
                'a[aria-label*="新對話"], a[aria-label*="New chat"], '
                'button[aria-label*="新對話"], button[aria-label*="New chat"]'
            ).first
            await new_chat.wait_for(state="visible", timeout=5000)
            await new_chat.click()
            await page.wait_for_timeout(3000)
            new_count = await page.evaluate(
                "() => document.querySelectorAll('model-message').length"
            )
            if new_count == 0:
                log.info("[Gemini] Fresh conversation started via sidebar button")
                try:
                    await page.mouse.click(400, 400)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                return
        except Exception as e:
            log.warning("[Gemini] New chat button not found: %s", e)

        log.info("[Gemini] Falling back to base URL navigation")
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        try:
            await page.mouse.click(400, 400)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

    # ── Pro Extended Thinking (v3 robust — 2026-06-28) ────────────────────

    async def _wait_for_menu_items_filled(self, page,
                                          timeout_ms: int = MENU_RENDER_TIMEOUT_MS
                                          ) -> bool:
        """Poll until ≥2 gem-menu-item elements have non-empty innerText.

        Angular CDK overlay renders gem-menu-item elements immediately into the
        DOM, but zone.js change-detection populates innerText 200-500ms later.
        Without this poll, all text-based filters fail silently.
        """
        t0 = time.time()
        while (time.time() - t0) * 1000 < timeout_ms:
            count = await page.evaluate("""() => {
                return [...document.querySelectorAll('gem-menu-item')]
                    .filter(el => (el.innerText || '').trim().length > 0)
                    .length;
            }""")
            if count >= 2:
                return True
            await asyncio.sleep(MENU_POLL_INTERVAL_S)
        return False

    async def _get_menu_items(self, page) -> list[dict]:
        """Return all visible gem-menu-item elements with text and metadata.

        Uses textContent (P1) — avoids forced reflow.  Visibility is determined
        by offsetParent !== null, not innerText length, so we don't lose the
        hidden-element filter by switching away from innerText.
        """
        return await page.evaluate("""() => {
            return [...document.querySelectorAll('gem-menu-item')]
                .map((el, i) => ({
                    i: i,
                    text: (el.textContent || el.innerText || '').trim(),
                    visible: el.offsetParent !== null,
                    selected: el.classList.contains('selected'),
                }));
        }""")

    async def ensure_pro_extended(self, page) -> bool:
        """Switch to Pro Extended Thinking.  Idempotent — skips if already active.

        Uses the v3 robust pattern (2026-06-28) validated against the
        gemini-web-extended-thinking skill:
          1. Aria-label idempotent guard (not textContent — avoids empty state)
          2. Angular CDK overlay polling (wait_for_menu_items_filled)
          3. gem-menu-item selectors (not [role="menuitem"])
          4. .selected class + offsetParent visibility check

        Returns True on success, False if any step fails (non-fatal).
        """
        # ── Step 1: Idempotent guard via aria-label ──
        try:
            btn = page.locator(self.MODEL_SELECTOR_SEL).first
            await btn.wait_for(state="visible", timeout=5000)
            aria = await btn.get_attribute("aria-label") or ""
            if "延長" in aria or "Extended" in aria:
                log.info("[Gemini] Pro Extended already active (aria-label guard)")
                return True
        except Exception:
            log.warning("[Gemini] Cannot read model selector aria-label")

        # ── Step 2: Open model selector + wait for Angular CDK render ──
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            btn = page.locator(self.MODEL_SELECTOR_SEL).first
            await btn.click()
        except Exception:
            log.warning("[Gemini] Cannot open model selector")
            return False

        if not await self._wait_for_menu_items_filled(page):
            log.warning("[Gemini] Menu items never rendered (Angular CDK delay)")
            return False

        # ── Step 3: Ensure Pro model is selected ──
        items = await self._get_menu_items(page)
        pro_selected = any(
            it["selected"] and ("Pro" in it["text"]) and ("Flash" not in it["text"])
            for it in items
        )

        if not pro_selected:
            # Find and click the Pro menu item
            for it in items:
                if "Pro" in it["text"] and "Flash" not in it["text"] and it["visible"]:
                    try:
                        await page.locator("gem-menu-item").nth(it["i"]).click()
                        await asyncio.sleep(1.5)
                        # Re-open menu (selection may have closed it)
                        btn = page.locator(self.MODEL_SELECTOR_SEL).first
                        await btn.click()
                        if not await self._wait_for_menu_items_filled(page):
                            log.warning("[Gemini] Menu not re-rendered after Pro select")
                            return False
                        log.info("[Gemini] Switched to Pro model")
                    except Exception as e:
                        log.warning("[Gemini] Pro selection click failed: %s", e)
                    break
            else:
                log.warning("[Gemini] Pro menu item not found in: %s",
                           [it["text"] for it in items if it["text"]])

        # ── Step 4: Click "思考程度" (Thinking level) to expand submenu ──
        items = await self._get_menu_items(page)
        thinking_clicked = False
        for it in items:
            if ("思考程度" in it["text"] or "Thinking" in it["text"]) and it["visible"]:
                try:
                    await page.locator("gem-menu-item").nth(it["i"]).click()
                    await asyncio.sleep(SUBMENU_ANIMATION_S)
                    thinking_clicked = True
                    log.info("[Gemini] Expanded thinking level submenu")
                except Exception as e:
                    log.warning("[Gemini] Thinking level click failed: %s", e)
                break

        if not thinking_clicked:
            log.warning("[Gemini] '思考程度' menu item not found")
            return False

        # ── Step 5: Select "延長" (Extended) from submenu ──
        if not await self._wait_for_menu_items_filled(page):
            log.warning("[Gemini] Submenu items never rendered")
            return False

        items = await self._get_menu_items(page)
        for it in items:
            if ("延長" in it["text"]
                    and "標準" not in it["text"]
                    and it["visible"]):
                try:
                    await page.locator("gem-menu-item").nth(it["i"]).click()
                    await asyncio.sleep(1.0)
                    log.info("[Gemini] Selected Extended thinking")
                except Exception as e:
                    log.warning("[Gemini] Extended click failed: %s", e)
                    return False
                break
        else:
            log.warning("[Gemini] '延長' menu item not found in: %s",
                       [it["text"] for it in items if it["text"] and it["visible"]])
            return False

        # ── Step 6: Close menu + verify via aria-label ──
        await page.keyboard.press("Escape")
        await asyncio.sleep(1.0)

        try:
            btn = page.locator(self.MODEL_SELECTOR_SEL).first
            aria = await btn.get_attribute("aria-label") or ""
            if "延長" in aria or "Extended" in aria:
                log.info("[Gemini] Pro Extended verified ✓")
                return True
            else:
                log.warning("[Gemini] Post-switch aria-label: %s", aria[:80])
                return False
        except Exception as e:
            log.warning("[Gemini] Verification aria-label read failed: %s", e)
            # Optimistic: the clicks succeeded even if aria-label read failed
            return True

    # ── Extended Thinking completion detection (2026-06-28 fix) ──────────

    async def wait_response(self, page, timeout_ms: int = 600_000) -> str:
        """Extended-Thinking-aware completion detection.

        Overrides BaseAdapter because Extended Thinking has a unique lifecycle:
          1. Submit → stop button appears briefly (1-2s)
          2. Stop button disappears → thinking begins (30-300s)
             ⚠️  BaseAdapter treats stop-button-hidden as "generation finished"
          3. Thinking completes → final answer renders → toolbar appears

        Strategy: use the base detection flow (stop→toolbar) but with a much
        longer minimum-wait guard after the stop button disappears, because
        Extended mode keeps the toolbar hidden during the thinking phase.
        """
        import time as _time
        start = _time.time()

        # Step 1: Confirm submission (stop button appears)
        try:
            stop_btn = page.locator(self.STOP_SELECTOR).first
            await stop_btn.wait_for(state="visible", timeout=15_000)
            log.info("[Gemini] Stop button visible — submission confirmed")
        except Exception:
            log.info("[Gemini] Stop button did not appear")

        # Step 2: Wait for stop button to disappear (thinking begins).
        # Do NOT treat this as completion — Extended Thinking is just starting.
        try:
            remaining = max(10_000, timeout_ms - int((_time.time() - start) * 1000))
            await stop_btn.wait_for(state="hidden", timeout=remaining)
            log.info("[Gemini] Stop button hidden — Extended Thinking phase began")
        except Exception:
            log.info("[Gemini] Stop button never hidden or timed out")

        # Step 3: Wait for toolbar as definitive completion anchor.
        # P1 fix (2026-06-29): Cap thinking-phase wait at 90s. If stop button
        # disappeared (thinking began) but toolbar doesn't appear within 90s,
        # Gemini's backend is likely stuck (intermittent server-side issue
        # where generation starts but never completes).  Don't waste the full
        # timeout budget — extract partial content and let the orchestrator
        # flag it as PROMPT_ECHO_DOMINANT / degraded.
        THINKING_PHASE_CAP_MS = 90_000
        toolbar_found = False
        try:
            toolbar = page.locator(self.TOOLBAR_SELECTOR).first
            await toolbar.wait_for(state="visible", timeout=THINKING_PHASE_CAP_MS)
            toolbar_found = True
            log.info("[Gemini] Toolbar detected — Extended Thinking complete")
        except Exception:
            log.info("[Gemini] Toolbar timeout after %.0fs — generation likely stuck",
                     THINKING_PHASE_CAP_MS / 1000)

        # Step 3.5: If toolbar never appeared, generation is stuck.
        # 30s stability check is enough to confirm stuck vs slow.
        if not toolbar_found:
            max_stability_s = 30
            poll_interval_s = 3.0
            max_checks = int(max_stability_s / poll_interval_s)
            log.info("[Gemini] Post-stuck stability check: %.0fs (%d checks)",
                     max_stability_s, max_checks)

            last_len = 0
            stable_checks = 0
            for _ in range(max_checks):
                await asyncio.sleep(poll_interval_s)

                # Check if thinking indicator still present — reset if thinking
                if self.THINKING_SELECTOR:
                    try:
                        thinking_el = page.locator(self.THINKING_SELECTOR).first
                        if await thinking_el.is_visible():
                            last_change = _time.time()
                            stable_checks = 0
                            continue
                    except Exception:
                        pass

                try:
                    current = await self.extract_response(page)
                    if current and abs(len(current) - last_len) < 20:
                        stable_checks += 1
                        if stable_checks >= 2:
                            log.info("[Gemini] Content stabilised at %d chars",
                                     len(current))
                            break
                    else:
                        stable_checks = 0
                    last_len = len(current) if current else 0
                except Exception:
                    break

        # Step 4: Extract final response
        try:
            raw = await self.extract_response(page)
            log.info("[Gemini] Final extraction: %d chars", len(raw))
            return raw
        except Exception as e:
            log.warning("[Gemini] Final extract failed: %s", e)
            return ""

    async def extract_response(self, page) -> str:
        """Gemini-specific extraction with prompt-echo filtering.

        Overrides BaseAdapter.extract_response() to handle Gemini-specific
        DOM quirks: model-message ordering, thinking-section visibility,
        and prompt-echo detection.
        """
        # Try each strategy (parent implementation)
        strategies = self.RESPONSE_STRATEGIES
        for i, sel in enumerate(strategies):
            try:
                text = await page.evaluate("""(sel) => {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) return '';
                    // Get the LAST matching element (latest response)
                    const el = els[els.length - 1];
                    // Skip if it's a thinking toggle alone (very short)
                    const t = (el.textContent || el.innerText || '').trim();
                    if (t.length < 30) {
                        // Try second-to-last
                        if (els.length >= 2) {
                            const prev = els[els.length - 2];
                            const pt = (prev.textContent || prev.innerText || '').trim();
                            if (pt.length > 30) return pt;
                        }
                    }
                    return t;
                }""", sel)
                if text and len(text) > 30:
                    log.info("[Gemini] Strategy #%d '%s' → %d chars",
                             i + 1, sel[:50], len(text))
                    return text
            except Exception as e:
                log.debug("[Gemini] Strategy #%d failed: %s", i + 1, e)
                continue

        # Ultimate fallback: find largest text block that ISN'T the prompt.
        # Prompt-echo filtering: skip blocks that contain the adjudication
        # template markers (they're the prompt, not the response).
        try:
            text = await page.evaluate("""() => {
                const promptMarkers = [
                    '請按以下結構輸出',
                    '请按以下结构输出',
                    '你現在是擁有長鏈條推理能力的終審法官',
                    '你现在是拥有长链条推理能力的终审法官',
                    '原始問題',
                    '原始问题',
                    '專家分析矩陣',
                    '专家分析矩阵',
                ];
                const nodes = document.querySelectorAll(
                    'model-message, [class*=\"message\"], div, article, section'
                );
                let best = '';
                for (let i = nodes.length - 1; i >= 0; i--) {
                    const t = (nodes[i].textContent || nodes[i].innerText || '').trim();
                    // Skip prompt echo and UI chrome
                    if (t.length < 50 || t.length > 200000) continue;
                    let isPrompt = false;
                    for (const m of promptMarkers) {
                        if (t.includes(m)) { isPrompt = true; break; }
                    }
                    if (!isPrompt && t.length > best.length) {
                        best = t;
                    }
                }
                return best;
            }""")
            if text and len(text) > 30:
                log.info("[Gemini] Ultimate fallback (filtered): %d chars", len(text))
                return text
        except Exception:
            pass

        log.warning("[Gemini] ALL extraction strategies exhausted — returning empty")
        return ""

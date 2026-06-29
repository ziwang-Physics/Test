"""Gemini Mode Controller — Pro Extended Thinking switch (Angular CDK overlay).

P0 refactor (iteration-4 ChatGPT G-01/G-02): replaces fragile bool return with
structured ModeResult + proper state machine.  The old code:
  - Returned bool that orchestrator never checked
  - Optimistically returned True when aria-label read failed
  - Had no recovery path if menu state was inconsistent

Now: verify → apply → verify cycle with one retry. Fails with structured reason.
"""

import asyncio, logging, time
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger("adapters.gemini.mode")

# Angular CDK menu rendering timing
MENU_RENDER_TIMEOUT_MS = 5000
MENU_POLL_INTERVAL_S = 0.2
SUBMENU_ANIMATION_S = 2.0


class ThinkingPolicy(str, Enum):
    REQUIRED = "required"       # fail if can't enable
    PREFERRED = "preferred"     # try, but allow degradation
    OFF = "off"                 # explicitly disabled


@dataclass(frozen=True)
class ModeResult:
    """Structured result of thinking mode enablement.

    P0 fix (iteration-4 ChatGPT G-01): replaces bare bool that orchestrator
    never checked.  Callers MUST inspect .verified before proceeding.
    """
    verified: bool
    model: str | None = None
    level: str | None = None
    reason: str | None = None
    recovered: bool = False

    def __bool__(self) -> bool:
        """Explicit boolean conversion — True ONLY if verified."""
        return self.verified


class GeminiModeController:
    """Enable Pro Extended Thinking on Gemini Web.

    P0 fix (iteration-4 ChatGPT G-02): state-machine approach:
      1. verify current state
      2. if correct → VERIFIED
      3. close overlays → apply Pro + Extended → verify
      4. one retry on failure → return structured ModeResult
    """

    def __init__(self, url: str, editor_selector: str,
                 model_selector_sel: str = ""):
        self.url = url
        self.editor_sel = editor_selector
        self.model_sel = model_selector_sel or (
            'button[aria-label*="Pro"], button[aria-label*="Flash"], '
            'button[aria-label*="Gemini"]'
        )

    async def ensure_thinking_mode(self, page) -> ModeResult:
        """Enable Pro Extended Thinking. Idempotent, verified.

        P0 fix (iteration-4 ChatGPT G-01): returns ModeResult — callers MUST
        check .verified.  Never silently succeeds.
        """
        return await self._ensure_pro_extended(page)

    async def ensure_fresh_conversation(self, page) -> None:
        """Start a new conversation to avoid old history bleeding.

        P0 fix (2026-06-30 ChatGPT review): MUST verify the page is actually
        at the Gemini URL before checking DOM state.  On about:blank,
        msg_count is always 0, causing an early return that never navigates.
        """
        # P0: navigate first if not on target URL
        if not page.url.startswith(self.url):
            log.info("[Gemini] Page at %s — navigating to %s", page.url[:60], self.url)
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3000)
            try:
                await page.mouse.click(400, 400)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

        msg_count = await page.evaluate(
            "() => document.querySelectorAll('model-message').length"
        )
        if msg_count == 0:
            log.info("[Gemini] Already fresh (0 messages)")
            return

        log.info("[Gemini] %d existing messages — starting fresh conversation",
                 msg_count)
        try:
            new_chat = page.locator(
                'a[aria-label*="新对话"], a[aria-label*="New chat"], '
                'button[aria-label*="新对话"], button[aria-label*="New chat"]'
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
        await page.goto(self.url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)
        try:
            await page.mouse.click(400, 400)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

    async def _ensure_pro_extended(self, page) -> ModeResult:
        """State machine: verify → apply → verify, one retry.

        P0 refactor (iteration-4 ChatGPT G-02): explicit state machine with
        pre- and post-condition verification.  Closes overlays in finally block
        so inconsistent CDK state can't leak across attempts.
        """
        async def _verify() -> tuple[str | None, str | None]:
            """Read current model + thinking level from DOM. Returns (model, level).

            P0 fix (R1 Gemini mode): checks both aria-label AND innerText.
            After Angular CDK re-renders, aria-label may not immediately reflect
            the thinking level selection.  Fallback to button text content.
            """
            try:
                btn = page.locator(self.model_sel).first
                await btn.wait_for(state="visible", timeout=3000)
                aria = (await btn.get_attribute("aria-label") or "")
                inner = (await btn.inner_text() or "")
                # Combine both sources — inner_text often has level info aria-label misses
                combined = f"{aria} {inner}"
                model = None
                level = None
                if "Pro" in combined:
                    model = "pro"
                elif "Flash" in combined:
                    model = "flash"
                if "延長" in combined or "Extended" in combined or "延长" in combined:
                    level = "extended"
                elif "标准" in combined or "Standard" in combined:
                    level = "standard"
                log.info("[Gemini] Verify: model=%s level=%s (aria=%s inner=%s)",
                        model, level, aria[:60], inner[:60])
                return model, level
            except Exception:
                return None, None

        async def _close_overlays() -> None:
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
            except Exception:
                pass

        last_reason = None

        for attempt in range(2):
            try:
                # Step 1: Verify current state
                model, level = await _verify()
                if model == "pro" and level == "extended":
                    log.info("[Gemini] Pro Extended verified ✓ (attempt %d)", attempt + 1)
                    return ModeResult(True, model, level, recovered=attempt > 0)

                # Step 2: Close any open overlays + re-open
                await _close_overlays()
                btn = page.locator(self.model_sel).first
                try:
                    await btn.click(timeout=5000)
                except Exception:
                    last_reason = "MODEL_SELECTOR_NOT_CLICKABLE"
                    continue

                if not await self._wait_for_menu_items(page):
                    last_reason = "MENU_ITEMS_NOT_RENDERED"
                    continue

                # Step 3: Select Pro model
                if model != "pro":
                    if not await self._select_pro_model(page):
                        last_reason = "PRO_MODEL_SELECTION_FAILED"
                        continue
                    # Re-open menu after Pro selection (model change closes it)
                    try:
                        await btn.click(timeout=5000)
                        await self._wait_for_menu_items(page)
                    except Exception:
                        last_reason = "POST_PRO_MENU_REOPEN_FAILED"
                        continue

                # Step 4: Expand thinking submenu
                if not await self._expand_thinking_submenu(page):
                    last_reason = "THINKING_SUBMENU_EXPAND_FAILED"
                    continue

                # Step 5: Select Extended
                if not await self._select_extended(page):
                    last_reason = "EXTENDED_SELECTION_FAILED"
                    continue

                # Step 6: Close + final verification
                await _close_overlays()
                await asyncio.sleep(1.0)
                model, level = await _verify()
                if model == "pro" and level == "extended":
                    log.info("[Gemini] Pro Extended verified ✓ (attempt %d)", attempt + 1)
                    return ModeResult(True, model, level, recovered=attempt > 0)

                last_reason = f"POST_SWITCH_VERIFY: model={model} level={level}"
            except Exception as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
            finally:
                await _close_overlays()

        log.error("[Gemini] Pro Extended FAILED after 2 attempts: %s", last_reason)
        return ModeResult(False, reason=last_reason)

    # ── Angular CDK menu helpers ──────────────────────────────────────

    async def _wait_for_menu_items(self, page,
                                   timeout_ms: int = MENU_RENDER_TIMEOUT_MS) -> bool:
        """Poll until >=2 gem-menu-item elements have non-empty innerText."""
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
        """Return all visible gem-menu-item elements."""
        return await page.evaluate("""() => {
            return [...document.querySelectorAll('gem-menu-item')]
                .map((el, i) => ({
                    i, text: (el.textContent || el.innerText || '').trim(),
                    visible: el.offsetParent !== null,
                    selected: el.classList.contains('selected'),
                }));
        }""")

    async def _select_pro_model(self, page) -> bool:
        """Ensure 'Pro' model is selected (not Flash). Returns True on success."""
        items = await self._get_menu_items(page)
        pro_selected = any(
            it["selected"] and "Pro" in it["text"] and "Flash" not in it["text"]
            for it in items
        )
        if pro_selected:
            log.info("[Gemini] Pro model already selected")
            return True

        for it in items:
            if "Pro" in it["text"] and "Flash" not in it["text"] and it["visible"]:
                try:
                    await page.locator("gem-menu-item").nth(it["i"]).click()
                    await asyncio.sleep(1.5)
                    log.info("[Gemini] Switched to Pro model")
                    return True
                except Exception as e:
                    log.warning("[Gemini] Pro selection click failed: %s", e)
                    return False
        log.warning("[Gemini] Pro model not found in menu items")
        return False

    async def _expand_thinking_submenu(self, page) -> bool:
        """Click 'Thinking level' to expand submenu."""
        items = await self._get_menu_items(page)
        for it in items:
            if ("思考程度" in it["text"] or "Thinking" in it["text"]) and it["visible"]:
                try:
                    await page.locator("gem-menu-item").nth(it["i"]).click()
                    await asyncio.sleep(SUBMENU_ANIMATION_S)
                    log.info("[Gemini] Expanded thinking level submenu")
                    return True
                except Exception as e:
                    log.warning("[Gemini] Thinking level click failed: %s", e)
                break
        log.warning("[Gemini] '思考程度' menu item not found")
        return False

    async def _select_extended(self, page) -> bool:
        """Select '延長' (Extended) from submenu.

        P0 fix (R1): tries text-based locator first (more robust against
        Angular CDK re-renders that change nth indices), then falls back
        to nth-index click.
        """
        if not await self._wait_for_menu_items(page):
            log.warning("[Gemini] Submenu items never rendered")
            return False

        items = await self._get_menu_items(page)
        log.info("[Gemini] Menu items for Extended: %s",
                 ', '.join(f'{it["i"]}:{it["text"][:30]}' for it in items[:8]))

        # Method 1: text-based locator (survives Angular CDK re-renders)
        try:
            ext_btn = page.locator("gem-menu-item").filter(has_text="延長").first
            await ext_btn.wait_for(state="visible", timeout=3000)
            await ext_btn.click()
            await asyncio.sleep(1.0)
            log.info("[Gemini] Selected Extended via text locator")
            return True
        except Exception as e:
            log.debug("[Gemini] Text locator click failed: %s — trying nth", e)

        # Method 2: nth-index fallback
        for it in items:
            if ("延長" in it["text"] and "标准" not in it["text"]
                    and it["visible"]):
                try:
                    await page.locator("gem-menu-item").nth(it["i"]).click()
                    await asyncio.sleep(1.0)
                    log.info("[Gemini] Selected Extended via nth(%d)", it["i"])
                    return True
                except Exception as e:
                    log.warning("[Gemini] Extended nth click failed: %s", e)

        log.warning("[Gemini] '延長' menu item not found in %d items", len(items))
        return False

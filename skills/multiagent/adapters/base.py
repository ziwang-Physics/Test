#!/usr/bin/env python3
"""
Base adapter — generic browser-automation primitives shared by all platforms.

Subclasses MUST override: name, EDITOR_SELECTOR, SEND_SELECTOR, STOP_SELECTOR,
TOOLBAR_SELECTOR, RESPONSE_STRATEGIES, URL.
"""

import asyncio, logging, time
from contextlib import asynccontextmanager, suppress

from common import (
    cdp_url, PAGE_GOTO_TIMEOUT_MS, PAGE_LOAD_WAIT_MS, SPA_WAKE_WAIT_MS,
    EDITOR_READY_TIMEOUT_MS, INSERT_TEXT_LIMIT, RESPONSE_STABILITY_S,
    STABILITY_POLL_MS,
)

log = logging.getLogger("adapters.base")


class PromptInjectionError(RuntimeError):
    """Raised when prompt text fails to land in the editor (P0: fail-closed)."""
    pass


# ── P1: Safe Page lifecycle (RAII, prevents CDP leaks) ───────────────────

@asynccontextmanager
async def safe_page(context):
    """Async context manager for RAII Page lifecycle.

    Guarantees page.close() even if the body raises.  Uses suppress() in the
    finally block so that a Target-already-closed error during cleanup does
    not mask the original exception.

    Usage:
        async with safe_page(context) as page:
            await page.goto(url)
            result = await extract(page)
    """
    page = await context.new_page()
    try:
        yield page
    finally:
        with suppress(Exception):
            await page.close()


class BaseAdapter:
    """Abstract interface for a web AI chat platform.

    Subclass must define platform-specific selectors and a response-extraction
    strategy list.  The base class provides the full pipeline:
    connect → ensure_fresh → ensure_ready → clear_input → inject_prompt →
    trigger_send → wait_response → extract_response → clean_response →
    validate_response.
    """

    name: str = "base"
    cdp_port: str = "9222"

    # ── Subclass MUST override ──
    EDITOR_SELECTOR: str = ""
    SEND_SELECTOR: str = ""
    STOP_SELECTOR: str = ""
    TOOLBAR_SELECTOR: str = ""
    RESPONSE_SELECTOR: str = ""
    URL: str = ""

    # Response extraction strategies — ordered; first substantial match wins.
    RESPONSE_STRATEGIES: list[str] = []

    # Platform-specific error / rate-limit patterns appended by subclasses.
    ERROR_PATTERNS: list[str] = []

    # CSS selector for "still thinking/loading" indicator (spinner, dots, etc.).
    # Used by stability fallback to avoid extracting mid-generation.
    THINKING_SELECTOR: str = ""

    def __init__(self, cdp_port: str = "9222"):
        self.cdp_port = cdp_port

    # ── Connect ────────────────────────────────────────────────────────────

    async def connect(self, pw=None, context=None):
        """Connect to the platform in one of two modes:

        1. SHARED CONTEXT (recommended): pass ``context=`` (a BrowserContext).
           Creates a new TAB in the existing Chrome window. Cleanup closes tab.

        2. INDEPENDENT CONTEXT (legacy): pass ``pw=`` (Playwright instance).
           Creates a new BrowserContext (= new window). Cleanup destroys it.
        """
        if context is not None:
            self._owns_context = False
            self._context = context
            page = await context.new_page()
            # Don't navigate here — ensure_fresh_conversation() handles initial
            # navigation.  Double page.goto() was wasting ~10s per tab and
            # could trigger "Target has been closed" on concurrent tabs.
            self._page = page
            log.info("[%s] Connected (shared tab) — new page created", self.name)
            return page

        if pw is None:
            raise ValueError("connect() requires either pw= or context=")

        self._owns_context = True
        browser = await pw.chromium.connect_over_cdp(cdp_url(self.cdp_port))
        self._browser = browser
        self._context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        await self._context.grant_permissions(["clipboard-read", "clipboard-write"])

        page = await self._context.new_page()
        await page.goto(self.URL, wait_until="domcontentloaded",
                        timeout=PAGE_GOTO_TIMEOUT_MS)
        await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
        try:
            await page.mouse.click(400, 400)
        except Exception:
            pass
        await page.wait_for_timeout(SPA_WAKE_WAIT_MS)

        self._page = page
        log.info("[%s] Connected (isolated context) — %s", self.name, await page.title())
        return page

    async def cleanup(self) -> None:
        """Close tab (shared mode) or destroy context (legacy mode)."""
        if hasattr(self, '_owns_context') and not self._owns_context:
            if hasattr(self, '_page') and self._page:
                try:
                    await self._page.close()
                    log.info("[%s] Tab closed", self.name)
                except Exception as e:
                    log.warning("[%s] Tab close error: %s", self.name, e)
            return

        if hasattr(self, '_context') and self._context:
            try:
                await self._context.close()
                log.info("[%s] Context destroyed", self.name)
            except Exception as e:
                log.warning("[%s] Context close error: %s", self.name, e)

    # ── Page readiness ─────────────────────────────────────────────────────

    # ── Health Probe (P0: ChatGPT robustness review 2026-06-30) ──────────────

    async def probe(self, page) -> dict:
        """Quick health check before injecting full prompt.

        Returns dict with keys: url_ok, editor_visible, can_type, can_clear,
        error (str or None).  Called by orchestrator before expensive operations.
        """
        result = {"url_ok": False, "editor_visible": False,
                  "can_type": False, "can_clear": False, "error": None}
        try:
            # 1. URL check
            current = page.url
            result["url_ok"] = current.startswith(self.URL) and "about:blank" not in current
            if not result["url_ok"]:
                result["error"] = f"URL mismatch: {current[:80]}"
                return result

            # 2. Editor check
            editor = page.locator(self.EDITOR_SELECTOR).first
            try:
                await editor.wait_for(state="visible", timeout=5_000)
                result["editor_visible"] = True
            except Exception:
                result["error"] = "Editor not visible"
                return result

            # 3. Can-type round-trip test
            canary = "__hb_probe__"
            await editor.focus()
            await page.keyboard.insert_text(canary)
            await asyncio.sleep(0.3)
            content = await editor.evaluate(
                "el => (el.textContent || el.value || el.innerText || '')"
            )
            result["can_type"] = canary in content

            # 4. Clear test
            await editor.fill("")
            await asyncio.sleep(0.2)
            cleared = await editor.evaluate(
                "el => (el.textContent || el.value || el.innerText || '').trim()"
            )
            result["can_clear"] = len(cleared) == 0

            if not result["can_type"] or not result["can_clear"]:
                result["error"] = (
                    f"Editor round-trip failed: type={result['can_type']}, "
                    f"clear={result['can_clear']}"
                )
        except Exception as e:
            result["error"] = str(e)[:200]
        return result

    async def ensure_ready(self, page) -> None:
        """Wait for input editor to be visible and focused."""
        try:
            editor = page.locator(self.EDITOR_SELECTOR).first
            await editor.wait_for(state="visible", timeout=EDITOR_READY_TIMEOUT_MS)
            await editor.focus()
            await editor.click()
            log.info("[%s] Editor ready", self.name)
        except Exception as e:
            log.warning("[%s] Editor wait failed: %s — retrying", self.name, e)
            # P0 fix (2026-06-30): NEVER goto(page.url) blindly — if the page
            # is about:blank, navigating to about:blank succeeds but stays blank.
            # Instead: reload if on target URL, else navigate to target.
            if page.url.startswith(self.URL):
                await page.reload(wait_until="domcontentloaded",
                                  timeout=PAGE_GOTO_TIMEOUT_MS)
            else:
                await page.goto(self.URL, wait_until="domcontentloaded",
                                timeout=PAGE_GOTO_TIMEOUT_MS)
            await page.wait_for_timeout(5000)
            editor = page.locator(self.EDITOR_SELECTOR).first
            await editor.wait_for(state="visible", timeout=EDITOR_READY_TIMEOUT_MS)
            await editor.focus()
            await editor.click()

    async def ensure_fresh_conversation(self, page) -> None:
        """Start a new conversation. Override in platform adapters.

        Default: navigate to base URL (strips conversation-specific path)."""
        log.info("[%s] Starting fresh conversation via URL navigation", self.name)
        await page.goto(self.URL, wait_until="domcontentloaded",
                        timeout=PAGE_GOTO_TIMEOUT_MS)
        await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)
        try:
            await page.mouse.click(400, 400)
        except Exception:
            pass
        await page.wait_for_timeout(SPA_WAKE_WAIT_MS)

    async def ensure_thinking_mode(self, page) -> bool:
        """Enable the platform's deep-thinking / reasoning mode.

        Default: no-op (most platforms don't have a toggle).
        Override in platform adapters that have a thinking toggle
        (Qianwen: 思考 button, Gemini: Pro Extended via ensure_pro_extended).

        Returns True on success, False on failure (non-fatal).
        """
        return True

    # ── Input pipeline ─────────────────────────────────────────────────────

    async def clear_input(self, page) -> None:
        """Clear editor via keyboard (triggers framework change detection)."""
        try:
            editor = page.locator(self.EDITOR_SELECTOR).first
            await editor.fill("")
        except Exception:
            await page.locator(self.EDITOR_SELECTOR).first.focus()
            await page.keyboard.press("ControlOrMeta+a")
            await page.keyboard.press("Backspace")
        await page.wait_for_timeout(100)

    async def inject_prompt(self, page, text: str) -> None:
        """Type text into the chat editor.

        P0 fix (iteration-3 ChatGPT P0-02): uses locator.fill() as primary
        method (supports input/textarea/[contenteditable], triggers input events).
        Falls back to keyboard.insert_text() for short prompts.  CLIPBOARD PASTE
        IS DISABLED — navigator.clipboard.writeText() may fail silently on
        shared contexts without clipboard permissions, and the subsequent
        Ctrl+V would paste whatever was already in the user's OS clipboard.
        """
        editor = page.locator(self.EDITOR_SELECTOR).first

        # Method 1: locator.fill() — Playwright-recommended, works on
        # <input>, <textarea>, and [contenteditable]. Fires input events.
        try:
            await editor.fill(text)
            log.info("[%s] Prompt injected via fill() (%d chars)", self.name, len(text))
            await page.wait_for_timeout(300)
            return
        except Exception as e:
            log.debug("[%s] fill() failed: %s — trying insert_text", self.name, e)

        # Method 2: keyboard.insert_text() for shorter prompts
        if len(text) <= INSERT_TEXT_LIMIT:
            await editor.focus()
            await page.keyboard.insert_text(text)
            log.info("[%s] Prompt injected via insert_text (%d chars)", self.name, len(text))
            await page.wait_for_timeout(300)
            return

        # Method 3: DOM injection as last resort (for large prompts on
        # rich-text editors that reject fill()).  Directly sets textContent
        # on the editor element's locator, NOT via document.querySelector.
        try:
            await editor.evaluate("(el, t) => el.textContent = t", text)
            log.info("[%s] Prompt injected via DOM el.textContent (%d chars)",
                     self.name, len(text))
            await page.wait_for_timeout(300)
        except Exception as e:
            log.error("[%s] ALL injection methods failed: %s", self.name, e)
            raise PromptInjectionError(
                f"Failed to inject prompt ({len(text)} chars): {e}"
            ) from e

        # Integrity check using content fingerprint (hash), not length diff
        if len(text) >= 50:
            try:
                actual = await editor.evaluate(
                    "el => (el.textContent || el.innerText || '').trim()"
                )
                import hashlib, unicodedata
                norm_expected = unicodedata.normalize("NFC", text).replace("\r\n", "\n").strip()
                norm_actual = unicodedata.normalize("NFC", actual).replace("\r\n", "\n").strip()
                if hashlib.blake2s(norm_actual.encode()).digest() != \
                   hashlib.blake2s(norm_expected.encode()).digest():
                    log.warning("[%s] Content fingerprint mismatch — may be truncated",
                               self.name)
                    # Still proceed if length is reasonable (>70% of expected)
                    if len(norm_actual) < len(norm_expected) * 0.7:
                        raise RuntimeError(
                            f"Payload severely truncated: {len(norm_actual)} vs {len(norm_expected)}"
                        )
            except RuntimeError:
                raise
            except Exception:
                pass  # integrity check is best-effort

        log.info("[%s] Prompt injected (%d chars)", self.name, len(text))

    async def trigger_send(self, page) -> None:
        """Submit prompt — one method only, verify state change.

        P1 fix (iteration-3 ChatGPT P1-01): old code tried Enter → click →
        Ctrl+Enter in sequence.  If click() actually succeeded but then
        navigated or detached, the exception catch would proceed to Enter
        fallback — causing double-send.  Now: try click first (it has
        Playwright actionability checks), then Enter, then stop.
        """
        # Record pre-send state to verify submission actually happened
        try:
            pre_user_count = await page.evaluate("""() => {
                return document.querySelectorAll(
                    '[data-message-author-role="user"]'
                ).length;
            }""")
        except Exception:
            pre_user_count = -1

        sent = False

        # Method 1: Button click — Playwright checks visible/stable/enabled
        try:
            send_btn = page.locator(self.SEND_SELECTOR).first
            await send_btn.click(timeout=5000)
            log.info("[%s] Sent via button click", self.name)
            sent = True
        except Exception:
            pass

        # Method 2: Enter key — only if click didn't send
        if not sent:
            try:
                editor = page.locator(self.EDITOR_SELECTOR).first
                await editor.focus()
                await editor.press("Enter")
                log.info("[%s] Sent via Enter key", self.name)
                sent = True
            except Exception:
                pass

        if not sent:
            log.error("[%s] ALL send methods failed", self.name)
            raise RuntimeError(f"[{self.name}] Failed to send prompt")

        # Verify state change: either a new user message appeared or
        # editor was cleared (confirms submission was consumed)
        await asyncio.sleep(1.5)
        try:
            post_user_count = await page.evaluate("""() => {
                return document.querySelectorAll(
                    '[data-message-author-role="user"]'
                ).length;
            }""")
            if pre_user_count >= 0 and post_user_count > pre_user_count:
                log.info("[%s] Send confirmed: user messages %d→%d",
                         self.name, pre_user_count, post_user_count)
            else:
                # Check if editor was cleared as alternative confirmation
                editor = page.locator(self.EDITOR_SELECTOR).first
                content = await editor.evaluate(
                    "el => (el.textContent || el.innerText || '').trim()"
                )
                if len(content) < 10:
                    log.info("[%s] Send confirmed: editor cleared", self.name)
                else:
                    log.warning("[%s] Send may NOT have succeeded — editor still has %d chars",
                               self.name, len(content))
        except Exception:
            pass  # verification is best-effort

    # ── Baseline tracking (P0 fix 2026-06-29: multi-AI 3-way diagnostic) ──
    # Root cause of 6-round Gemini PROMPT_ECHO_DOMINANT: in reused tabs,
    # `els[els.length - 1]` picks the user's OWN just-injected message
    # (it's the newest element), not the yet-to-be-generated assistant reply.
    # Fix: record assistant-turn count BEFORE send, only extract index >= baseline.

    async def _record_assistant_baseline(self, page) -> dict:
        """Count existing assistant-turn elements BEFORE sending the prompt.

        P0 fix (R2-series R1): returns per-selector baseline counts instead of
        a single scalar max.  Old code recorded max(count) across all selectors,
        then used that single number as the start index for EVERY selector.
        When selectors have different granularities (e.g. model-message has 12
        elements but .response-text has 2), the smaller set was never scanned
        because i >= 12 skipped all its elements.

        Called by orchestrator._p2_worker right before trigger_send().
        After generation, wait_response() only looks at elements with
        index >= baseline[sel] — skipping the user message and old history.
        """
        try:
            counts = await page.evaluate("""(strategies) => {
                const result = {};
                for (const sel of strategies) {
                    result[sel] = document.querySelectorAll(sel).length;
                }
                return result;
            }""", self.RESPONSE_STRATEGIES)
            log.info("[%s] Baseline: %s", self.name,
                     ', '.join(f'{s[:30]}={c}' for s, c in list(counts.items())[:3]))
            return counts
        except Exception:
            return {s: 0 for s in self.RESPONSE_STRATEGIES}

    # ── Response pipeline ──────────────────────────────────────────────────

    async def wait_response(self, page, timeout_ms: int = 300_000) -> str:
        """Wait for generation complete, then extract response.

        P0 fix (iteration-6 P0-03): sets self._last_was_truncated when timeout
        occurs so callers can propagate the truncation marker to users.  The old
        code returned partial text without indicating truncation — users saw
        incomplete answers thinking they were complete.

        Q1-Q2 AI feedback (2026-06-29): MutationObserver + content-fingerprint.
        - Baseline recorded before submit (via _record_baseline) to only extract NEW content
        - MutationObserver injected to detect DOM changes without polling
        - Falls back to 500ms poll if MutationObserver unavailable
        """
        self._last_was_truncated = False
        start = time.time()

        # Phase 1: stop button appear → disappear = generation window
        try:
            stop_btn = page.locator(self.STOP_SELECTOR).first
            await stop_btn.wait_for(state="visible", timeout=30_000)
            log.info("[%s] Generation started", self.name)
            remaining = max(10_000, timeout_ms - int((time.time() - start) * 1000))
            await stop_btn.wait_for(state="hidden", timeout=remaining)
            log.info("[%s] Stop button hidden", self.name)
        except Exception:
            log.info("[%s] No stop-button phase", self.name)

        # Phase 2: MutationObserver + single-evaluate extraction.
        # P0 fix (iteration-9): disconnect old observer before installing new.
        # Old code never disconnected on the success return path — each round
        # accumulated a new observer on the DOM, causing CPU/memory leak across
        # tab reuses.  Now wrapped in try/finally for guaranteed cleanup.
        try:
            await page.evaluate("""() => {
                window.__agentchat_observer?.disconnect();
                window.__agentchat_observer = null;
                window.__agentchat_mutations = 0;
                window.__agentchat_observer = new MutationObserver(() => {
                    window.__agentchat_mutations++;
                });
                window.__agentchat_observer.observe(document.body, {
                    childList: true, subtree: true, characterData: true
                });
            }""")
        except Exception:
            pass  # observer is best-effort

        CONTENT_STABILITY_S = 1.5
        last_len = 0
        stable_since = time.time()

        # P0 fix (iteration-9): wrap polling in try/finally so MutationObserver
        # is disconnected on ALL exit paths (success return, timeout, exception).
        # Old code only cleaned up on timeout/exception — the normal return path
        # left the observer active, accumulating across tab reuses.
        try:
            while True:
                elapsed_ms = int((time.time() - start) * 1000)
                if elapsed_ms > timeout_ms:
                    log.warning("[%s] Timeout after %.0fs — extracting partial", self.name, timeout_ms / 1000)
                    self._last_was_truncated = True
                    break

                # Check thinking indicator
                if self.THINKING_SELECTOR:
                    try:
                        if await page.locator(self.THINKING_SELECTOR).first.is_visible():
                            stable_since = time.time()
                            await page.wait_for_timeout(500)
                            continue
                    except Exception:
                        pass

                # P0 fix (R2-series R1): per-selector baseline — old code
                # used a single scalar for ALL selectors, which skipped new
                # responses on selectors with fewer total elements.
                try:
                    baseline = getattr(self, '_assistant_baseline', {})
                    # If baseline is still old-style scalar, convert
                    if isinstance(baseline, (int, float)):
                        baseline = {s: int(baseline) for s in self.RESPONSE_STRATEGIES}
                    result = await page.evaluate("""([strategies, baseline]) => {
                        const mutations = window.__agentchat_mutations || 0;
                        window.__agentchat_mutations = 0;
                        let text = '';
                        for (const sel of strategies) {
                            const start = baseline[sel] ?? 0;
                            const els = document.querySelectorAll(sel);
                            for (let i = els.length - 1; i >= start; i--) {
                                const t = (els[i].textContent || '').trim();
                                if (t.length > 20) { text = t; break; }
                            }
                            if (text) break;
                        }
                        return {mutations, text, len: text.length};
                    }""", [self.RESPONSE_STRATEGIES, baseline])
                except Exception:
                    await page.wait_for_timeout(500)
                    continue

                current = result.get("text", "")
                mutations = result.get("mutations", 0)
                cur_len = len(current)

                if cur_len > last_len or mutations > 0:
                    last_len = cur_len
                    stable_since = time.time()
                elif cur_len > 20 and (time.time() - stable_since) >= CONTENT_STABILITY_S:
                    log.info("[%s] Content stable at %d chars (%.1fs, %d mutations)",
                             self.name, cur_len, time.time() - stable_since, mutations)
                    return current

                await page.wait_for_timeout(400)
        finally:
            # Guaranteed cleanup — disconnect observer, clear state
            try:
                await page.evaluate("""() => {
                    window.__agentchat_observer?.disconnect();
                    delete window.__agentchat_observer;
                    delete window.__agentchat_mutations;
                }""")
            except Exception:
                pass

        try:
            return await self.extract_response(page)
        except Exception as e:
            log.warning("[%s] Final extract failed: %s", self.name, e)
            return ""

    async def extract_response(self, page) -> str:
        """Multi-strategy DOM extraction. NEVER touches OS clipboard.

        Tries each selector in RESPONSE_STRATEGIES. Returns the first match
        with substantial content (>20 chars). If all strategies fail, scans
        the page for the largest text block as an ultimate fallback.

        P2 fix (R3 2026-06-29): MAX_RESPONSE_SIZE cap prevents OOM from
        runaway textContent on pages with massive inline scripts/styles.
        """
        strategies = self.RESPONSE_STRATEGIES
        if not strategies:
            log.warning("[%s] No RESPONSE_STRATEGIES defined!", self.name)
            return ""

        MAX_RESPONSE_SIZE = 500_000  # 500KB — well above any real LLM response

        for i, sel in enumerate(strategies):
            try:
                # P0 security: selector passed as parameter, not interpolated
                # P1: textContent preferred over innerText — no forced reflow,
                # penetrates Shadow DOM, higher performance. innerText is
                # layout-aware (triggers style recalculation on every read).
                baseline = getattr(self, '_assistant_baseline', {})
                if isinstance(baseline, (int, float)):
                    baseline = {s: int(baseline) for s in self.RESPONSE_STRATEGIES}
                start_idx = baseline.get(sel, 0) if isinstance(baseline, dict) else 0
                text = await page.evaluate("""([sel, start]) => {
                    const els = document.querySelectorAll(sel);
                    if (els.length === 0) return '';
                    // P0 fix: only extract NEW elements (index >= per-selector baseline)
                    for (let i = els.length - 1; i >= start; i--) {
                        const t = (els[i].innerText || els[i].textContent || '').trim();
                        if (t.length > 20) return t;
                    }
                    return '';
                }""", [sel, start_idx])
                if text and len(text) > 20:
                    if len(text) > MAX_RESPONSE_SIZE:
                        log.warning("[%s] Response truncated: %d → %d chars",
                                     self.name, len(text), MAX_RESPONSE_SIZE)
                        text = text[:MAX_RESPONSE_SIZE] + "\n[RESPONSE_TRUNCATED]"
                    log.info("[%s] Strategy #%d '%s' → %d chars",
                             self.name, i + 1, sel[:50], len(text))
                    return text
            except Exception as e:
                log.debug("[%s] Strategy #%d failed: %s", self.name, i + 1, e)
                continue

        # Ultimate fallback: find largest text block in page.
        # Skip nav/aside/footer/sidebar containers — they poison extraction
        # with navigation labels and conversation history.
        # P1 fix (2026-06-29): raised upper limit from 50k → 200k to handle
        # Extended Thinking responses that can reach 50k-200k chars.
        try:
            text = await page.evaluate("""() => {
                const SKIP_TAGS = new Set(['nav', 'aside', 'footer', 'header',
                    'script', 'style', 'noscript', 'svg', 'side-navigation',
                    'side-navigation-v2', 'chat-history-sidebar']);
                const nodes = document.querySelectorAll('div, article, section');
                let best = '';
                for (let i = nodes.length - 1; i >= 0; i--) {
                    const el = nodes[i];
                    // Skip UI chrome containers
                    if (SKIP_TAGS.has(el.tagName.toLowerCase())) continue;
                    const parent = el.parentElement;
                    if (parent && SKIP_TAGS.has(parent.tagName.toLowerCase())) continue;
                    const t = (el.textContent || el.innerText || '').trim();
                    // Skip too-small (noise); upper bound 200k handles ET long responses
                    if (t.length > 30 && t.length < 200000 && t.length > best.length) {
                        best = t;
                    }
                }
                return best;
            }""")
            if text and len(text) > 20:
                log.info("[%s] Ultimate fallback: %d chars", self.name, len(text))
                return text
        except Exception:
            pass

        log.warning("[%s] ALL extraction strategies exhausted — returning empty", self.name)
        return ""

    # ── Clean & Validate ───────────────────────────────────────────────────

    # Navigation / UI noise markers stripped by clean_response.
    # Each tuple is (marker, max_line_len) — lines containing the marker are
    # dropped ONLY if the line is shorter than max_line_len (prevents false
    # positives when a real response discusses these platforms by name).
    NOISE_MARKERS: list[tuple[str, int]] = [
        ("和 Gemini 的對話", 40),
        ("与 Gemini 对话", 40),
        ("你說了", 20),
        ("你说", 20),
        ("Gemini 說了", 30),
        ("Gemini 说", 30),
        ("Gemini 是 AI", 40),
        ("Gemini 是一款 AI", 50),
        ("ChatGPT", 15),
        ("Claude", 12),
        ("Kimi", 10),
        ("豆包", 8),
        ("千问", 8),
        ("Pro", 5),
        ("延長", 5),
        ("Copy", 8),
        ("複製", 8),
        ("Good response", 20),
        ("好答案", 10),
        ("Send", 8),
        ("发送", 8),
        ("傳送", 8),
        ("新對話", 10),
        ("搜尋對話", 10),
        ("You are out of free messages", 80),
        ("Upgrade to", 30),
        ("Cancel anytime", 30),
        # P1 fix (2026-06-29): Kimi thinking-trace markers — the stability
        # fallback was extracting "思考已完成" + rephrased-prompt as the answer.
        ("思考已完成", 15),
        ("用户要求", 15),
        ("用户询问", 15),
        ("用户问", 12),
        ("用户说", 12),
        # P1 fix (2026-06-29): Gemini conversation chrome
        ("登录即可保存活动记录", 30),
        ("在新窗口中打开", 20),
        ("获取 Gemini 应用", 20),
        ("订阅", 6),
        ("企业应用场景", 15),
        ("其回答未必正确无误", 20),
    ]

    # Generic error/rate-limit patterns checked by validate_response.
    GENERIC_ERROR_PATTERNS = [
        "You are out of free messages",
        "You've hit your limit",
        "You hit your 5-hour message limit",
        "Upgrade to keep chatting",
        "limits will reset",
        "explore our Pro plan",
        "out of free messages until",
        "Please wait",
        "请稍候…",
        "Just a moment",
        "Verify you are human",
        # Cloudflare block page markers (NOT mentions of "Cloudflare" in normal text)
        "Cloudflare Ray ID",
        "Just a moment...",
        "Checking if the site connection is secure",
        "DDoS protection by Cloudflare",
    ]

    def clean_response(self, raw_text: str, prompt: str = "") -> str:
        """Strip prompt echo, navigation labels, and UI chrome from response.

        Noise filtering uses per-marker max-line-length guards so that a
        legitimate sentence like "Claude Code is great for architecture review"
        is NOT stripped just because it contains the word "Claude".

        P0 fix (iteration-3 ChatGPT P0-03): Kimi-specific regex moved to
        KimiAdapter.clean_response().  The old DOTALL patterns were destroying
        valid answers across all platforms.
        """
        if not raw_text:
            return ""
        text = raw_text.strip()

        # Strip the user's prompt if it appears verbatim at the start
        if prompt and text.startswith(prompt):
            text = text[len(prompt):].strip()

        # Noise marker removal with line-length guard
        for marker, max_len in self.NOISE_MARKERS:
            if marker in text:
                lines = text.split('\n')
                text = '\n'.join(
                    l for l in lines
                    if not (marker in l and len(l.strip()) < max_len)
                ).strip()

        text = text.strip('\n')
        return text

    def validate_response(self, text: str, prompt: str = "") -> tuple[bool, str]:
        """Check if response is a real answer or garbage.

        Returns:
            (is_valid, reason) where reason is one of:
            OK, EMPTY_OR_TOO_SHORT, ERROR_PATTERN_DETECTED, PROMPT_ECHO_DOMINANT,
            UI_CHROME_DOMINANT, DEGRADED_BUT_USABLE
        """
        if not text or len(text.strip()) < 5:
            return False, "EMPTY_OR_TOO_SHORT"

        # Check error / rate-limit patterns (combined generic + platform-specific)
        all_patterns = self.GENERIC_ERROR_PATTERNS + list(self.ERROR_PATTERNS)
        for pattern in all_patterns:
            if pattern.lower() in text.lower():
                return False, f"ERROR_PATTERN_DETECTED: {pattern[:40]}"

        # Check if response is mostly the user's own prompt (old convo bleed)
        if len(prompt) > 5:
            prompt_ratio = text.count(prompt) * len(prompt) / max(len(text), 1)
            if prompt_ratio > 0.5:
                return False, "PROMPT_ECHO_DOMINANT"

        # UI chrome detection: many short lines = navigation
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) > 20:
            short_lines = sum(1 for l in lines if len(l) < 30)
            if short_lines > len(lines) * 0.7:
                # UI_CHROME_DOMINANT but still has some content —
                # caller decides whether to use it (orchestrator P2 leniency)
                return False, "UI_CHROME_DOMINANT"

        return True, "OK"

    @staticmethod
    def is_pipeline_usable(is_valid: bool, reason: str, text_len: int) -> bool:
        """Centralised leniency rule for Phase 2 and main.py workers.

        UI_CHROME_DOMINANT responses often still contain usable content — the
        extraction just picked up some navigation chrome.  If the text is
        long enough (>200 chars), treat it as usable for downstream processing.
        """
        if is_valid:
            return True
        if reason == "UI_CHROME_DOMINANT" and text_len > 200:
            return True
        return False

    # ── Full submit pipeline (convenience) ─────────────────────────────────

    async def submit(self, page, prompt: str, timeout_ms: int = 300_000) -> str:
        """Full pipeline: clear → inject → send → wait."""
        await self.clear_input(page)
        await self.inject_prompt(page, prompt)
        await self.trigger_send(page)
        return await self.wait_response(page, timeout_ms)

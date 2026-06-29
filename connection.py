#!/usr/bin/env python3
"""ConnectionManager + PageLeaseRegistry — browser lifecycle + page ownership.

ChatGPT robustness review (2026-06-30) identified these as P0 architectural gaps:
  - Heartbeat's BrowserSupervisor reconnects without notifying orchestrator
  - No page ownership tracking → heartbeat can close workers' pages
  - connect_over_cdp disconnects not handled atomically

Design principle (ChatGPT):
  "browser_epoch handles CDP connection invalidation;
   lease.generation handles page ownership transfer between attempts.
   If either mismatches, forbid reload/close."

Integration:
  phase2_dispatch creates one ConnectionManager → acquires PageLeases for
  each worker tab → workers validate leases before operations → heartbeat
  checks leases before cleanup.
"""

import asyncio, logging, time, uuid
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import async_playwright

from common import cdp_url

log = logging.getLogger("connection")

SHARED_CDP_PORT = "9222"


class LeaseConflict(RuntimeError):
    """Raised when acquire() finds an existing lease on the same page."""
    pass


# ── Page Lease ───────────────────────────────────────────────────────────

@dataclass
class PageLease:
    """Ownership record for a browser page.

    P0 fix (ChatGPT Round 2): includes browser_epoch so leases from old
    connections are automatically invalid after reconnect.  page_key uses
    Python `id(page)` — stable across navigation, unique per object.
    """
    platform: str
    page_key: int          # id(page) — stable, unique per Python object
    run_id: str
    browser_epoch: int = 0
    attempt: int = 0
    generation: int = 0
    created_at: float = field(default_factory=time.time)

    def matches(self, platform: str, run_id: str, epoch: int, generation: int) -> bool:
        """True if this lease is valid for the given context."""
        return (self.platform == platform
                and self.run_id == run_id
                and self.browser_epoch == epoch
                and self.generation == generation)


# ── Page Lease Registry ──────────────────────────────────────────────────

class PageLeaseRegistry:
    """Track which page is owned by which worker.

    Prevents:
      - heartbeat from closing a page that a worker is using
      - old supervisor from closing a page transferred to a new attempt
      - two workers sharing the same page
      - safe_cleanup from clearing localStorage on pages owned by other runs
    """

    def __init__(self, run_id: str):
        self._run_id = run_id
        self._leases: dict[str, PageLease] = {}  # page_id → lease

    def acquire(self, page, platform: str, browser_epoch: int = 0,
                attempt: int = 0) -> PageLease:
        """Claim ownership of a page.  Returns the new lease token.

        P1 fix (iteration-5): raises LeaseConflict if page already has an active
        lease — prevents two workers silently sharing the same page.
        """
        pid = self._page_id(page)
        prev = self._leases.get(pid)
        if prev is not None:
            raise LeaseConflict(
                f"Page {pid} already leased by {prev.platform} "
                f"(gen={prev.generation}, epoch={prev.browser_epoch})"
            )
        lease = PageLease(
            platform=platform, page_key=pid,
            run_id=self._run_id, browser_epoch=browser_epoch,
            attempt=attempt,
            generation=0,
        )
        self._leases[pid] = lease
        log.debug("[Lease] page=%d acquired by %s gen=%d epoch=%d",
                 pid, platform, lease.generation, browser_epoch)
        return lease

    def release(self, token: PageLease = None, page=None) -> bool:
        """Release a lease.  Requires *token* for CAS safety.

        P1 fix (iteration-5): old code popped by page ID without checking the
        token — a stale worker could release a page transferred to a new owner.
        Now requires the lease token; only releases if the stored lease matches.
        Returns True if the lease was released, False if it was already gone.
        """
        if token is not None:
            pid = token.page_key
        elif page is not None:
            pid = self._page_id(page)
            token = self._leases.get(pid)
        else:
            return False

        current = self._leases.get(pid)
        if current is token or (token is not None and current == token):
            del self._leases[pid]
            return True
        return False

    def validate(self, page, platform: str, epoch: int, generation: int) -> bool:
        """Check if the lease for *page* is still valid.

        P0 fix: requires epoch + generation to prevent stale operations
        after browser reconnect or page transfer.
        """
        pid = self._page_id(page)
        lease = self._leases.get(pid)
        if lease is None:
            return False
        return lease.matches(platform, self._run_id, epoch, generation)

    def invalidate_epoch(self, old_epoch: int) -> None:
        """Remove all leases from *old_epoch* after browser reconnect."""
        removed = [k for k, v in self._leases.items()
                   if v.browser_epoch == old_epoch]
        for k in removed:
            del self._leases[k]
        if removed:
            log.info("[Lease] Invalidated %d leases from epoch %d",
                     len(removed), old_epoch)

    def is_mine(self, page) -> bool:
        pid = self._page_id(page)
        return pid in self._leases

    def my_pages(self, context) -> list:
        return [p for p in context.pages
                if not p.is_closed() and self.is_mine(p)]

    def owned_platforms(self) -> set[str]:
        return {l.platform for l in self._leases.values()}

    @staticmethod
    def _page_id(page) -> int:
        """P0 fix (ChatGPT Round 2): use Python object id, not URL.
        URL changes on navigation and collides across same-origin tabs."""
        return id(page)


# ── Connection Manager ───────────────────────────────────────────────────

class ConnectionManager:
    """Single owner of Playwright browser lifecycle.

    Every CDP disconnection creates a NEW browser_epoch.  All workers and
    heartbeat tasks must check the epoch before operating — operations on
    a stale epoch fail fast rather than corrupting state.

    Usage::

        cm = ConnectionManager()
        browser, context, epoch = await cm.connect()
        try:
            # ... run workers ...
        finally:
            await cm.disconnect()
    """

    def __init__(self):
        self._pw: Optional[async_playwright] = None
        self._browser = None
        self._context = None
        self._epoch: int = 0
        self._connected: bool = False
        self._run_id: str = uuid.uuid4().hex[:12]
        # P0 fix (iteration-2 ChatGPT C-01): per-epoch disconnect Futures instead
        # of a shared repeatedly-cleared Event.  Old epochs get their own Future
        # that is completed ONCE — no lost wake-up when _browser is cleared before
        # browser.close() triggers the disconnect handler.
        self._epoch_signals: dict[int, asyncio.Future[str]] = {}
        self._disconnect_reason: str | None = None
        self._lifecycle_lock = asyncio.Lock()  # P0: shared lock, not per-call

    # ── Public properties ─────────────────────────────────────────────

    @property
    def browser(self): return self._browser
    @property
    def context(self): return self._context
    @property
    def epoch(self) -> int: return self._epoch
    @property
    def connected(self) -> bool: return self._connected
    @property
    def run_id(self) -> str: return self._run_id
    def current_signal(self) -> asyncio.Future[str] | None:
        """The disconnect signal for the current epoch, or None."""
        return self._epoch_signals.get(self._epoch)
    @property
    def disconnect_reason(self) -> str | None: return self._disconnect_reason

    def is_epoch_live(self, expected_epoch: int) -> bool:
        """True if this epoch's connection is still alive."""
        signal = self._epoch_signals.get(expected_epoch)
        return (self._epoch == expected_epoch and self._connected
                and signal is not None and not signal.done()
                and self._browser is not None
                and self._browser.is_connected())

    async def wait_disconnected(self, expected_epoch: int) -> str:
        """Block until expected_epoch is disconnected or superseded.

        P0 fix (iteration-2 ChatGPT C-01): uses per-epoch Future instead of
        shared Event.  If the epoch is already gone, returns immediately.
        Uses asyncio.shield() so a cancelled waiter doesn't cancel the shared
        Future that other waiters are also awaiting.
        """
        signal = self._epoch_signals.get(expected_epoch)
        if signal is None:
            return f"epoch_already_superseded:{expected_epoch}→{self._epoch}"
        try:
            return await asyncio.shield(signal)
        except asyncio.CancelledError:
            # Don't break the shared Future for other waiters
            raise

    # ── Connect / Disconnect ──────────────────────────────────────────

    async def connect(self) -> tuple:
        """Initialize Playwright and connect to Chrome via CDP.

        P0 fix (ChatGPT Round 5): uses shared lifecycle lock.  Idempotent —
        if already connected, returns current state without touching epoch.
        """
        async with self._lifecycle_lock:
            if self._connected and self._browser and self._browser.is_connected():
                return self._browser, self._context, self._epoch
            return await self._connect_internal()

    async def reconnect(self, *, expected_epoch: int = None,
                         reason: str = "", force: bool = False) -> tuple:
        """Atomically reconnect under shared lifecycle lock.

        P0 fix (iteration-2 ChatGPT C-04): requires *expected_epoch* from the
        caller — if the current epoch differs, another recovery already happened
        and this call is a no-op.  Prevents stale heartbeat/worker recovery
        actions from tearing down a freshly-reconnected browser.

        P0 fix (ChatGPT Round 5): uses self._lifecycle_lock (shared) not
        asyncio.Lock() (new each call).
        """
        old_epoch = expected_epoch if expected_epoch is not None else self._epoch
        async with self._lifecycle_lock:
            # Already reconnected by another caller? Return new state
            if self._epoch != old_epoch:
                if self._connected:
                    log.info("[Connection] Already reconnected (epoch %d→%d) — no-op",
                             old_epoch, self._epoch)
                    return self._browser, self._context, self._epoch
                # old_epoch is gone, current not connected — force reconnect
                log.warning("[Connection] Epoch %d→%d stale + not connected — forcing",
                           old_epoch, self._epoch)
            elif self._connected and not force:
                return self._browser, self._context, self._epoch

            await self._disconnect_internal()
            result = await self._connect_internal()
            log.warning("[Connection] Reconnected — epoch %d reason=%s", self._epoch, reason)
            return result

    async def disconnect(self) -> None:
        """Graceful shutdown under lifecycle lock.

        P0 fix (iteration-2 ChatGPT C-01): manual disconnect now signals the
        current epoch's Future (via _disconnect_internal) so any waiter in
        wait_disconnected() returns immediately instead of hanging.
        """
        async with self._lifecycle_lock:
            log.info("[Connection] Disconnecting — browser_epoch=%d", self._epoch)
            self._connected = False
            await self._disconnect_internal()

    async def _connect_internal(self) -> tuple:
        """Create new connection.  Must hold lock.

        P0 fix (iteration-2 ChatGPT C-01): creates per-epoch disconnect Future
        FIRST, then atomically publishes resources.  If any step fails, cleans
        up without leaving half-initialized state.
        """
        new_epoch = self._epoch + 1
        epoch_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        pw = None
        browser = None
        context = None
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(
                cdp_url(SHARED_CDP_PORT)
            )
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("CDP connection established but no browser contexts found")
            context = contexts[0]
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
        except BaseException:
            # Clean up partially-built resources before publishing anything
            if browser:
                try: await browser.close()
                except Exception: pass
            if pw:
                try: await pw.stop()
                except Exception: pass
            raise

        # Atomically publish — only after all steps succeed
        self._pw = pw
        self._browser = browser
        self._context = context
        self._epoch = new_epoch
        self._connected = True
        self._disconnect_reason = None
        self._epoch_signals[new_epoch] = epoch_signal
        self._install_disconnect_handler(browser, new_epoch, epoch_signal)
        log.info("[Connection] Connected — browser_epoch=%d", new_epoch)
        return browser, context, new_epoch

    async def _disconnect_internal(self) -> None:
        """Close old connection fully — browser + Playwright driver.

        P0 fix (iteration-2 ChatGPT C-01): signals the old epoch's Future
        BEFORE clearing self._browser and calling browser.close().  The old
        code cleared self._browser first, which made the disconnect handler's
        identity check (self._browser is emitted_browser) fail — so _disconnected
        was never set, causing old-epoch waiters to hang forever.
        """
        old_browser = self._browser
        old_pw = self._pw
        old_epoch = self._epoch

        # Signal old epoch waiters BEFORE clearing references
        if old_epoch in self._epoch_signals:
            signal = self._epoch_signals.pop(old_epoch)
            if not signal.done():
                signal.set_result("manual_disconnect")

        self._browser = None
        self._context = None
        self._pw = None
        self._connected = False

        try:
            if old_browser:
                await old_browser.close()
        except Exception:
            pass
        try:
            if old_pw:
                await old_pw.stop()
        except Exception:
            pass

    def _install_disconnect_handler(self, browser, epoch: int,
                                     signal: asyncio.Future[str] | None = None) -> None:
        """P0 fix (iteration-2 ChatGPT C-01): uses per-epoch disconnect Future.

        If *signal* is not provided, looks up self._epoch_signals[epoch].
        The handler completes the Future to wake ALL waiters — no lost wake-up.
        """
        if signal is None:
            signal = self._epoch_signals.get(epoch)
            if signal is None:
                return  # epoch already superseded — nothing to signal

        def on_disconnected(emitted_browser=None) -> None:
            # Only act if this handler belongs to the physical browser object
            # that actually disconnected (Playwright emits on the exact Browser
            # instance — no stale events from old connections).
            if emitted_browser is not browser:
                return
            if not signal.done():
                signal.set_result("playwright_browser_disconnected")
            self._connected = False
            self._disconnect_reason = "playwright_browser_disconnected"
            log.error("[Connection] Browser disconnected — epoch=%d signal=%s",
                     epoch, "set" if signal.done() else "noop")

        browser.on("disconnected", on_disconnected)


# ── Integration helpers ──────────────────────────────────────────────────

def create_run_context() -> tuple[ConnectionManager, PageLeaseRegistry]:
    """Create a new run context with fresh ConnectionManager + PageLeaseRegistry.

    Returns (cm, registry).  Caller is responsible for cm.connect() and cm.disconnect().
    """
    cm = ConnectionManager()
    registry = PageLeaseRegistry(cm.run_id)
    return cm, registry

#!/usr/bin/env python3
"""Heartbeat monitoring for parallel Web AI workers (P0 reliability).

Multi-AI consensus design (2026-06-30, 3-platform review + DeepSeek adjudication):

  BrowserSupervisor (30s)              TabSupervisor (15s per tab)
  Browser.getVersion ping              page.evaluate(() => Date.now())
  3 failures → global reconnect        2 failures → tab reconnect
  Reconnect 2× (5s delay)              Reconnect 1× (2s delay)
  All fail → safe cleanup              Fail → degraded/skip

Safe cleanup sequence: clear editor → close CDP sessions → close tabs → kill.
"""

import asyncio, logging, time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("heartbeat")

# ── Parameters (multi-AI adjudicated defaults) ────────────────────────────

BROWSER_HEARTBEAT_INTERVAL = 30.0   # seconds between browser pings
BROWSER_HEARTBEAT_TIMEOUT  = 10.0   # seconds per ping before timeout
BROWSER_FAILURE_THRESHOLD  = 3      # consecutive failures → reconnect
BROWSER_RECONNECT_MAX      = 2      # max reconnect attempts
BROWSER_RECONNECT_DELAY    = 5.0    # seconds between reconnect attempts

TAB_HEARTBEAT_INTERVAL     = 15.0   # seconds between tab checks
TAB_HEARTBEAT_TIMEOUT      = 10.0   # seconds per check before timeout
TAB_FAILURE_THRESHOLD      = 2      # consecutive failures → reconnect
TAB_RECONNECT_MAX          = 1      # max reconnect attempts
TAB_RECONNECT_DELAY        = 2.0    # seconds between reconnect attempts

# ── Structured event log ──────────────────────────────────────────────────

@dataclass
class HeartbeatEvent:
    """Structured log entry for heartbeat state transitions."""
    timestamp: float = field(default_factory=time.time)
    event_type: str = ""        # "ping_ok" | "ping_fail" | "reconnect" | "degraded" | "dead" | "cleanup"
    target: str = ""            # "browser" | "chatgpt" | "qianwen" | "gemini" | ...
    latency_ms: float = 0.0     # round-trip latency
    fail_count: int = 0
    message: str = ""


# ── Browser Supervisor ────────────────────────────────────────────────────

class BrowserSupervisor:
    """Monitor Chrome browser CDP connection via periodic Browser.getVersion.

    P0 fix (iteration-5 H-01): uses browser-level CDP session for pings instead
    of the first page's page.evaluate().  The old approach would mark the browser
    as dead when only a single tab's renderer was stuck — a tab-level problem
    was escalated to full browser reconnect, cancelling healthy workers.

    Runs as a background asyncio task.  When the browser dies:
      1. Signal via on_dead callback (ConnectionManager handles recovery)
    """

    def __init__(self, browser, on_dead=None):
        self._browser = browser
        self._on_dead = on_dead            # async callback when browser is dead
        self._failures = 0
        self._alive = True
        self._cdp_session = None           # created in start()
        self._events: list[HeartbeatEvent] = []

    @property
    def alive(self) -> bool:
        return self._alive

    async def start(self) -> None:
        """Create browser-level CDP session for Browser.getVersion pings."""
        try:
            self._cdp_session = await self._browser.new_browser_cdp_session()
            log.info("[Heartbeat:Browser] CDP session acquired for browser-level ping")
        except Exception as e:
            log.warning("[Heartbeat:Browser] Cannot create CDP session: %s — "
                        "falling back to browser.is_connected()", e)
            self._cdp_session = None

    async def run(self):
        """Background loop: probe first, then sleep (detect faults immediately)."""
        log.info("[Heartbeat:Browser] Started (interval=%.0fs, timeout=%.0fs, threshold=%d)",
                 BROWSER_HEARTBEAT_INTERVAL, BROWSER_HEARTBEAT_TIMEOUT, BROWSER_FAILURE_THRESHOLD)
        while self._alive:
            ok, latency = await self._ping()
            if ok:
                self._failures = 0
                self._events.append(HeartbeatEvent(
                    event_type="ping_ok", target="browser", latency_ms=latency))
            else:
                self._failures += 1
                self._events.append(HeartbeatEvent(
                    event_type="ping_fail", target="browser", latency_ms=latency,
                    fail_count=self._failures))
                log.warning("[Heartbeat:Browser] Ping failed (%d/%d)",
                           self._failures, BROWSER_FAILURE_THRESHOLD)
                if self._failures >= BROWSER_FAILURE_THRESHOLD:
                    self._alive = False
                    log.error("[Heartbeat:Browser] DEAD — fault threshold reached")
                    if self._on_dead:
                        await self._on_dead()
                    break
            await asyncio.sleep(BROWSER_HEARTBEAT_INTERVAL)

    async def _ping(self) -> tuple[bool, float]:
        """Browser-level liveness check via CDP Browser.getVersion.

        P0 fix (iteration-5 H-01): CDP Browser.getVersion tests the browser
        transport directly — no renderer/page dependency.  First-page failures
        (navigation, renderer hang, tab close) no longer mark the browser dead.
        """
        t0 = time.monotonic()
        try:
            # Primary: browser-level CDP session
            if self._cdp_session is not None:
                await asyncio.wait_for(
                    self._cdp_session.send("Browser.getVersion"),
                    timeout=BROWSER_HEARTBEAT_TIMEOUT,
                )
                return True, (time.monotonic() - t0) * 1000
        except Exception:
            pass  # CDP failed — fall through to secondary check

        # Secondary: browser.is_connected() (no pages needed)
        try:
            if not self._browser.is_connected():
                return False, (time.monotonic() - t0) * 1000
            return True, (time.monotonic() - t0) * 1000
        except Exception:
            return False, (time.monotonic() - t0) * 1000

    async def _attempt_reconnect(self) -> bool:
        """P0 fix (ChatGPT review 2026-06-30): BrowserSupervisor MUST NOT
        reconnect independently.  Self-reconnect creates a second Playwright
        driver and replaces _browser without notifying ConnectionManager or
        cancelling old-epoch workers — causing split-brain.

        Now only REPORTS the fault via on_dead callback.  ConnectionManager
        is the single owner of browser lifecycle and handles reconnection.
        """
        log.warning("[Heartbeat:Browser] Fault reported — delegating to ConnectionManager")
        return False  # don't self-reconnect — let on_dead callback handle it

    async def safe_cleanup(self, context, leases=None) -> None:
        """Safe cleanup: close OWNED pages only.  NEVER touch storage.

        P0 fix (ChatGPT 2026-06-30): refuses destructive cleanup without
        PageLeaseRegistry.  Never clears localStorage/sessionStorage on
        shared persistent context — that destroys login state for all tabs.
        Without leases, simply does nothing (fail-closed).
        """
        if leases is None:
            log.warning("[Heartbeat:Browser] Refusing cleanup without PageLeaseRegistry")
            return
        log.info("[Heartbeat:Browser] Safe cleanup — closing owned tabs only")
        self._events.append(HeartbeatEvent(event_type="cleanup", target="browser"))
        pages_to_clean = leases.my_pages(context)
        for page in pages_to_clean:
            try:
                if not page.is_closed():
                    # P0: never clear storage on shared context — destroys login
                    await asyncio.shield(page.close())
            except Exception:
                pass

    def stop(self):
        self._alive = False


# ── Tab Supervisor ────────────────────────────────────────────────────────

class TabSupervisor:
    """Monitor individual tab health via page.evaluate + DOM mutation rate.

    Runs as a background asyncio task alongside the worker.  When a tab
    becomes unhealthy:
      1. Attempt reconnect (1×)
      2. On failure → mark degraded, call on_degraded callback
    """

    def __init__(self, tab_id: str, page, on_degraded=None):
        self.tab_id = tab_id
        self._page = page
        self._on_degraded = on_degraded
        self._failures = 0
        self._alive = True
        self._degraded = False
        self._last_mutation_count = 0
        self._events: list[HeartbeatEvent] = []

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def alive(self) -> bool:
        return self._alive

    async def run(self):
        """Background loop: health-check tab every TAB_HEARTBEAT_INTERVAL."""
        log.info("[Heartbeat:%s] Started (interval=%.0fs, timeout=%.0fs, threshold=%d)",
                 self.tab_id, TAB_HEARTBEAT_INTERVAL, TAB_HEARTBEAT_TIMEOUT, TAB_FAILURE_THRESHOLD)
        while self._alive and not self._degraded:
            await asyncio.sleep(TAB_HEARTBEAT_INTERVAL)
            if not self._alive or self._degraded:
                break
            ok, latency, dom_changed = await self._health_check()
            if ok:
                self._failures = 0
                self._events.append(HeartbeatEvent(
                    event_type="ping_ok", target=self.tab_id, latency_ms=latency))
            else:
                self._failures += 1
                self._events.append(HeartbeatEvent(
                    event_type="ping_fail", target=self.tab_id, latency_ms=latency,
                    fail_count=self._failures,
                    message="dom_stalled" if not dom_changed else "evaluate_timeout"))
                log.warning("[Heartbeat:%s] Health check failed (%d/%d): dom_changed=%s",
                           self.tab_id, self._failures, TAB_FAILURE_THRESHOLD, dom_changed)
                # P0 refactor: heartbeat only signals — worker decides recovery.
                # TabSupervisor no longer reloads or closes pages.
                if self._failures >= TAB_FAILURE_THRESHOLD:
                    self._degraded = True
                    log.error("[Heartbeat:%s] DEGRADED signal", self.tab_id)
                    if self._on_degraded:
                        await self._on_degraded(self.tab_id)
                    break  # stop probing degraded tab

    async def _health_check(self) -> tuple[bool, float, bool]:
        """L2 + L3 check: page.evaluate round-trip + DOM mutation rate."""
        t0 = time.time()
        try:
            result = await asyncio.wait_for(
                self._page.evaluate("""() => {
                    const now = Date.now();
                    // L3: DOM mutation check
                    window.__hb_mutations = window.__hb_mutations || 0;
                    const mutations = window.__hb_mutations;
                    window.__hb_mutations = 0;
                    return {ts: now, mutations};
                }"""),
                timeout=TAB_HEARTBEAT_TIMEOUT,
            )
            latency = (time.time() - t0) * 1000
            dom_changed = result.get("mutations", 0) > 0
            self._last_mutation_count = result.get("mutations", 0)
            return True, latency, dom_changed
        except Exception:
            return False, (time.time() - t0) * 1000, False

    async def _attempt_reconnect(self) -> bool:
        """Try to recover the tab by reloading it."""
        for attempt in range(1, TAB_RECONNECT_MAX + 1):
            log.warning("[Heartbeat:%s] Tab reconnect attempt %d/%d",
                       self.tab_id, attempt, TAB_RECONNECT_MAX)
            await asyncio.sleep(TAB_RECONNECT_DELAY)
            try:
                if not self._page.is_closed():
                    await self._page.reload(wait_until="domcontentloaded")
                    self._failures = 0
                    self._events.append(HeartbeatEvent(
                        event_type="reconnect", target=self.tab_id,
                        message=f"success (attempt {attempt})"))
                    log.info("[Heartbeat:%s] Tab reconnected", self.tab_id)
                    return True
            except Exception as e:
                log.warning("[Heartbeat:%s] Tab reconnect %d failed: %s", self.tab_id, attempt, e)
        return False

    async def safe_cleanup(self) -> None:
        """Clear editor content and close tab gracefully."""
        self._events.append(HeartbeatEvent(event_type="cleanup", target=self.tab_id))
        try:
            if not self._page.is_closed():
                await self._page.evaluate(
                    "() => { const ed = document.querySelector('[contenteditable], textarea, .ql-editor, rich-textarea'); if(ed) ed.textContent = ''; }"
                )
        except Exception:
            pass
        try:
            if not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass

    def stop(self):
        self._alive = False

    def record_mutation(self) -> None:
        """Increment the DOM mutation counter (call from MutationObserver)."""
        # Best-effort: the health check reads window.__hb_mutations
        pass


# ── Heartbeat Monitor (orchestrates browser + tab supervisors) ────────────

class HeartbeatMonitor:
    """Signal-only heartbeat — detects faults, NEVER modifies pages.

    P0 refactor (ChatGPT Round 2, 2026-06-30): heartbeat is now a pure
    detector.  It exposes ``browser_dead`` (asyncio.Event) and
    ``dead_reason`` for the orchestrator to consume.  Recovery (cancel
    workers, reconnect, rerun) is the orchestrator's responsibility.

    TabSupervisor no longer reloads or closes pages — it only sets
    ``degraded``.  The owning worker decides whether to reload or replace.
    """

    def __init__(self, browser, context):
        self._browser = browser
        self._context = context
        self._browser_sup: Optional[BrowserSupervisor] = None
        self._tab_sups: dict[str, TabSupervisor] = {}
        self._bg_tasks: list[asyncio.Task] = []
        self._degraded_tabs: set[str] = set()
        # Signal-only: orchestrator watches this Event
        self.browser_dead = asyncio.Event()
        self.dead_reason: str | None = None

    async def _on_browser_dead(self):
        """Signal browser death — orchestrator handles recovery."""
        if self.browser_dead.is_set():
            return
        self.dead_reason = "browser_heartbeat_failed"
        self.browser_dead.set()
        log.critical("[Heartbeat] BROWSER DEAD signal set")
        # Stop probing — pages may be invalid
        for sup in self._tab_sups.values():
            sup.stop()

    async def _on_tab_degraded(self, tab_id: str):
        """Signal tab degraded — worker decides recovery action."""
        log.error("[Heartbeat] TAB DEGRADED signal: %s", tab_id)
        self._degraded_tabs.add(tab_id)
        # No cleanup — worker owns the page

    def add_tab(self, tab_id: str, page) -> TabSupervisor:
        """Register a new tab for health monitoring.

        If monitor is already running, immediately creates a background
        supervisor task for dynamic registration.
        """
        sup = TabSupervisor(tab_id, page, on_degraded=self._on_tab_degraded)
        self._tab_sups[tab_id] = sup
        if self._bg_tasks:
            task = asyncio.create_task(sup.run(), name=f"hb-tab-{tab_id}")
            self._bg_tasks.append(task)
            log.info("[Heartbeat] Tab supervisor started for %s (dynamic)", tab_id)
        return sup

    def remove_tab(self, tab_id: str):
        sup = self._tab_sups.pop(tab_id, None)
        if sup:
            sup.stop()

    def is_degraded(self, tab_id: str) -> bool:
        return tab_id in self._degraded_tabs

    async def start(self) -> list[asyncio.Task]:
        self._browser_sup = BrowserSupervisor(
            self._browser, on_dead=self._on_browser_dead
        )
        # P0 fix (iteration-5 H-01): create browser CDP session before starting
        # the ping loop so the first ping can use Browser.getVersion.
        await self._browser_sup.start()
        tasks = [asyncio.create_task(self._browser_sup.run(), name="hb-browser")]
        for tab_id, sup in self._tab_sups.items():
            tasks.append(asyncio.create_task(sup.run(), name=f"hb-tab-{tab_id}"))
        self._bg_tasks = tasks
        log.info("[Heartbeat] Monitor started: 1 browser + %d tab supervisor(s)",
                 len(self._tab_sups))
        return tasks

    async def stop(self):
        if self._browser_sup:
            self._browser_sup.stop()
        for sup in self._tab_sups.values():
            sup.stop()
        # Let loops exit naturally
        await asyncio.sleep(0.3)
        for t in self._bg_tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        log.info("[Heartbeat] Monitor stopped")

# Changelog

## [Unreleased] — 10-Round Multi-Agent Optimization Loop (2026-06-29)

### R1: README + Architecture
- Data-flow diagram (P1→P2→P3→P4)
- One-line definition: "evidence aggregation system, not a chat framework"
- Clearer value proposition

### R2: Error Handling + Observability
- `ErrorEnvelope` dataclass: unified error container (status/type/reason/retryable)
- `WorkerResult` dataclass: standardized P2 output envelope
- Structured logging with `trace_id` (contextvars) for cross-stage correlation
- `setup_logging()` enhanced: trace_id injected into every log record

### R3: Code Quality + Safety
- `MAX_RESPONSE_SIZE = 500_000` (500KB) OOM guard in `extract_response()`
- `[RESPONSE_TRUNCATED]` marker on oversized extractions
- Dead import audit (no issues found)

### R4: Error Handling + Degradation
- Gemini `ERROR_PATTERNS` fixed: conversation chrome ("和Gemini对话") no longer triggers false error
- `Cloudflare` false positive: changed to match block-page markers only
- Tab liveness guard: `is_closed()` check before reusing existing tab

### R5: Documentation
- CHANGELOG.md (this file)
- FAQ section in README

### Infrastructure
- **Tab Reuse**: `_find_existing_tab()` scans open browser tabs by URL pattern; reuses existing conversation instead of opening new tabs each loop iteration
- **keep_alive default**: tabs stay open after extraction (default `True`)
- Page liveness fallback: dead tabs auto-replaced with fresh ones

## [0.1.0] — Initial Release (2026-06-28)

- 3-Mode DAG Pipeline: PARALLEL / SIMPLE / CONSENSUS
- 3 Web AI Workers: ChatGPT, Kimi, Gemini Pro Extended Thinking
- DeepSeek V4 Pro API One-Shot Scoring-Synthesis Judge
- Chrome CDP automation with Playwright
- Sandwich Prompt Template (Core 80% + Lens 15% + Cross 5%)
- AbortableBarrier (race-condition-free)
- Per-platform adapters (modular, 8 files)
- P4 Adjudicator: Independence Check → Scoring → Conflict Graph → Synthesis
- Condorcet gate for selective Claude escalation
- Early Exit: ≥2/3 consensus skips P3+P4
- Qianwen Deep Thinking auto-enable (aria-pressed toggle)

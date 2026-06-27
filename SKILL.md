# MultiAgent: 4-Phase Expert Pipeline with Gemini Final Adjudication

> **最后更新**: 2026-06-27 — Claude-as-Orchestrator + DeepSeek 后端正确定位

## Trigger

Use this skill when the user asks to:
- "问所有 AI" / "同时问 X 个平台" / "多平台对比"
- Get a final answer synthesized from multiple AI platforms
- Any complex technical question that benefits from multi-angle expert analysis

**Core pattern**: Claude Code (DeepSeek backend) orchestrates a 4-phase pipeline:
Claude decomposes → dispatches to 4 web experts → compresses → sends to Gemini for final judgment.

---

## Architecture

```
User Question
     │
     ▼
🟢 Phase 1: Claude Code (DeepSeek backend) — DIRECT LLM REASONING
   Analyzes request → generates 4 specialized prompts (JSON)
   Roles: chatgpt(代码效率), claude(防御架构), kimi(文献基准), qianwen(安全审计)
   Output: JSON file /tmp/multiagent_prompts.json
   ⚡ No browser — instant
     │
     ▼
🟡 Phase 2: 4 Expert Nodes — CONCURRENT (Playwright → Chrome tabs)
   $ python3 orchestrator.py phase2 /tmp/multiagent_prompts.json
   ┌──────────┬──────────┬──────────┬──────────┐
   │ ChatGPT  │ Claude   │ Kimi     │ Qianwen  │
   │ 代码效率  │ 防御架构  │ 文献基准  │ 安全审计  │
   └──────────┴──────────┴──────────┴──────────┘
   Hard timeout: 60s per platform. Barrier sync.
   🌐 Browser required — ~2 min
     │
     ▼
🟠 Phase 3: Claude Code (DeepSeek backend) — DIRECT LLM REASONING
   Reads Phase 2 results → compresses into structured matrix:
     [共识区 | Consensus]  — all-agreed points
     [特色区 | Features]   — unique contributions
     [冲突区 | Conflicts]  — disagreements
   Output: /tmp/multiagent_matrix.md
   ⚡ No browser — instant
     │
     ▼
🔴 Phase 4: Gemini 3.1 Pro Web — Playwright → Chrome tab
   $ python3 orchestrator.py phase4 /tmp/multiagent_matrix.md "task core"
   Extended Thinking → final judgment:
     - 综合结论 / 争议裁决 / 缝合方案 / 可信度评估
   🌐 Browser required — ~3-5 min
     │
     ▼
   Final Output (presented by Claude to user)
```

**Key insight**: Claude Code itself runs on DeepSeek's backend. Phase 1 and Phase 3 are performed by Claude Code directly — no browser, no DeepSeek web UI. Only Phase 2 (4 web platforms) and Phase 4 (Gemini web) need Playwright browser automation.

---

## Grand Orchestrator Workflow (MANDATORY)

When `/multiagent` is invoked, Claude MUST execute this sequence:

### Step 1: Decompose (Claude Code — no browser)

Analyze the user's request. Generate 4 specialized prompts, one per expert angle:

```json
{
  "task_core": "一句话核心目标",
  "worker_prompts": {
    "chatgpt": "从代码效率、算法优化、性能最佳实践角度...",
    "claude": "从防御性架构、错误处理、边界条件角度...",
    "kimi": "从学术文献、技术标准、基准测试角度...",
    "qianwen": "从安全审计、漏洞分析、竞态条件角度..."
  }
}
```

Write to `/tmp/multiagent_prompts.json`.

### Step 2: Dispatch (browser automation)

```bash
bash ~/connect-gemini.sh 2>&1 | tail -1  # ensure Chrome ready
python3 ~/.claude/skills/multiagent/orchestrator.py phase2 --file /tmp/multiagent_prompts.json --timeout 60 --json > /tmp/multiagent_p2_results.json
```

### Step 3: Compress (Claude Code — no browser)

Read `/tmp/multiagent_p2_results.json`. Analyze the 4 responses. Produce a structured matrix:

```markdown
## 共识区 | Consensus
[所有平台一致同意的观点，逐条标注来源]

## 特色区 | Features
[各平台独特贡献，标注来源]

## 冲突区 | Conflicts
[存在分歧的观点，明确标注冲突双方]
```

Write to `/tmp/multiagent_matrix.md`.

### Step 4: Adjudicate (browser automation)

```bash
python3 ~/.claude/skills/multiagent/orchestrator.py phase4 --file /tmp/multiagent_matrix.md "TASK_CORE_SUMMARY"
```

### Step 5: Present

Read Gemini's final output. Present to user. Add meta-commentary if helpful (e.g., which platform contributed what, any notable disagreements).

---

## Quick Reference

```bash
# Phase 2: dispatch 4 prompts concurrently
python3 orchestrator.py phase2 '{"chatgpt":"...","claude":"...","kimi":"...","qianwen":"..."}'
python3 orchestrator.py phase2 --file prompts.json --timeout 45

# Phase 4: Gemini adjudication
python3 orchestrator.py phase4 "matrix text" "task core"
python3 orchestrator.py phase4 --file matrix.md "task core"
```

---

## Platform Maturity

| Platform | Status | DOM Injection | Extraction | Pipeline Role |
|----------|--------|---------------|------------|---------------|
| **Gemini** | ⭐⭐⭐⭐⭐ | ✅ insertText | ✅ model-message | P4 终审裁决 (Pro Extended Thinking) |
| **ChatGPT** | ⭐⭐⭐⭐ | ✅ insertText | ✅ assistant role | P2 代码效率专家 |
| **Claude** | ⭐⭐⭐ | ✅ insertText | ⚠️ fallback | P2 防御架构专家 (free tier rate-limit) |
| **Kimi** | ⭐⭐⭐ | ✅ insertText | ✅ chat-content-item | P2 文献基准专家 |
| **Qianwen** | ⭐⭐⭐ | ✅ insertText | ✅ [class*=message] | P2 安全审计专家 |
| **DeepSeek** | — | — | — | P1+P3 via Claude Code backend (no web) |
| ~~Doubao~~ | 🚫 | — | — | Deprecated 2026-06-27 |

---

## Degradation Chain

| Phase | Failure | Fallback |
|-------|---------|----------|
| P1 | — | Claude generates default angle-prefixed prompts |
| P2 | 1+ platform timeout/crash | Partial extraction, continue with remaining |
| P2 | ALL 4 fail | Report failure, ask user if they want to retry |
| P3 | — | Claude can still reason over partial results |
| P4 | Gemini unreachable | Claude presents Phase 3 matrix as final output |
| P4 | Pro Extended fails | Proceed with default Gemini mode |

---

## File Structure

```
~/.claude/skills/multiagent/
├── SKILL.md           # This file (Claude-as-Orchestrator workflow)
├── orchestrator.py    # Phase 2 + Phase 4 browser automation tool
├── main.py            # Original flat 7-platform controller (backward compat)
├── adapters.py        # BaseAdapter + 7 concrete adapters
└── requirements.txt   # Python deps (playwright)
```

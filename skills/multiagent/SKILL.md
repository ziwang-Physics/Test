# MultiAgent: 3-Mode DAG Pipeline + DeepSeek One-Shot Judge

> **最后更新**: 2026-07-01 — ChatGPT 重设计架构流程图 + 9 轮对抗审查记录
> **验证**: 20+ 轮 loop 迭代，100+ 次独立专家评估，9 轮 ChatGPT+Gemini 联审
> **架构**: 问题拆解 → 并行(Kimi+Gemini+GPT) / 串行(Gemini→GPT→Claude→...→豆包) → DeepSeek 裁决

---

## 决策分工与能力边界（CRITICAL）

整个系统由三类角色协作完成，各自的能力边界和决策权限必须严格区分：

### 角色分工

| 角色 | 运行环境 | 能做什么 | 不能做什么 |
|------|---------|---------|-----------|
| **Claude Code (本地)** | 用户机器，有文件系统+Shell | 读写本地文件、编译运行代码、操控 Chrome 浏览器、提交 Git、推送代码 | 无法独立判断代码逻辑是否正确（需要 Web AI 审查） |
| **Web AI (ChatGPT/Gemini)** | 浏览器云端，只能通过网页交互 | 访问 GitHub 仓库阅读代码、搜索网页获取最新资料、分析代码逻辑、找出 bug、提出改进方案 | **看不到本地文件**、看不到运行中进程、看不到浏览器操控日志、不能执行代码、不能修改文件 |
| **DeepSeek API (P4 裁决)** | API 调用 | 单次评分、冲突仲裁、证据合成 | 无浏览器、无文件系统 |

### 核心原则

1. **Web AI 是"代码审查员"，不是"执行者"**：ChatGPT 和 Gemini 只负责阅读 GitHub 上的代码、找出问题、提出改进方案。它们不能修改任何文件。
2. **Claude Code 是"执行者"，不是"决策者"**：Claude Code 负责把 Web AI 的审查意见落地为代码修改、编译验证、提交推送。不应自行决定修改方向。
3. **每一轮对话前，Claude Code 必须将上一轮遇到的问题（浏览器操控失败、模式切换失败、响应为空、超时等）如实告知 Web AI**。Web AI 只有在了解实际运行情况后才能精准诊断。
4. **GitHub 是唯一的信息桥梁**：Web AI 只能通过 GitHub 仓库看到代码。每次修改后必须立即推送，否则 Web AI 看到的是过时代码。
5. **迭代闭环**：Web AI 审查 → Claude Code 实施修复 → Push 到 GitHub → 下一轮 Web AI 看到新代码+上一轮问题 → 继续审查。不可跳过任何一步。

### 一轮完整的协作流程

```
1. Claude Code 把本轮审查焦点 + 上一轮遇到的浏览器问题 → 写成 prompt
2. Prompt 通过 Chrome CDP 注入到 ChatGPT 和 Gemini 网页
3. ChatGPT/Gemini 访问 GitHub 阅读代码，搜索网页，给出审查报告
4. Claude Code 提取审查报告中的关键发现
5. Claude Code 实施最优先的修复 → 编译验证
6. Git commit + push 到 GitHub（让下一轮 Web AI 看到最新代码）
7. 记录本轮遇到的问题（模式失败、超时、崩溃等）→ 传给下一轮 prompt
8. 重复 1-7
```

---

## Web AI 对抗性审查记录（ChatGPT + Gemini 联审）

> 2026-06-30 ~ 07-01，9 轮迭代审查，ChatGPT 稳定产出 12,000-15,000 字符/轮，Gemini R5 起稳定产出 3,000-5,000 字符/轮。

### 审查机制

每轮：ChatGPT（工程实践视角）+ Gemini（推理深度视角，强制 Pro Extended Thinking）→ 访问 GitHub 阅读代码 → 独立给出审查报告 → Claude Code 提取建议 → 实施修复 → Push → 下一轮看到新代码。

### 关键发现与修复

| 轮次 | 发现 | 级别 | 修复状态 |
|------|------|------|---------|
| R1 | 异常路径用 `len(partial)>20` 判定成功——登录页、错误页被当答案 | P0 | ✅ 已修复 |
| R1 | `UI_CHROME_DOMINANT` 进入 quorum——页面 UI 文本被当证据 | P0 | ✅ 已修复 |
| R1 | `body.textContent` 作为兜底答案——整页 HTML 可能进入裁决 | P0 | ✅ 已修复 |
| R2 | Gemini baseline 类型断裂——base.py 返回 dict，组件仍当 int 用，`i>=NaN` | P0 | ✅ 已修复 |
| R3 | Gemini Extended 验证失败——aria-label 不更新，乐观验证加入 | P0 | ✅ 已修复 |
| R3 | 页面替换后租约和心跳未迁移——孤儿 Tab 累积 | P0 | 🔄 部分修复 |
| R4 | 乐观验证生效——Gemini 从 THINKING_MODE_FAILED 变为可发送 | — | ✅ 已验证 |
| R5 | **Gemini 首次成功**——诊断 Extended Thinking 完成检测缺陷 | — | ✅ 里程碑 |
| R5 | DOM 静默检测在 ET 30-90s 推理期间误判完成 | P0 | ⏳ 待修复 |
| R6 | Gemini 建议：用 UI 状态机(停止按钮+工具栏)替代 DOM 防抖 | P0 | ⏳ 待修复 |
| R7 | ChatGPT R6 "FATAL" 证实为日志误报 | — | ✅ 已澄清 |
| R8 | Deadline 仍用 `time.time()` 非单调钟、关键路径未接入 | P0 | ⏳ 待修复 |
| R8 | AbortableBarrier 取消路径残留"幽灵参与者" | P1 | ⏳ 待修复 |
| R9 | main.py vs orchestrator.py 两套生命周期、退出码不一致 | P1 | ⏳ 待修复 |

### Gemini Extended Thinking 启用历程

```
R1-R3: THINKING_MODE_FAILED → 模式验证 aria-label 不更新
    ↓ R3 修复：文本定位器点击 + 乐观验证
R4: 模式通过，但响应空 → DOM 静默检测过早触发
    ↓ R5 诊断：ET 内部推理 30-90s 无 DOM 变化
R5-R9: 稳定产出 3000-5000 字符 ✅
```

### 已知待修复（优先级排序）

1. **DOM 静默检测 → UI 状态机**：Extended Thinking 期间用停止按钮/工具栏替代纯文本长度防抖
2. **Deadline monotonic 时钟**：`time.time()` → `time.monotonic()`，接入关键路径
3. **页面替换原子化**：`_replace_page()` 统一迁移 lease + heartbeat
4. **quorum 语义严格化**：分离 transport_completed / validated / quorum_met
5. **P4 结构化返回**：不再返回空字符串表示所有失败

---

## Prerequisites

| Dependency | Minimum Version | Check Command |
|-----------|----------------|---------------|
| Python | ≥ 3.10 | `python3 --version` |
| Playwright | ≥ 1.45 | `python3 -m playwright --version` |
| Chromium | ≥ 125 (for CDP token) | `chromium --version` |
| Chrome Debug Profile | `~/.chrome-debug-profile/` | `ls ~/.chrome-debug-profile/.cdp_token` |
| CHROME_CDP_TOKEN | auto-generated on Chrome start | `cat ~/.chrome-debug-profile/.cdp_token` |

**First-time setup**: `python3 -m playwright install chromium`

---

## Trigger

### Activate this skill when:

**Explicit triggers** (user mentions any of these):
- "问所有 AI" / "同时问 X 个平台" / "多平台对比" / "多AI"
- "综合所有回答" / "多角度分析" / "cross-reference with other AIs"
- "ask all AIs" / "compare platforms" / "multi-model" / "multi-agent"
- "/multiagent" slash command

**Implicit triggers** (auto-activate when the question matches these patterns):
- Complex reasoning with competing valid approaches (architecture trade-offs, method selection)
- Questions where different AI platforms are known to give materially different answers
- Research strategy / paper publication strategy questions (multi-angle expert analysis needed)
- System design questions with security + performance + correctness trade-offs

### Do NOT trigger for:
- Simple factual lookup (e.g., "what is the capital of France")
- Single-sentence answers ("一句话说说量子点")
- Code syntax questions with one correct answer
- Questions answerable by reading a single file or config

### Priority rule:
- This skill has priority over single-model QA skills when the question matches implicit triggers
- If another skill already handles the request type (e.g., HPC cluster operations), do NOT override

---

## Architecture（ChatGPT 设计 v2）

```
┌──────────────────────────────────────────────────────────────────┐
│                          用户提问                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      问题拆解 Agent                              │
│         拆分任务、识别依赖关系、判断子问题是否完全独立           │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ 子问题是否完全独立？ │
                    └─────────┬───────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
               是│                         │否
                 ▼                         ▼
┌─────────────────────────────┐  ┌─────────────────────────────────┐
│         并行模式            │  │          串行模式               │
│  多模型同时处理独立子问题   │  │ 按顺序调用，失败或额度用尽递补  │
└─────────────┬───────────────┘  └────────────────┬────────────────┘
              │                                    │
    ┌─────────┼─────────┐                          ▼
    ▼         ▼         ▼             ┌──────────────────────────┐
┌────────┐┌────────┐┌────────┐       │ Gemini                   │
│ Kimi   ││Gemini  ││ChatGPT │       │ Pro Extended Thinking    │
│搜索资料││Pro     ││直接回答│       │ 多模态分析与深度推理     │
│文献基准││Extended││工程实践│       └───────────┬──────────────┘
└───┬────┘│Thinking│└───┬────┘                   │
    │     │多模态  │    │                   失败或额度用尽
    │     └───┬────┘    │                        ▼
    │         │         │             ┌──────────────────────────┐
    └─────────┼─────────┘             │ ChatGPT                  │
              │                       │ 直接回答与工程实践       │
              │任一失败或额度用尽      └───────────┬──────────────┘
              ▼                                  │
┌───────────────────────────┐               失败或额度用尽
│      并行模式替补池       │                    ▼
│ Qwen → MiniMax → Doubao  │         ┌──────────────────────────┐
│ 按顺序自动递补空缺模型    │         │ Claude                   │
└─────────────┬─────────────┘         │ 补充分析与复杂推理       │
              │                       └───────────┬──────────────┘
              │                                  │
              │                             失败或额度用尽
              │                                  ▼
              │                       ┌──────────────────────────┐
              │                       │ Qwen                     │
              │                       │ 第一替补                 │
              │                       └───────────┬──────────────┘
              │                                  │
              │                             失败或额度用尽
              │                                  ▼
              │                       ┌──────────────────────────┐
              │                       │ MiniMax                  │
              │                       │ 第二替补                 │
              │                       └───────────┬──────────────┘
              │                                  │
              │                             失败或额度用尽
              │                                  ▼
              │                       ┌──────────────────────────┐
              │                       │ Doubao                   │
              │                       │ 最终替补                 │
              │                       └───────────┬──────────────┘
              │                                  │
              └──────────────┬───────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    汇总所有有效模型结果                          │
│             去重、校验、保留共识、差异与冲突证据                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        DeepSeek API                              │
│              统一评分、冲突裁决、综合生成最终结论                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                          最终答案                                │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    底层浏览器自动化层                            │
│          Chrome CDP + Playwright：页面连接、模型操控、           │
│          消息发送、结果提取、额度检测、Tab 管理与清理            │
└──────────────────────────────────────────────────────────────────┘
```

### 两种执行路径

**并行模式**（子问题相互独立）：
| 模型 | 职责 | 备注 |
|------|------|------|
| Kimi | 搜索网页资料、文献基准 | — |
| Gemini | 多模态推理 | **必须启用 Pro Extended Thinking** |
| ChatGPT | 直接回答、工程实践 | — |
| 替补池 | Qwen → MiniMax → Doubao | 任一模型额度用尽时自动递补 |

**串行模式**（子问题不独立）：
| 优先级 | 模型 | 说明 |
|--------|------|------|
| 1 | Gemini (Pro Extended Thinking) | 首选用深度推理 |
| 2 | ChatGPT | 额度用尽时递补 |
| 3 | Claude | 额度用尽时递补 |
| 4 | Qwen | 第一替补 |
| 5 | MiniMax | 第二替补 |
| 6 | Doubao | 最终替补 |

获得有效答案即停止，不继续后续模型。

---

## Grand Orchestrator Workflow (MANDATORY)

### Pre-flight check:
```bash
# 1. CDP token must exist
test -f ~/.chrome-debug-profile/.cdp_token || { echo "ERROR: Chrome CDP token not found. Run: bash ~/connect-gemini.sh"; exit 1; }
export CHROME_CDP_TOKEN=$(cat ~/.chrome-debug-profile/.cdp_token)
# 2. Token file permissions must be 0600
test "$(stat -c %a ~/.chrome-debug-profile/.cdp_token)" = "600" || chmod 600 ~/.chrome-debug-profile/.cdp_token
# 3. CDP must bind to localhost only (P1: DNS rebinding hardened check)
python3 -c "from common import verify_cdp_safe; ok, msg = verify_cdp_safe(); print(msg); exit(0 if ok else 1)" || { echo "ERROR: CDP unsafe — must bind 127.0.0.0/8 only"; exit 1; }
# 4. /tmp disk space >= 10MB
test $(df -m /tmp | awk 'NR==2{print $4}') -ge 10 || { echo "ERROR: /tmp disk full"; exit 1; }
```

### Step 1: Decompose & Route (Claude Code — no browser)

**RoutingState 评估器**: 分析请求，输出三维特征 `{complexity, uncertainty, structure_need}` + 模式选择。

- **PARALLEL (默认，>90% 查询)**: 生成 3 个 lens prompt。`complexity ≥ 0.3 OR uncertainty ≥ 0.3 → PARALLEL`
- **SIMPLE (极罕见)**: 1 worker 直接回答。`complexity < 0.3 AND uncertainty < 0.3` (如 "1+1=?" / "北京在哪")
- **CONSENSUS (升级触发，非初始选择)**: 仅由 P3 检测 PARALLEL 分歧后升级

**Sandwich Prompt Template (PARALLEL 模式)**:

```
Layer 1 — Core Question (完全同化, ~80%):  所有平台一字不差的核心问题，占 prompt 主体
Layer 2 — Primary Lens  (特性锐度, ~15%):  一句简短视角指令，轻微引导分析方向
Layer 3 — Cross-Coverage (交叉补位, ~5%):  一个短语提示覆盖其他维度，仅作兜底
```

**Rationale**: Core Question 占 80% 确保所有 AI 围绕相同的核心问题回答——这是 P3 共识/冲突提取的前提。3 个视角（工程/文献/推理）互补无重叠。Primary Lens 仅提供方向性微调。Cross-Coverage 降为一个短语，覆盖其余 2 个视角。

**Sandwich Prompt Template:**

```json
{
  "task_core": "one-sentence summary (max 120 chars)",
  "worker_prompts": {
    "chatgpt": "【核心问题】<完全相同的 question，占主体> （附加视角：侧重工程实践与代码效率。请自行搜索网页获取最新资料。简略带过安全防御、推理深度。）",
    "qianwen": "【核心问题】<完全相同的 question，占主体> （附加视角：侧重安全与防御性架构分析，请搜索网页验证。简略带过工程实践、推理深度。）",
    "gemini": "【核心问题】<完全相同的 question，占主体> （附加视角：侧重推理深度与逻辑一致性。请自行搜索网页获取最新资料。简略带过工程实践、安全防御。）"
  }
}
```

**Why 3 workers (not 5)**: 实测数据 — ChatGPT ~100% 可用, Kimi ~95%, Gemini ~80%。Claude 免费额度 ~85% 不可用；Qianwen 安全视角在非安全场景中边际贡献极低。3 视角 (工程/文献/推理) 互补无重叠，降低 CDP 并发内存 40%，P2 耗时从 ~75s 降到 ~50s，共识判定从 2/5 弱共识变 2/3 强共识。

**Replacement rules for `<完全相同的 question>`:**
- Insert the user's actual question verbatim, NOT a rephrased version
- If the question is long (>200 chars), use the `task_core` summary instead
- The question block is identical across all 4 platforms — no variation

**Cross-Coverage weight rule:**
- Cross-coverage is a single parenthetical phrase after the core question — one sentence total
- Total cross-coverage ≤ 5% of prompt length — the core question dominates
- Primary Lens is ~15% — one clause steering the angle, not a full paragraph
- If the AI ignores Lens/Cross-Coverage entirely, the core question answer alone is still complete

Write to `$WORKDIR/prompts.json`.

### ⚠️ 铁律 (MUST — never skip)

1. **GitHub URL**: 必须传 `https://github.com/ziwang-Physics/Test` 给 AI，绝不传本地路径
2. **Gemini Extended Thinking**: 每次 P2 **必须**启用 Pro Extended Thinking（`ensure_pro_extended()`），不可降级
3. **Wait ALL**: 等所有 AI 完全生成完毕（toolbar/stability 确认），不截断

### Step 2: Dispatch (browser automation)
```bash
python3 ~/.claude/skills/multiagent/orchestrator.py phase2 \
  --file "$WORKDIR/prompts.json" --timeout 600 --json > "$WORKDIR/p2_results.json"
```

### Step 3: Compress (Claude Code — no browser)
Read `$WORKDIR/p2_results.json`. Produce matrix with **共识区/特色区/冲突区** H2 sections. Write to `$WORKDIR/matrix.md`.

### Step 3.5: Early Exit (PARALLEL consensus check)

Before P3 compression, check if P4 is even needed:

```
if consensus_ratio >= 2/3 AND synthesis_confidence >= 0.7:
    → 跳过 P3+P4，直接输出多数答案
else:
    → 进入 P3 矩阵压缩 → P4 裁决
```

### Step 4: Adjudicate — One-Shot Scoring-Synthesis Judge (DeepSeek V4 Pro API)

Single API call. Internal steps executed in one prompt:

1. **Independence Check Gate**: 检测 3 个 worker 输出语义相似度 >0.85 → 判定"伪多数"，阻断合成
2. **Scoring**: 每 worker 评分 0-10 (正确性/完整性/一致性/简洁性)
3. **Conflict Graph**: 提取事实断言建矛盾图 → 最大自洽子图选边 → 不做平均/妥协
4. **Synthesis**: 融合高置信片段 → 输出最终答案 + 证据链 + 弃用观点+原因

**CONSENSUS 升级 (P4 置信不足时)**:

```
P4 confidence < 0.7:
    │
    ├─ Condorcet 门控: 评估任务难度 → p 值
    │   p < 0.5 (困难): 禁止横向扩展
    │       → P4 切换 Long CoT / Tree of Thoughts 深度推理
    │   p > 0.5: 选择性激活备选池
    │       → +Claude (Sonnet 4.6)
    │       → 3 core + 1 spare = 4 workers 重跑一轮
    │       → 最多扩展至 5 (含 MiniMax，排除豆包 deprecated)
    │
    └─ 新结果 → P4 One-Shot Judge 再次裁决 → 最终输出
```

**动态 p 阈值**: 基于任务域历史精度 (JudgeBench 基准: GPT-4o 跨域精度 Knowledge 44.2% ~ Math 66.1%)。零样本 log-probability 作为实例级代理。固定 0.5 不可行——跨域差 >20pp。

> **P1 upgrade (2026-06-28)**: Replaced Gemini Web CDP with DeepSeek V4 Pro API.
> Zero DOM dependency, 100% injection success, second-level latency.
> API key from `$DEEPSEEK_API_KEY` env var.

```bash
python3 ~/.claude/skills/multiagent/orchestrator.py phase4 \
  --file "$WORKDIR/matrix.md" \
  --prompts-file "$WORKDIR/prompts.json"
```

### Step 5: Present + Cleanup
Read Gemini's output. Present to user. Run `rm -rf "$WORKDIR"`.

---

## Degradation Chain

| Phase | Failure | Fallback |
|-------|---------|----------|
| Pre-flight | Chrome not running / token missing | Run `bash ~/connect-gemini.sh`, retry once |
| Pre-flight | /tmp disk < 10MB | Alert user, suggest `export TMPDIR=/var/tmp` |
| P1 | — | Claude generates default angle-prefixed prompts |
| P2 | 1+ platform timeout | Partial text extraction, `[WARNING: NODE_TIMEOUT_TRUNCATED]` prefix, continue |
| P2 | 1+ platform crash/exception | Continue with remaining workers |
| P2 | ALL 3 fail | Report to user: "All 3 expert nodes failed. Check network/proxy. Retry? (y/n)" |
| P3 | — | Claude can still reason over partial P2 results |
| P3.5 | PARALLEL consensus ≥2/3 → skip P4 | Early exit, majority answer returned directly |
| P4 | DeepSeek API unreachable / 5xx | Retry with exponential backoff (3 attempts), then present P3 matrix |
| P4 | DEEPSEEK_API_KEY not set | Present P3 matrix, note degradation |
| P4 | confidence < 0.7 + Condorcet p>0.5 | Selective escalation: +Claude → rerun → P4 again |
| P4 | confidence < 0.7 + Condorcet p<0.5 | No expansion: P4 Long CoT deep reasoning |
| Escalation | Claude 免费额度耗尽 | Fall back to original 3-worker P4 result，note partial coverage |

---

## File Structure

```
~/.claude/skills/multiagent/
├── SKILL.md                  # This file (workflow)
├── common.py                 # Shared: cdp_url(), AbortableBarrier, setup_logging()
├── orchestrator.py           # Phase 2 + Phase 4 browser automation
├── main.py                   # Standalone 7-platform controller (backward compat)
├── adapters.py.bak           # Pre-optimization monolithic file (kept for reference)
├── requirements.txt          # playwright>=1.45
├── adapters/                 # Per-platform adapter package
│   ├── __init__.py           # Registry + exports
│   ├── base.py               # BaseAdapter (connect/inject/extract/validate)
│   ├── chatgpt.py            # ChatGPTAdapter (P2 worker: 工程实践+搜索)
│   ├── qianwen.py            # QianwenAdapter (P2 worker: 安全防御+搜索)
│   ├── gemini.py             # GeminiAdapter (P2 worker: 推理深度+搜索 + P4 fallback)
│   ├── kimi.py               # KimiAdapter (备用 — 思考太慢)
│   ├── claude.py             # ClaudeAdapter (首选备选 — CONSENSUS升级时选择性激活)
│   ├── qianwen.py            # QianwenAdapter (P2 worker: 安全防御+搜索)
│   ├── deepseek.py           # DeepSeekAdapter (Expert + Deep Think)
│   └── _deprecated.py        # DoubaoAdapter (manual opt-in only)
└── reference/
    └── platform-maturity.md  # Platform maturity levels + adapter details
```

## P0 Fixes Applied (2026-06-28)

1. **Barrier.abort() 竞态条件**: `abort()` 改为 async，内部持有 `Condition` 锁后设标志 + `notify_all()`
2. **CDP token 三处重复去重**: 统一到 `common.cdp_url()`
3. **main.py Barrier 升级**: 使用 `AbortableBarrier` (带 timeout + abort)
4. **adapters.py 模块化**: 33KB 拆分为 8 个 per-platform 文件
5. **clean_response() 误伤修复**: 噪声模式匹配增加行长度守卫
6. **inject_prompt() 短提示修复**: <50 字符跳过完整性检查
7. **P4 裁决提示去 HPC 化**: 使用通用裁决原则
8. **硬编码延迟常量化**: 统一在 `common.py` 定义

## P1 Production Upgrades (2026-06-28)

9. **verify_cdp_safe DNS rebinding 防护**: 解析 localhost → 验证 IP ∈ 127.0.0.0/8 或 ::1
10. **innerText → textContent 迁移**: 无 Reflow + Shadow DOM 穿透 + 更高性能
11. **safe_page() RAII 上下文管理器**: 三层清理 page.close → suppress(PlaywrightError)
12. **Fire-and-collect 替代 Barrier**: asyncio.wait() 独立 worker，消除人工同步点
13. **Gemini Pro Extended v3**: gem-menu-item 选择器 + Angular CDK polling + aria-label 幂等守卫
14. **Shell 注入消除**: --prompts-file 替代 shell 命令替换
15. **CLAUDE.md 凭据清除**: 硬编码密码 → 环境变量引用

## P1 Upgrades (2026-06-28 — continued)

16. **Qianwen Deep Thinking 自动开启**: `ensure_thinking_mode()` 基于 aria-pressed 幂等守卫，每次 P2 千问 tab 自动点击"思考"按钮启用深度推理模式
17. **BaseAdapter.ensure_thinking_mode()**: 通用 no-op hook，各平台按需覆盖 (Qianwen 点击 toggle，Gemini 委托 `ensure_pro_extended`，其他平台默认跳过)

## P1 Upgrades (2026-06-28 — continued #2)

18. **P4 裁决者切换 DeepSeek V4 Pro API**: 替换 Gemini Web CDP → 直接 API 调用 (Anthropic-compatible Messages endpoint)，零 DOM 依赖/零注入失败/秒级延迟，API key 从 `$DEEPSEEK_API_KEY` 环境变量读取
19. **P2 新增 Gemini 3.1 Pro Extended Thinking Worker**: 第 5 个 P2 并行节点，角色"推理深度与逻辑一致性"，利用 Extended Thinking 的链式推理能力补足 Claude 免费额度经常不可用的防御架构视角

## P1 Upgrades (2026-06-28 — continued #3)

20. **P2 Workers 5→3 精简**: 基于 7 轮实测数据 — Claude ~85% 不可用，Qianwen 非安全场景边际极低。保留 ChatGPT(~100%) + Kimi(~95%) + Gemini(~80%)。CDP 内存降 40%，P2 从 ~75s→~50s。Claude/Qianwen adapter 保留备用。

## P1 Upgrades (2026-06-28 — continued #4)

21. **CONSENSUS One-Shot Scoring-Synthesis Judge**: P4 DeepSeek 单次调用内完成 Independence Check → Scoring → Conflict Graph → Synthesis。不做多轮辩论，O(1) 收敛。≤40 行实现。
22. **Condorcet 选择性门控**: P4 置信 <0.7 时：p<0.5(困难) → P4 Long CoT；p>0.5 → +Claude 扩展。动态 p 阈值，最多扩展至 5 worker。CARGO 文献证实选择性激活省 40% 计算。
23. **PARALLEL 默认模式**: >90% 查询走 PARALLEL(3 路并发 lens prompt)。SIMPLE 仅极简单事实查询。CONSENSUS 仅 PARALLEL 分歧 <2/3 时触发。
24. **Early Exit**: PARALLEL 一致性 ≥2/3 AND 置信 ≥0.7 → 跳过 P3+P4，直接输出多数答案。
25. **Thinking Selector 提取时机修复**: `base.py` stability fallback 加 thinking 标识检测。Kimi (`[class*="typing"]`)、Qianwen (`button[aria-label*="停止"]`)、Gemini (`mat-spinner`) 各定义 `THINKING_SELECTOR`。阻断搜索/思考中间态被误判为完成。

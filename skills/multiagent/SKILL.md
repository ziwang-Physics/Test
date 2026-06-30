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

> 状态核对于 R13 (2026-06-30)，对照实际代码：

1. ✅ **DOM 静默检测 → UI 状态机**：已在 `adapters/components/gemini_completion.py` 落地 SENDING→GENERATING→THINKING→COMPLETE 状态机（toolbar 锚点，R10/R12）。通用 `base.wait_response` 仍用文本长度防抖。
2. ✅ **Deadline monotonic 时钟**：`common.Deadline` 已用 `loop.time()` 单调钟并接入 `_p2_worker`。⚠️ `phase2_dispatch` 外层 `asyncio.wait(timeout=timeout_s+60)` 仍用裸相对值，未走 Deadline。
3. ⏸️ **tab 复用：管线已通，但已禁用（R15 真机 smoke test 发现）**：lease/heartbeat/retry 迁移的底层改动（`_lease_and_monitor`、retry 时迁移 lease+heartbeat、`_p2_worker` 各 page 分支统一获取 lease）**已生效**，覆盖 always-fresh 路径。但 `phase2_dispatch` 传 `existing_page=_find_existing_tab(...)` 那行**已回退**——真机测试发现复用 ChatGPT 对话 tab 时，导航到 base URL 不会真正开新对话，fallback 提取器抓到用户自己的 prompt 气泡（`你说：<prompt>`）→ 每次复用都 `PROMPT_ECHO_DOMINANT`，retry 的 fresh tab 也失败；fresh tab 稳定。**复用代码保留在 `_p2_worker`**（正确但未激活），等 ChatGPT adapter 学会复用时点「新对话」、并把 `RESPONSE_STRATEGIES` 收紧到 assistant 角色后再开启。`_replace_page()` 仍未单独编写（轮换路径已覆盖其意图）。
4. **quorum 语义严格化**：分离 transport_completed / validated / quorum_met（仍待办）。（R13 已修：`run_parallel_route` 的 quorum 不再被 fallback 成功虚高。）
5. **P4 结构化返回**：`phase4_adjudicate` 仍用空字符串表示所有失败（仍待办）。（R13 已修：P4 的 indirect-prompt-injection 缓解从"文档声称、代码未生效"改为真正生效——judge 规则在 `system`、evidence 以 `<evidence>` JSON 进入 user 消息。）

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

## 快速使用

### 端到端运行（推荐）
```bash
cd skills/multiagent

# 自动路由（DeepSeek 判断并行/串行）
python3 orchestrator.py run "你的问题"

# 强制并行模式
python3 orchestrator.py run "你的问题" --mode parallel

# 强制串行模式
python3 orchestrator.py run "你的问题" --mode serial

# JSON 输出
python3 orchestrator.py run "你的问题" --json

# 自定义超时
python3 orchestrator.py run "你的问题" --timeout 300
```

### 分步执行
```bash
# Phase 2: 手动控制 Worker
python3 orchestrator.py phase2 --file prompts.json --json

# Phase 4: 手动裁决
python3 orchestrator.py phase4 --file matrix.md --prompts-file prompts.json
```

### 执行模式

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **auto** (默认) | DeepSeek 路由器判断 | 独立子问题→并行(Kimi+Gemini+ChatGPT)；有依赖→串行链 |
| **parallel** | --mode parallel | 强制 3 Worker 并行 + 替补池 |
| **serial** | --mode serial | 严格串行链 Gemini→ChatGPT→Claude→Qwen→MiniMax→Doubao |

---

## 降级策略

| 场景 | 处理 |
|------|------|
| DeepSeek 路由器不可用 | 自动回退为 3 Worker 并行模式 |
| 并行模式 Worker 失败 | 替补池 Qwen→MiniMax→Doubao 1:1 递补 |
| 串行模式当前阶段失败 | 自动跳到下一平台，继承上次成功输出 |
| DeepSeek 裁决不可用 | 最佳努力答案，标记 `⚠️ 降级答案` |
| Web AI 额度用尽 | 自动检测并递补下一模型 |
| Chrome CDP 断开 | ConnectionManager 自动重连，epoch 隔离 |

---

## File Structure

```
~/.claude/skills/multiagent/             # skill root (git repo)
├── SKILL.md                             # symlink → skills/multiagent/SKILL.md (this doc)
├── README.md  CHANGELOG.md              # user + change docs
├── scripts/                             # connect-gemini.sh, start-chrome-debug.{sh,py}
└── skills/multiagent/                   # ← all Python code lives here (cd here to run)
    ├── SKILL.md                         # the real workflow doc
    ├── common.py                        # PlatformId, Deadline, AbortableBarrier, cdp_url, ErrorInfo, setup_logging
    ├── connection.py                    # ConnectionManager (browser_epoch) + PageLeaseRegistry
    ├── heartbeat.py                     # HeartbeatMonitor / BrowserSupervisor / TabSupervisor
    ├── router.py                        # decompose_and_route + parallel/serial pipeline (run_pipeline)
    ├── orchestrator.py                  # phase2_dispatch + phase4_adjudicate + CLI
    ├── main.py                          # Legacy standalone multi-platform controller (--route delegates to router)
    ├── adapters.py.bak                  # Pre-modularization monolith (reference only)
    ├── pyproject.toml  requirements.txt # pytest config / playwright>=1.45
    ├── adapters/                        # Per-platform adapter package
    │   ├── __init__.py                  # ADAPTER_REGISTRY + PLATFORM_MATURITY
    │   ├── base.py                      # BaseAdapter (connect/inject/extract/validate)
    │   ├── chatgpt.py  claude.py  gemini.py  kimi.py  qianwen.py
    │   ├── deepseek.py  minimax.py  doubao.py
    │   ├── _deprecated.py               # legacy DoubaoAdapter (manual opt-in)
    │   └── components/                  # Protocol-based Gemini drivers
    │       ├── protocols.py  gemini_editor.py  gemini_completion.py
    │       └── gemini_extraction.py  gemini_mode.py
    ├── reference/platform-maturity.md   # Platform maturity levels + adapter details
    └── tests/  (contracts/  unit/)      # adapter-contract + platform-id / circuit-breaker tests
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

# AgentChat

> 基于浏览器自动化的多 Web LLM 证据采集、协作推理与独立裁决系统。

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-CDP-2EAD33?logo=playwright&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active-success)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## 概述

AgentChat 不是让多个模型轮流发言的聊天界面。它将不同的 Web LLM 视为**相互独立、可能失败、可能冲突的证据源**，通过 Playwright 连接本地 Chrome DevTools Protocol 会话，并发采集多个平台的回答，再将结果压缩为可审计的证据矩阵，最后交给 DeepSeek API 完成评分、仲裁与最终合成。

一次标准任务由四个阶段组成：

| 阶段 | 名称 | 职责 |
|------|------|------|
| P1 | 问题分解 | 提取任务核心，为不同 Worker 生成差异化视角提示词 |
| P2 | 并发采集 | 通过 CDP 驱动 ChatGPT、Kimi、Gemini 并发回答并校验质量 |
| P3 | 证据压缩 | 整理共识区、特色区和冲突区，形成结构化矩阵 |
| P4 | 独立裁决 | DeepSeek V4 Pro API 完成评分、冲突仲裁与答案合成 |

---

## 核心设计理念

### 证据采集与最终判断分离

Web Worker 只负责提供证据，不负责决定最终答案。即使某个平台输出更长、更自信，也不会天然获得更高权重。最终裁决器根据证据完整性、逻辑质量、可验证性和平台间冲突独立判断。

### 不可变任务核心

每个 Worker Prompt 保留同一个 `task_core`，避免在视角分解过程中改变原问题。推荐 Prompt 组成：

| 部分 | 占比 | 作用 |
|------|------|------|
| 任务核心 | ~80% | 保证所有 Worker 回答同一个问题 |
| 专属视角 | ~15% | 引导工程、研究或推理方向的差异 |
| 交叉覆盖 | ≤5% | 防止某个视角遗漏关键问题 |

### 差异化并行，而非重复投票

默认 Worker 分工：

- **ChatGPT**：工程实践、实现细节、边界条件与可维护性
- **Kimi**：文献基准、资料覆盖、事实核验与背景补充
- **Gemini Pro Extended Thinking**：深层推理、反例分析、长链思考

### 显式降级，而非静默成功

系统将 P2 结果划分为四级：

| 状态 | 含义 |
|------|------|
| `healthy` | 所有 Worker 均提供可用结果 |
| `degraded` | 至少两个 Worker 提供可用结果 |
| `low_confidence` | 仅一个 Worker 提供可用结果 |
| `failed` | 没有获得可用证据 |

---

## 系统架构

```
                            用户问题
                               │
                               ▼
                  ┌────────────────────────┐
                  │ P1 · 问题分析与拆解      │
                  │ 难度判断、模式选择、提示词 │
                  └───────────┬────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
  ┌────────────────┐ ┌────────────────┐ ┌────────────────────┐
  │ ChatGPT Worker │ │  Kimi Worker   │ │   Gemini Worker    │
  │ 工程实践视角    │ │ 文献基准视角    │ │ 深度推理视角        │
  └───────┬────────┘ └───────┬────────┘ └─────────┬──────────┘
          │                  │                    │
          └──────────────────┼────────────────────┘
                             │
                     Chrome CDP 并发调度
                             │
                             ▼
                  ┌────────────────────────┐
                  │ P3 · 证据压缩矩阵       │
                  │ 共识区 / 特色区 / 冲突区 │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │ P4 · DeepSeek V4 Pro   │
                  │ 评分 → 仲裁 → 合成     │
                  └───────────┬────────────┘
                              │
                              ▼
                           最终结果
```

---

## 执行模式

| 模式 | 适用场景 | Worker 数量 | 说明 |
|------|---------|-------------|------|
| **PARALLEL** | 默认，>90% 常规任务 | 3 | 并发三视角，质量、速度、成本均衡 |
| **SIMPLE** | 极简单事实、短答案 | 1 | 跳过完整多模型流程，降低延迟 |
| **CONSENSUS** | 高风险、高冲突、关键决策 | 3+ | 扩大验证，必要时启动千问或 Claude |

DAG 升级路径（单向不可逆）：

```
SIMPLE ──→ PARALLEL ──→ CONSENSUS
              │              │
              │ 2/3 一致     │ Condorcet 门控
              │ → 直出       │ → 深度思考或扩展
```

---

## 平台与角色

| 角色 | 平台 | 核心职责 |
|------|------|---------|
| 工程实践 Worker | ChatGPT | 可执行方案、代码路径、边界条件 |
| 文献基准 Worker | Kimi | 资料覆盖、事实核验、背景补充 |
| 推理深度 Worker | Gemini Pro Extended | 反例构造、隐含假设、长链分析 |
| 替补 Worker | 千问 Deep Thinking | 主要 Worker 不可用时接管 |
| 高难度兜底 | Claude Sonnet | 棘手问题、高冲突升级 |
| 最终裁决 | DeepSeek V4 Pro API | 评分、仲裁、冲突消解、答案合成 |

---

## 稳健性设计

系统经过 20+ 轮迭代和 100+ 次独立专家评估，构建了多层防护。

### 连接与生命周期

- `ConnectionManager` 管理浏览器连接，每次断连产生新 `browser_epoch`
- 旧 epoch 等待者通过 per-epoch Future 立即唤醒，不会永久挂起
- `PageLeaseRegistry` 通过 CAS 令牌防止页面对所有权冲突

### 心跳与故障检测

- 浏览器级 CDP `Browser.getVersion` 心跳，单 Tab 故障不会误报为浏览器死亡
- Tab 级健康检查，连续失败触发降级信号
- `HeartbeatMonitor` 作为纯信号检测器，恢复操作由 orchestrator 统一决策

### 熔断与重试

- 单平台连续 2 次失败进入 OPEN 状态，跳过 30 秒
- HALF_OPEN 状态允许一次探测，成功恢复 CLOSED
- 失败计数随时间衰减——长时间稳定后的偶发失败不会触发熔断

### 超时与截断

- 每个 Worker 独立超时控制
- 超时响应显式标记 `[WARNING: RESPONSE_TRUNCATED]`，不会伪装成完整结果
- 全局 deadline 遵守单调时钟，不使用 floor 掩盖过期

### 错误分类

结构化错误模型覆盖 14 种错误类型，每种错误有明确的恢复策略和恢复范围。

---

## 快速开始

### 环境要求

- Python ≥ 3.10
- Google Chrome 或 Chromium
- Playwright ≥ 1.45
- DeepSeek API 密钥

### 安装

```bash
git clone https://github.com/ziwang-Physics/Test.git
cd Test/skills/multiagent
pip install -r requirements.txt
playwright install chromium
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
DEEPSEEK_API_KEY=你的接口密钥
CDP_ENDPOINT=http://127.0.0.1:9222
DEFAULT_MODE=PARALLEL
```

### 启动 Chrome

```bash
bash scripts/start-chrome-debug.sh
```

在浏览器中登录 ChatGPT、Kimi、Gemini 等需要的平台。

### 运行

```bash
python main.py "如何为多模型调度系统设计可靠的断线恢复机制？"
```

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek V4 Pro API 密钥（必填） |
| `CDP_ENDPOINT` | `http://127.0.0.1:9222` | Chrome CDP 地址 |
| `DEFAULT_MODE` | `PARALLEL` | 默认执行模式 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `WORKER_TIMEOUT_SECONDS` | `300` | 单 Worker 超时 |
| `MIN_SUCCESSFUL_WORKERS` | `2` | 最低成功 Worker 数 |

### YAML 配置

```yaml
runtime:
  mode: parallel
  max_concurrency: 3
  minimum_quorum: 2

platforms:
  chatgpt:
    enabled: true
    role: engineering
  kimi:
    enabled: true
    role: literature
  gemini:
    enabled: true
    role: reasoning
    extended_thinking: true

arbitration:
  provider: deepseek
  model: deepseek-v4-pro
```

---

## 使用方法

### 默认并发模式

```bash
python main.py "审查这个异步架构的竞态条件和资源泄漏。"
```

### 共识模式（高冲突任务）

```bash
python main.py --mode consensus "共享 BrowserContext 中并发运行多 Worker 是否安全？"
```

### 极简模式

```bash
python main.py --mode simple "CDP 是什么的缩写？"
```

### JSON 输出

```bash
python main.py --json "评估多标签页并发调度的可靠性。"
```

---

## 项目结构

```
skills/multiagent/
├── SKILL.md                  # 完整工作流文档
├── orchestrator.py           # P2 浏览器自动化 + P4 API 裁决
├── common.py                 # CDP URL、Deadline、Barrier、安全验证
├── connection.py             # ConnectionManager + PageLeaseRegistry
├── heartbeat.py              # BrowserSupervisor + TabSupervisor
├── main.py                   # 独立 CLI 入口
├── adapters/
│   ├── base.py               # 基类：注入、提取、校验、清理
│   ├── chatgpt.py            # ChatGPT 适配器
│   ├── kimi.py               # Kimi 适配器
│   ├── gemini.py             # Gemini 适配器
│   ├── qianwen.py            # 千问适配器
│   ├── claude.py             # Claude 适配器
│   ├── deepseek.py           # DeepSeek 适配器
│   └── components/           # Gemini 组件驱动
│       ├── gemini_editor.py
│       ├── gemini_completion.py
│       ├── gemini_extraction.py
│       └── gemini_mode.py
├── tests/                    # 单元测试与契约测试
└── scripts/                  # Chrome 启动脚本
```

---

## 验证数据

- **20+ 轮** 迭代验证
- **100+ 次** 独立专家评估
- **30 轮** ChatGPT 对抗性代码审查，发现并修复 40+ 个 P0/P1 问题
- 覆盖：浏览器断连、额度耗尽、空响应、超时、部分 Worker 失败、DOM 变更

---

## 已知限制

- DeepSeek API 密钥缺失时 P4 裁决不可用，系统返回 P3 矩阵
- 部分平台的 DOM 结构可能随版本更新变化，需定期验证选择器
- 项目处于 Alpha 阶段，不建议在无人工复核的情况下用于高风险决策

---

## 许可证

MIT License

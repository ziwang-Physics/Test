# AgentChat - free Web-SubAgent Workflow

> 基于浏览器自动化的多 Web LLM 证据采集系统，DeepSeek 统一裁决合成。
> 
> Claude 换成千问 Qwen3.7-Max 最强平替不解释
> 
> DeepSeek 智能识别任务难度再调 Claude，彻底榨干微量的免费额度

---

## 什么是Web-SubAgent免费多Agent协作系统

AgentChat 不是一个"多模型聊天框架"——它是一个**带裁决器的异步证据聚合系统**。三个免费 Web AI（ChatGPT、Kimi、Gemini Pro Extended Thinking）作为数据采集 Worker，DeepSeek V4 Pro API 作为推理引擎，通过 One-Shot Scoring-Synthesis Judge 一次性完成评分、冲突图仲裁、融合，输出唯一裁决答案。

## 数据流

```
User Query
    │
    ▼
🟢 P1: Decompose → 3 lens prompts (engineering / literature / reasoning)
    │
    ▼
🟡 P2: Concurrent CDP Workers (fire-and-collect, ~50s)
    │
    ├─ ChatGPT  (工程实践)
    ├─ Kimi     (文献基准)
    └─ Gemini   (推理深度, Pro Extended Thinking)
    │
    ▼
🟠 P3: Compress → 共识区 / 特色区 / 冲突区 Matrix
    │
    ▼
🔴 P4: DeepSeek V4 Pro API — One-Shot Scoring-Synthesis Judge
    Independence Check → Scoring(0-10) → Conflict Graph → Synthesis → Final Answer
```

## 核心洞察

Web AI 免费但不可靠（DOM 依赖、超时、额度限制）。DeepSeek API 可靠但需要多视角输入来避免单一偏见。**把不可靠的免费 Web AI 当成"数据采集层"，把可靠的 DeepSeek API 当成"推理引擎层"——各取所长。**

## 为什么用这个？

### 1. DeepSeek 的推理力 × 免费 Web AI 的多样性

DeepSeek V4 Pro API 擅长长链条推理、冲突仲裁、方案融合，但单模型输入视角单一——容易陷入自身偏见或训练数据的系统性盲区。Gemini Pro Extended Thinking、ChatGPT、Claude 各有不同的模型架构和训练数据分布，能提供真正独立的多视角输入。

**AgentChat 将两者桥接**：免费 Web AI 做"数据采集层"（多角度并发回答）→ DeepSeek API 做"推理引擎层"（One-Shot Scoring-Synthesis Judge，一次性完成评分、冲突图仲裁、融合）。这是 **"廉价采集 + 核心推理"的协同模式**，单独使用任何一个都无法达到同样的可靠性和成本效益。

### 2. 多视角交叉验证，消除幻觉

单个 AI 容易产生幻觉——但如果三个不同架构的 AI 独立回答了同一个问题，分歧即是信号，共识即是验证。DeepSeek 不做简单投票，而是构造冲突图、提取原子事实断言、选最大自洽子图——**只有能独立验证的结论才被保留**。

### 3. 极致的 Token 节省

Web 端 Gemini Pro、ChatGPT、Claude 对用户**免费**，生成的思考 token 不占用任何 API 费用。整个流水线只有 DeepSeek 裁决环节消耗少量 API token（通常几百到几千 token）。

对比传统全 API 方案：
- **API 方案**：3 个模型的 API 调用全部计费，长链条推理成本指数级增长
- **AgentChat 方案**：3 个 Web AI 免费生成 → DeepSeek 只消耗少量裁决 token → 近乎零成本的深度推理

**这就是"免费大脑"模式**：用免费 Web 端做多视角采集，用最便宜的 DeepSeek API 做核心推理。

### 4. 抛砖引玉：不止于这三个 Web AI

这个架构的本质是 **"用 CDP 桥接任何免费 Web AI 到 DeepSeek API"**。同样的思路可以：

- 接入 **千问 Deep Thinking** Web 端（aria-pressed toggle 自动化，Claude 平替）
- 接入 **MiniMax Agent**（长上下文 agent workflow）
- 额度耗尽自动 fallback：Gemini/GPT → 千问无缝替换
- 遇到棘手问题启动 Claude，榨干免费额度
- 构建任意多模型协作工作流

AgentChat 提供了最难的第一个环节 — 在中国网络环境下可靠地驱动多个 Web AI + DeepSeek API 协同裁决。其他 Web 应用的接入只需修改 DOM 选择器即可复用全部基础设施。

## 架构

```
用户问题
    │
    ▼
P1: Claude Code 拆解 → 3 个 lens prompt
    │
    ▼
P2: ChatGPT ─┬─ Kimi ─┬─ Gemini Pro Extended Thinking  (CDP 并发)
    │         │        │
    └─────────┴────────┘
              │
              ▼
P3: Claude Code 压缩 → 共识区 / 特色区 / 冲突区 矩阵
              │
              ▼
P4: DeepSeek V4 Pro API — One-Shot Scoring-Synthesis Judge
    评分 → 冲突图 → 仲裁 → 合成 → 最终答案
```

**三种模式 (DAG 单向升级)**：

| 模式 | 触发 | 行为 |
|------|------|------|
| **PARALLEL (默认)** | >90% 查询 | 3 路并发 + lens prompt，一致性 ≥2/3 直接返回 |
| SIMPLE (极罕见) | 简单事实查询 | 1 worker 直接回答 |
| CONSENSUS (升级) | 高冲突/低置信 | One-Shot Judge + Condorcet 门控 + Claude 备选激活 |

## 为什么用 3 个 Web AI 而不是 API

| Web AI 免费 | API 付费 |
|-------------|---------|
| ChatGPT Web — 免费 | GPT-4 API — $10-30/M tokens |
| Kimi Web — 免费 | Moonshot API — ¥12/M tokens |
| Gemini Pro Extended — 免费 | Gemini API — $2.50-10/M tokens |
| **DeepSeek P4 (仅裁决)** | ¥3/6 元 每百万 token |

3 个 Web AI 的思考 token 全部免费。只有终审 DeepSeek API 消耗少量裁决 token——总成本极低。

## 为什么 DeepSeek 做最终裁决

Web AI 通过 CDP 注入，有 DOM 依赖、超时风险、不可控延迟。DeepSeek V4 Pro API 零浏览器依赖、100% 注入成功、秒级响应——流水线终节点必须绝对可靠。详见 [SKILL.md](./skills/multiagent-pipeline/SKILL.md) 中 20+ 轮 loop 迭代的完整验证数据。

## 降级与兜底（免费的尽头）

**遇到少数非常棘手的问题，启动 Claude，榨干 Claude 的免费额度。**

CONSENSUS 升级触发时，Condorcet 门控判断任务难度 → 选择性激活 Claude（Sonnet 4.6）作为第四位专家加入辩论。Claude 擅长防御性架构和边界条件分析，恰好补足 ChatGPT/Kimi/Gemini 的视角盲区——而这一切**免费**。

**如果 Gemini 或 GPT 免费额度用完，自动切换千问最强模型。**

> Claude 平替，懂的都懂。

千问 Qwen3.7-Max + 深度思考模式（aria-pressed toggle 自动化开启）。在 P2 并发池中无缝替换耗尽额度的 worker，流水线不停摆。24 轮实测数据：千问 Deep Thinking 输出 3000-9000 字符结构化分析，文献引用丰富，与 Gemini Pro Extended Thinking 在推理质量上可互相替代。

## 快速开始

一条命令从克隆到跑通：

```bash
git clone https://github.com/ziwang-Physics/Test.git && cd Test
pip install playwright>=1.45 && python3 -m playwright install chromium
export DEEPSEEK_API_KEY="sk-..."
bash scripts/start-chrome-debug.sh          # 启动 Chrome（无预开 tab）
python3 skills/multiagent-pipeline/orchestrator.py phase2 \
  --file prompts.json --timeout 300 --json  # 并发调度 ChatGPT + 千问
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（P4 裁决） |
| `CHROME_CDP_TOKEN` | CDP 认证 token（自动生成于 `~/.chrome-debug-profile/.cdp_token`） |
| `CDP_PORT` | CDP 端口（默认 9222） |

### 使用

```bash
# Claude Code skill 调用（推荐）
/multiagent 你的问题

# 直接 CLI
python3 skills/multiagent-pipeline/orchestrator.py phase2 --file prompts.json --json
python3 skills/multiagent-pipeline/orchestrator.py phase4 --file matrix.md --prompts-file prompts.json
```

## 文件结构

```
skills/multiagent-pipeline/
├── SKILL.md              # 完整工作流文档
├── orchestrator.py       # P2 浏览器自动化 + P4 API 裁定
├── common.py             # CDP URL、AbortableBarrier、安全验证
├── main.py               # 独立 7 平台控制器 (向后兼容)
├── requirements.txt      # playwright>=1.45
├── adapters/
│   ├── base.py           # 基类 (connect/inject/extract/validate)
│   ├── chatgpt.py        # ChatGPT Web adapter
│   ├── kimi.py           # Kimi Web adapter
│   ├── gemini.py         # Gemini Pro Extended Thinking adapter
│   ├── claude.py         # Claude Web adapter (备选)
│   ├── qianwen.py        # 千问 Deep Thinking adapter (备选)
│   ├── deepseek.py       # DeepSeek API adapter
│   └── _deprecated.py    # 豆包 (手动启用)
└── reference/
    └── platform-maturity.md
```

## 设计演进 (20+ 轮 Loop 验证)

- ✅ 5 worker → 3 worker (砍掉 ~85% 不可用的 Claude 和边际极低的千问)
- ✅ Gemini Web P4 → DeepSeek API P4 (零 DOM 依赖, 100% 可靠)
- ✅ One-Shot Scoring-Synthesis Judge (单次 API 完成评分+仲裁+合成)
- ✅ Condorcet 门控 (困难任务禁止扩展, P4 深度思考)
- ✅ Thinking Selector (修复 Kimi/千问/Gemini 提取时机 bug)
- ✅ Sandwich Prompt Structure (Core 80% 同化 + Lens 15% 锐度 + Cross 5% 补位)

## 许可 & 隐私

本仓库不含任何个人凭据、IP 地址或 API 密钥。所有敏感信息通过环境变量和 GPG 加密文件管理。

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

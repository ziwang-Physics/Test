编辑AgentChatFree Web-SubAgent Workflow基于浏览器自动化的多 Web LLM 证据采集与协作推理系统，由 DeepSeek API 统一评分、仲裁与合成。AgentChat 将免费的 Web AI 作为 Evidence Collection Layer，将稳定的 DeepSeek API 作为 Reasoning & Judging Layer：ChatGPT、Kimi、Gemini 等 Web AI 并发采集多视角证据DeepSeek 根据任务难度决定是否触发更深层协作Qwen Deep Thinking 可作为高质量免费替补极少数高难任务按需启用 Claude，最大化利用有限免费额度One-Shot Judge 一次完成评分、冲突分析、事实筛选与最终合成核心思路：廉价采集，集中推理。Use free Web LLMs for diverse evidence collection, and reserve paid API tokens for final reasoning.Table of ContentsWhat is AgentChat?How It WorksCore DesignWhy AgentChat?Execution ModesModel RolesFallback StrategyQuick StartUsageProject StructureDesign EvolutionLicense & PrivacyWhat is AgentChat?AgentChat 不是一个普通的“多模型聊天框架”。它是一个带统一裁决器的 Asynchronous Evidence Aggregation System：多个 Web AI 独立回答同一问题每个 Worker 使用不同的分析视角系统提取共识、差异与冲突DeepSeek 对候选结论进行评分和仲裁最终只输出一份经过融合的裁决答案默认的免费 Web Worker 包括：ChatGPT：工程实践与可执行方案Kimi：文献、资料与基准信息Gemini Pro Extended Thinking：长链条推理与深度分析当默认 Worker 不可用或免费额度耗尽时，可自动切换：Qwen3.7-Max Deep ThinkingClaude Sonnet 4.6其他可通过 CDP 驱动的 Web AI最终由 DeepSeek V4 Pro API 执行 One-Shot Scoring-Synthesis Judge，一次性完成：Independence Check
        ↓
Candidate Scoring
        ↓
Atomic Claim Extraction
        ↓
Conflict Graph Construction
        ↓
Consistency Arbitration
        ↓
Final SynthesisHow It WorksEnd-to-End Data FlowUser Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ P1 · Decompose                                          │
│ Generate three lens prompts:                            │
│ engineering / literature / reasoning                    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ P2 · Concurrent Web Workers                             │
│ CDP-based fire-and-collect execution, usually ~50 s     │
│                                                         │
│  ├─ ChatGPT  · Engineering Practice                     │
│  ├─ Kimi     · Literature & Benchmark                   │
│  └─ Gemini   · Deep Reasoning / Extended Thinking       │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ P3 · Compress                                           │
│ Build a structured evidence matrix:                     │
│ consensus / unique findings / conflicts                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ P4 · Judge                                              │
│ DeepSeek V4 Pro API                                     │
│                                                         │
│ Independence Check → Scoring → Conflict Graph           │
│ → Arbitration → Synthesis → Final Answer                │
└─────────────────────────────────────────────────────────┘Architecture Overview用户问题
    │
    ▼
P1 · Claude Code / Task Decomposer
    │
    ├─ Engineering Lens
    ├─ Literature Lens
    └─ Reasoning Lens
    │
    ▼
P2 · Concurrent CDP Workers
    │
    └─ Gemini Pro Extended Thinking
         │
         └─ Fallback: Qwen Deep Thinking / Claude
    │
    ▼
P3 · Evidence Compressor
    │
    ├─ 共识区 Consensus
    ├─ 特色区 Unique Findings
    └─ 冲突区 Conflicts
    │
    ▼
P4 · DeepSeek V4 Pro API
    │
    └─ One-Shot Scoring-Synthesis Judge
         │
         ├─ 评分
         ├─ 冲突图
         ├─ 仲裁
         ├─ 合成
         └─ 最终答案Core DesignEvidence Layer vs. Reasoning LayerWeb AI 的优势是免费、模型多样、推理 token 成本接近于零；缺点是依赖页面 DOM、账号状态、免费额度和网络环境。DeepSeek API 的优势是稳定、可编程、无浏览器依赖；缺点是单模型输入容易受到自身训练分布和推理偏好的影响。AgentChat 将两者拆分为不同层次：LayerResponsibilityCharacteristicsWeb Evidence Layer并发生成不同视角的候选答案免费、多样，但存在 DOM 和超时风险Compression Layer提取共识、独特信息和冲突减少冗余，控制 P4 输入长度API Reasoning Layer评分、冲突仲裁、事实筛选和合成稳定、集中、可控Final Answer Layer输出唯一裁决结果不暴露未经验证的中间结论核心原则：把不可靠但免费的 Web AI 当作数据采集层，把可靠的 API 模型当作推理与裁决层。Why AgentChat?1. DeepSeek Reasoning × Free Web AI DiversityDeepSeek V4 Pro API 擅长：长链条推理冲突仲裁方案比较多来源信息融合复杂决策合成但单模型容易受到自身训练数据和推理模式的限制。ChatGPT、Kimi、Gemini、Claude 和 Qwen 具有不同的模型架构、训练数据分布及对齐策略。它们独立回答同一问题时，可以提供真正有差异的候选视角。AgentChat 将两部分连接起来：Free Web AI
    │
    ├─ 多角度回答
    ├─ 独立证据
    └─ 不同推理路径
    │
    ▼
DeepSeek API
    │
    ├─ 统一评分
    ├─ 冲突识别
    ├─ 自洽性筛选
    └─ 最终融合单独使用免费 Web AI，结果不够稳定；单独使用 DeepSeek，输入视角又可能过于单一。AgentChat 采用的是：Cheap Collection + Centralized Reasoning2. Multi-Perspective Cross-Validation单个模型可能生成幻觉，但多个不同架构的模型独立回答时：共识可以作为潜在的交叉验证信号分歧可以暴露不确定性和事实冲突独特结论可以补足其他模型的盲区异常答案可以通过一致性和证据质量评分被降权AgentChat 不使用简单多数投票。DeepSeek Judge 会进一步执行：将答案拆解为原子事实断言判断各回答是否真正独立为证据质量和推理完整度评分构建候选结论之间的冲突图寻找最大自洽结论集合对无法验证的结论进行降权或剔除生成统一的最终答案共识不等于真理，但分歧一定是需要继续检查的信号。3. Minimal API Token CostWeb 端 ChatGPT、Gemini、Kimi、Claude 和 Qwen 的生成过程不消耗本系统的模型 API token。整个流水线主要只有 P4 的 DeepSeek Judge 需要 API 调用，通常仅消耗数百至数千 token。Traditional Full-API WorkflowModel A API ─┐
Model B API ─┼─ All generation tokens are billed
Model C API ─┘AgentChat WorkflowChatGPT Web ─┐
Kimi Web ────┼─ Free evidence generation
Gemini Web ──┘
      │
      ▼
DeepSeek API ── Only final judging tokens are billed原始成本对比：Model / ChannelWeb AccessAPI Reference CostChatGPT Web免费额度GPT API：约 $10–30 / M tokensKimi Web免费额度Moonshot API：约 ¥12 / M tokensGemini Pro Extended免费额度Gemini API：约 $2.50–10 / M tokensDeepSeek P4 Judge—约 ¥3 / ¥6 每百万 tokens价格可能随平台策略变化。表格保留的是项目设计阶段使用的成本参考。这套模式也可理解为：Free Brains for Exploration, Low-Cost API for Judgment4. Extensible Beyond Three Web ModelsAgentChat 的本质不是绑定某三个模型，而是：通过 Chrome DevTools Protocol 将任意可访问的 Web AI 接入统一协作流水线。相同基础设施可扩展到：Qwen Deep Thinking自动识别和操作 aria-pressed thinking toggle可作为 Claude 或 Gemini 的替代 WorkerMiniMax Agent适合长上下文 Agent WorkflowClaude Web适合防御性架构、边界条件和复杂工程审查Dynamic FallbackGemini / ChatGPT 额度耗尽后自动切换 QwenConditional Expert Activation仅在任务难度或冲突程度达到阈值时启用 ClaudeCustom Web Applications修改 DOM selectors 即可复用连接、并发、超时和裁决基础设施AgentChat 已实现最困难的基础部分：中国网络环境下的多 Web AI 驱动Chrome CDP 连接与安全验证多 Worker 并发调度DOM 注入与响应提取Extended Thinking 状态控制超时、重连与降级Evidence Matrix 压缩DeepSeek API 最终裁决新增平台通常只需要实现对应 Adapter，并更新必要的 DOM selector。Execution ModesAgentChat 使用单向升级的 DAG 模式。系统可以从低成本模式升级到更严格的协作模式，但不会在同一次执行中反向降级。ModeTypical TriggerBehaviorPARALLEL默认模式，覆盖超过 90% 的查询3 路并发执行 lens prompts；一致性达到 ≥ 2/3 时可直接返回SIMPLE极少数简单事实查询使用单个 Worker 直接回答CONSENSUS高冲突、低置信度或高难任务启动 One-Shot Judge、Condorcet 门控，并按需激活 ClaudeSIMPLE
   │
   ▼
PARALLEL
   │
   ▼
CONSENSUSPARALLEL适合大多数工程、研究和分析任务：三个 Worker 并行执行每个 Worker 获得不同 lens prompt以 fire-and-collect 方式等待结果对成功结果进行一致性检查当结果足够一致时避免不必要的扩展SIMPLE仅用于非常简单、可由单一 Worker 稳定回答的事实型任务。该模式极少触发，主要用于减少：浏览器操作次数页面启动延迟不必要的多模型重复生成CONSENSUS当出现以下情况时升级：多个 Worker 给出互相冲突的结论有效 Worker 数量不足关键事实无法交叉验证任务被判定为高难度初步答案置信度较低CONSENSUS 模式会执行：Conflict Detection
       ↓
Condorcet Gate
       ↓
Optional Claude Activation
       ↓
One-Shot Judge
       ↓
Final SynthesisModel RolesModelPrimary RoleStrengthChatGPT WebEngineering Lens工程实践、实现路径、可执行建议Kimi WebLiterature Lens文献检索、资料整理、长文本处理Gemini Pro Extended ThinkingReasoning Lens深度推理、长链条分析、复杂问题拆解Qwen3.7-Max Deep ThinkingPrimary Fallback中文分析、结构化长回答、免费深度思考Claude Sonnet 4.6Conditional Expert防御性架构、边界条件、代码审查DeepSeek V4 Pro APIFinal Judge评分、冲突图、仲裁与答案合成Default Worker Pool概念架构中的默认三 Worker：ChatGPT + Kimi + Gemini实际运行时可根据可用额度和平台状态替换为：ChatGPT + Qwen + Gemini
ChatGPT + Kimi + Qwen
Qwen + Kimi + GeminiQuick Start 示例当前展示的是：ChatGPT + Qwen具体启用的平台由配置、Adapter 注册状态及运行时可用性决定。Why DeepSeek Is the Final JudgeWeb AI 通过 CDP 和浏览器页面驱动，天然存在以下不确定性：DOM selector 变化页面重新渲染登录状态失效免费额度耗尽浏览器崩溃页面导航超时输出完成状态误判网络延迟不可控DeepSeek V4 Pro API 不依赖浏览器页面，可提供：稳定的结构化输入高成功率的 prompt 注入可预测的超时行为更容易观测的错误传播秒级或可控范围内的响应统一的最终输出格式因此，流水线的终节点必须使用稳定的 API 调用，而不是继续依赖 Web DOM。完整验证过程与 20+ 轮迭代记录见：skills/multiagent-pipeline/SKILL.mdFallback StrategyWhen Free Quotas Run Out当 Gemini 或 ChatGPT 的免费额度耗尽时，系统可以将对应 Worker 替换为：Qwen3.7-Max + Deep ThinkingQwen Adapter 通过 aria-pressed 状态识别并自动开启深度思考模式，可在 P2 并发池中替换不可用 Worker，使流水线继续运行。根据项目 24 轮实测记录：Qwen Deep Thinking 单次输出约 3,000–9,000 字符结构化分析能力较强文献和背景信息较丰富在多个任务中可与 Gemini Pro Extended Thinking 互为替代Difficult-Task Escalation对于少数特别困难的问题，可按需启用 Claude，而不是让 Claude 参与所有查询。CONSENSUS 升级时：Condorcet Gate 判断冲突和任务难度满足阈值后启用 Claude Sonnet 4.6Claude 作为第四位专家提供补充意见DeepSeek 统一处理新增候选答案Claude 的主要补充方向包括：防御性架构边界条件异常路径失败恢复安全性审查隐蔽工程风险这种设计可以在有限免费额度下，将 Claude 留给最需要它的任务。Quick StartRequirementsPython 3Chromium 或 Google ChromePlaywright >= 1.45可访问目标 Web AI 的浏览器账号DeepSeek API KeyLinux、macOS 或兼容的 Shell 环境Clone and Installgit clone https://github.com/ziwang-Physics/Test.git
cd Test

pip install "playwright>=1.45"
python3 -m playwright install chromiumConfigure DeepSeek APIexport DEEPSEEK_API_KEY="sk-..."Start Chrome with CDPbash scripts/start-chrome-debug.sh该脚本会：使用独立的 Chrome profile启动 CDP 调试端口不预先创建业务 tab生成或读取 CDP 认证 tokenRun Phase 2python3 skills/multiagent-pipeline/orchestrator.py phase2 \
  --file prompts.json \
  --timeout 300 \
  --json该命令会通过 CDP 并发调度已启用的 Web Worker。当前运行配置可包含 ChatGPT、Qwen、Kimi 或 Gemini。Environment VariablesVariableRequiredDescriptionDEEPSEEK_API_KEYP4 必需DeepSeek API 密钥，用于最终裁决CHROME_CDP_TOKEN推荐CDP 认证 token；默认可从 ~/.chrome-debug-profile/.cdp_token 读取CDP_PORT可选Chrome DevTools Protocol 端口，默认 9222示例：export DEEPSEEK_API_KEY="sk-..."
export CDP_PORT="9222"
export CHROME_CDP_TOKEN="$(cat ~/.chrome-debug-profile/.cdp_token)"不要将 API Key、CDP token 或浏览器 profile 提交到 Git。UsageClaude Code Skill推荐通过 Claude Code Skill 调用完整流水线：/multiagent 你的问题Run Phase 2 Directly从 prompts.json 读取已拆解的 lens prompts，并执行 Web Worker：python3 skills/multiagent-pipeline/orchestrator.py phase2 \
  --file prompts.json \
  --json指定超时时间：python3 skills/multiagent-pipeline/orchestrator.py phase2 \
  --file prompts.json \
  --timeout 300 \
  --jsonRun Phase 4 Directly使用压缩后的 Evidence Matrix 和原始 prompts 执行最终裁决：python3 skills/multiagent-pipeline/orchestrator.py phase4 \
  --file matrix.md \
  --prompts-file prompts.jsonTypical Pipeline1. User Query
2. Generate prompts.json
3. Run phase2
4. Compress worker outputs into matrix.md
5. Run phase4
6. Return final answerProject Structure.
├── scripts/
│   └── start-chrome-debug.sh
│       # 启动带 CDP 调试端口的 Chrome
│
└── skills/
    └── multiagent-pipeline/
        ├── SKILL.md
        │   # 完整工作流、设计约束和运行说明
        │
        ├── orchestrator.py
        │   # P2 浏览器并发调度 + P4 DeepSeek API 裁决
        │
        ├── common.py
        │   # CDP URL、AbortableBarrier、安全验证及共享工具
        │
        ├── main.py
        │   # 独立 7 平台控制器，保留向后兼容入口
        │
        ├── requirements.txt
        │   # Python 依赖，包括 playwright>=1.45
        │
        ├── adapters/
        │   ├── __init__.py
        │   │   # Adapter 注册和平台可用性管理
        │   │
        │   ├── base.py
        │   │   # Adapter 基类：connect / inject / extract / validate
        │   │
        │   ├── chatgpt.py
        │   │   # ChatGPT Web Adapter
        │   │
        │   ├── kimi.py
        │   │   # Kimi Web Adapter
        │   │
        │   ├── gemini.py
        │   │   # Gemini Pro Extended Thinking Adapter
        │   │
        │   ├── claude.py
        │   │   # Claude Web Adapter，条件式备选专家
        │   │
        │   ├── qianwen.py
        │   │   # Qwen Deep Thinking Adapter，免费额度 fallback
        │   │
        │   ├── deepseek.py
        │   │   # DeepSeek API Adapter
        │   │
        │   └── _deprecated.py
        │       # 已弃用或默认关闭的平台，例如豆包
        │
        └── reference/
            └── platform-maturity.md
                # 各平台成熟度、限制和验证状态Adapter Contract所有 Web 平台通过统一 Adapter 接口接入。基础生命周期：connect
   ↓
probe
   ↓
inject
   ↓
trigger_send
   ↓
wait_for_completion
   ↓
extract
   ↓
validate
   ↓
clean_response
   ↓
cleanup / reuse / rotateadapters/base.py 提供公共能力，各平台 Adapter 负责实现：页面和登录状态检测编辑器定位文本注入Thinking Mode 切换发送动作生成完成检测响应提取输出清理错误模式识别页面复用与清理因此，新增 Web AI 通常只需要：创建新的 Adapter定义平台 URL实现 DOM selectors实现注入、发送和提取逻辑注册 Adapter在 platform-maturity.md 中记录成熟度Prompt StrategyAgentChat 使用 Sandwich Prompt Structure：LayerApprox. RatioPurposeCore80%保证所有 Worker 理解相同任务和约束Lens15%强化各 Worker 的专业视角Cross5%要求主动检查其他视角可能遗漏的问题示意：┌──────────────────────────────────────┐
│ Core Prompt · 80%                    │
│ Shared objective, context, format    │
├──────────────────────────────────────┤
│ Lens Prompt · 15%                    │
│ Engineering / Literature / Reasoning │
├──────────────────────────────────────┤
│ Cross-Check Prompt · 5%              │
│ Inspect blind spots from other lenses│
└──────────────────────────────────────┘该结构兼顾：任务一致性模型差异性输出可比较性视角互补性后续压缩效率Reliability ModelAgentChat 将 Web Worker 视为可失败组件，而不是可靠服务。单个 Worker 可能因为以下原因失败：CDP 断连页面崩溃tab 被关闭selector 失效输入未成功注入发送动作未触发响应为空Thinking Mode 未正确开启生成超时平台额度耗尽输出提取不完整系统通过以下机制降低影响：Worker 并发隔离Deadline 和超时控制Browser / Tab 健康检查Adapter-level validationPage lease 与生命周期管理Tab reuse 和 rotationCircuit BreakerQuorum 判断失败 Worker 过滤Dynamic fallbackP4 API 终审结构化错误信息和 JSON 输出系统不要求所有 Worker 都成功，只要求获得足够数量且质量合格的候选证据。Design EvolutionAgentChat 经过 20+ 轮 Loop 验证和架构迭代。Worker Pool Simplification5 Workers → 3 Workers移除了长期可用性不足或边际收益较低的默认 Worker，降低浏览器资源消耗和失败概率。原始迭代结论包括：约 85% 的 Claude Web 调用在当时环境下不可稳定使用Qwen 在部分默认场景中的边际收益有限将 Claude 和 Qwen 转为条件式 fallback 更合理Final Judge MigrationGemini Web P4 → DeepSeek API P4迁移后的优势：无 DOM 依赖更稳定的输入输出更清晰的错误处理更高的终审成功率更容易实施结构化 Judge PromptOne-Shot Scoring-Synthesis Judge将原本可能需要多轮 API 调用的流程压缩为一次请求：Scoring
   +
Conflict Arbitration
   +
Evidence Selection
   +
Answer Synthesis目标是减少：API token 消耗请求次数跨轮上下文漂移中间状态管理网络失败点Condorcet Gate使用 Condorcet 风格的门控逻辑识别：是否存在明显优势答案是否出现循环偏好是否需要额外专家是否应该升级到 CONSENSUS困难任务不会无条件扩展 Worker，而是优先将预算投入最终深度裁决。Thinking Selector统一管理 Kimi、Qwen 和 Gemini 的 Thinking Mode，修复或避免：模式未真正开启toggle 状态判断错误生成尚未完成就开始提取Thinking 输出与最终答案混淆页面状态切换后 selector 失效Prompt Sandwich采用：Core 80% + Lens 15% + Cross 5%在保持候选答案可比较性的同时，避免三个 Worker 输出过度同质化。Current Design Highlights✅ 多 Web AI 并发证据采集✅ Chrome CDP 浏览器自动化✅ 独立 lens prompts✅ Extended Thinking 自动控制✅ Worker 超时和错误分类✅ 浏览器断连恢复✅ Tab reuse 与 rotation✅ Quorum 和 Circuit Breaker✅ Evidence Matrix 压缩✅ One-Shot Scoring-Synthesis Judge✅ Conflict Graph 仲裁✅ Condorcet 门控✅ Qwen 免费额度 fallback✅ Claude 条件式专家激活✅ DeepSeek API 稳定终审✅ JSON-compatible CLI 输出✅ 独立多平台兼容入口Known Constraints由于系统依赖第三方 Web UI，需要注意：平台 DOM 更新可能导致 selector 失效免费模型名称和额度策略可能发生变化登录验证或验证码可能需要人工处理Web 平台可能限制自动化行为不同账号看到的 UI 可能不一致Extended Thinking 功能可能受账号或地区限制平台响应速度无法完全预测API 和 Web 模型版本可能由服务提供方自动更新平台支持状态和已知限制记录在：reference/platform-maturity.mdSecurity & Privacy本仓库不包含：个人账号凭据固定 IP 地址API Key浏览器 CookieCDP Token私有 Chrome Profile明文密码敏感信息通过以下方式管理：环境变量本地 Chrome profile自动生成的 CDP token 文件GPG 加密文件推荐安全实践：# API Key 仅注入当前 Shell
export DEEPSEEK_API_KEY="sk-..."

# 不要提交本地 profile 或 token
git status需要加入 .gitignore 的典型内容：.env
*.gpg
.chrome-debug-profile/
.cdp_token
__pycache__/
*.pycLicense & Privacy请根据仓库根目录中的许可证文件使用、修改和分发本项目。在公开部署或共享运行日志前，请检查其中是否包含：Prompt 中的敏感信息Web AI 返回的私人数据页面 URLSession 标识API 错误响应浏览器调试信息AcknowledgementsBuilt with browser automation, Playwright, Chrome DevTools Protocol, multiple Web LLMs, and DeepSeek API.🤖 Generated and iterated with Claude Code
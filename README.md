# AgentChat

**基于浏览器自动化并发调度多个网页大模型、采集多视角证据，并由统一裁决模型生成最终答案的多人工智能协作系统。**基于浏览器自动化并发调度多个网页大模型、采集多视角证据，并由统一裁决模型生成最终答案的多人工智能协作系统。    概述AgentChat 是一个基于浏览器自动化的多网页大模型证据采集与协作推理系统。它不是简单地把同一个问题发送给多个模型，也不是将多份回答直接拼接。AgentChat 会先拆解问题，再让不同模型从互补视角独立分析，随后压缩共识、差异与冲突，最后交由 DeepSeek V4 Pro API 完成评分、仲裁和答案合成。系统默认调度三个免费的网页人工智能服务：ChatGPT：侧重工程实践、实现路径、边界条件与可执行性。Kimi：侧重文献基准、资料覆盖、事实核验与背景补充。Gemini Pro Extended Thinking：侧重复杂推理、反例分析、长链路思考与深层约束。三个 Worker 通过 Chrome CDP 并发运行，不要求为每个网页模型配置独立接口密钥。最终结果由 DeepSeek V4 Pro API 统一裁决，避免简单投票造成的多数偏差。完整流程分为四个阶段：第一阶段：分析问题难度，并生成三个互补视角的提示词。第二阶段：通过 Chrome CDP 并发调度 ChatGPT、Kimi 和 Gemini。第三阶段：将多模型结果压缩为共识区、特色区和冲突区。第四阶段：由 DeepSeek V4 Pro API 评分、仲裁并生成最终答案。## 架构                              用户问题
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │ 第一阶段：问题分析与拆解 │
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
                    │ 第三阶段：证据压缩矩阵   │
                    │                        │
                    │ - 共识区               │
                    │ - 特色区               │
                    │ - 冲突区               │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ DeepSeek V4 Pro API    │
                    │ 评分、仲裁、冲突消解    │
                    │ 最终答案合成            │
                    └───────────┬────────────┘
                                │
                                ▼
                             最终结果当主要 Worker 不可用时，系统会进入自动降级链：ChatGPT、Kimi 或 Gemini 不可用
              │
              ▼
       自动切换千问深度思考
              │
              ▼
      判断问题是否仍然存在高冲突
              │
       ┌──────┴──────┐
       │             │
       否            是
       │             │
       ▼             ▼
  继续完成裁决    启动 Claude 兜底为什么选择 AgentChat多视角而非重复回答不同 Worker 使用不同任务提示词，分别承担工程实践、文献基准和推理深度职责，减少多个模型产生高度相似答案的问题。网页模型优先，降低使用成本ChatGPT、Kimi 和 Gemini 通过已登录的浏览器页面工作，不依赖三个独立的付费模型接口。并发采集，缩短等待时间三个 Worker 通过 Chrome CDP 同时运行，整体耗时接近最慢单个 Worker，而不是三个模型耗时之和。裁决而非简单投票DeepSeek V4 Pro 会结合证据质量、推理完整性、事实一致性和任务适配度进行评分，不会机械地选择多数意见。显式保留冲突系统会区分共识、独有发现和冲突结论。存在争议时，裁决器必须说明采用某一结论的原因。支持自动降级当网页模型额度耗尽、页面异常或生成失败时，系统可以切换到千问；面对高风险、高复杂度或高冲突任务时，可以进一步启动 Claude。面向长时间运行设计系统包含连接恢复、页面租约、超时控制、错误分类、Worker 隔离和安全清理机制，适合连续执行多轮任务。执行模式模式适用场景Worker 数量是否进行统一裁决特点PARALLEL默认模式，适用于绝大多数问题3是并发采集三个视角，在质量、速度和成本之间取得平衡SIMPLE极简单事实、短答案或无需争议分析的问题1按需跳过完整多模型流程，优先降低延迟CONSENSUS高风险、高冲突或需要更强证据一致性的问题3 个以上是扩大验证范围，必要时启动千问或 ClaudePARALLEL 模式PARALLEL 是默认模式，适用于超过九成的常规任务。执行过程：为三个 Worker 生成不同视角的提示词。并发采集 ChatGPT、Kimi 和 Gemini 的回答。提取共识、特色发现和冲突。交由 DeepSeek V4 Pro 完成最终裁决。SIMPLE 模式SIMPLE 用于答案明确、推理成本较低的问题，例如：简单定义。单一事实查询。短文本转换。不需要多视角验证的基础任务。该模式会减少 Worker 数量，并在证据充分时跳过复杂仲裁。CONSENSUS 模式CONSENSUS 用于以下任务：多个模型结论明显冲突。涉及复杂架构、关键决策或高风险判断。需要更严格的事实核验。单轮回答置信度不足。用户明确要求多模型共识。该模式会提高证据要求，并根据任务难度启动千问或 Claude 进行补充验证。Worker 角色Worker默认平台核心职责重点检查工程实践 WorkerChatGPT提供可执行方案、代码路径和工程判断可实现性、异常处理、性能、维护成本、边界条件文献基准 WorkerKimi补充资料、基准、背景与事实依据来源覆盖、术语准确性、行业基准、历史信息推理深度 WorkerGemini Pro Extended Thinking进行复杂推理、反例构造和约束分析隐含假设、逻辑漏洞、反例、长期影响、冲突解释替补 Worker千问深度思考在主要 Worker 不可用时接管任务回答完整性、推理连续性、可用性恢复高难度 WorkerClaude处理棘手问题和高冲突升级深层综合、复杂代码分析、长上下文一致性最终裁决器DeepSeek V4 Pro API评分、仲裁、冲突消解和答案合成证据权重、事实一致性、任务匹配度、最终可读性每个 Worker 都应独立完成任务，不能依赖其他 Worker 的中间结论。这样可以降低观点污染，并保留真正的模型差异。降级与兜底AgentChat 将网页模型异常分为额度、页面、网络、浏览器和内容五类，并根据错误类型选择不同的恢复策略。异常情况首选处理后续处理网页模型额度耗尽标记当前平台暂时不可用自动切换千问页面结构变化重新定位输入框和响应区域重建标签页并再次执行单个标签页崩溃释放当前页面租约创建新标签页重新运行对应 WorkerChrome CDP 暂时断开取消当前批次并清理任务重新连接浏览器后重跑当前阶段Worker 超时保留其他 Worker 的有效结果根据法定数量决定继续裁决或启动替补返回空内容重新提取并检查生成状态重新执行对应 Worker三个模型结论高度冲突切换到 CONSENSUS 模式启动 Claude 进行补充分析DeepSeek 裁决失败保留结构化证据矩阵使用备用裁决配置重试默认降级顺序：主要 Worker
    │
    ├─ 正常完成 ────────────────► 进入证据压缩
    │
    └─ 失败
         │
         ▼
    同平台重试
         │
         ├─ 成功 ───────────────► 进入证据压缩
         │
         └─ 失败
              │
              ▼
         千问深度思考替补
              │
              ├─ 证据充分 ──────► DeepSeek 裁决
              │
              └─ 仍有高冲突
                   │
                   ▼
               Claude 兜底降级不会静默发生。最终结果中应记录：哪些 Worker 成功。哪些 Worker 失败。是否发生重试。是否启用替补平台。是否进入共识升级。最终裁决依据了哪些有效证据。快速开始环境要求Python 3.11 或更高版本。Google Chrome 或 Chromium。已安装 Playwright。Chrome 已登录需要使用的网页人工智能平台。可用的 DeepSeek V4 Pro API 密钥。Linux、macOS 或 Windows 环境。获取项目git clone https://github.com/你的账号/AgentChat.git
cd AgentChat创建虚拟环境python -m venv .venv
source .venv/bin/activateWindows PowerShell：.venv\Scripts\Activate.ps1安装依赖pip install -r requirements.txt
playwright install chromium配置环境变量cp .env.example .env编辑 .env：DEEPSEEK_API_KEY=你的接口密钥
CDP_ENDPOINT=http://127.0.0.1:9222
DEFAULT_MODE=PARALLEL
LOG_LEVEL=INFO启动 Chrome 调试端口Linux 或 macOS：google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.agentchat-chrome"部分 Linux 环境中的命令可能是：chromium \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.agentchat-chrome"Windows PowerShell：& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:USERPROFILE\.agentchat-chrome"Chrome 启动后，在该浏览器窗口中登录需要使用的平台：ChatGPT。Kimi。Gemini。千问。Claude。运行 AgentChatpython main.py "如何为一个多模型调度系统设计可靠的浏览器断线恢复机制？"指定执行模式：python main.py \
  --mode PARALLEL \
  "比较三种异步任务取消策略，并给出适合生产环境的方案。"配置说明AgentChat 支持通过环境变量和配置文件管理运行参数。敏感信息应放在 .env 中，调度策略应放在配置文件中。环境变量变量必填默认值说明DEEPSEEK_API_KEY是无DeepSeek V4 Pro API 密钥CDP_ENDPOINT否http://127.0.0.1:9222Chrome DevTools Protocol 地址DEFAULT_MODE否PARALLEL默认执行模式LOG_LEVEL否INFO日志级别MAX_RETRIES否2单个 Worker 的最大重试次数WORKER_TIMEOUT_SECONDS否300单个 Worker 的生成超时时间ARBITER_TIMEOUT_SECONDS否180最终裁决超时时间ENABLE_QIANWEN_FALLBACK否true是否启用千问替补ENABLE_CLAUDE_ESCALATION否true是否允许高难度任务启动 ClaudeMIN_SUCCESSFUL_WORKERS否2PARALLEL 模式进入裁决所需的最少成功 Worker 数量调度配置示例配置文件 config.yaml：运行模式:
  默认模式: PARALLEL
  自动升级共识模式: true

浏览器:
  调试地址: http://127.0.0.1:9222
  导航超时秒数: 60
  单页最大复用次数: 10
  断线自动重连: true

并发:
  最大并发Worker数: 3
  最少成功Worker数: 2
  Worker超时秒数: 300

重试:
  最大重试次数: 2
  首次退避秒数: 2
  最大退避秒数: 15

降级:
  启用千问替补: true
  启用Claude升级: true
  高冲突阈值: 0.65

裁决:
  模型: deepseek-v4-pro
  超时秒数: 180
  输出冲突说明: true
  输出证据摘要: true

日志:
  级别: INFO
  结构化输出: true
  保存运行报告: true
  报告目录: runs模式选择规则模式选择:
  SIMPLE:
    最大预计复杂度: 低
    是否需要多来源验证: false

  PARALLEL:
    最大预计复杂度: 高
    是否需要多来源验证: true

  CONSENSUS:
    触发条件:
      - 高风险任务
      - 主要结论冲突
      - 有效Worker少于预期
      - 用户明确要求共识配置文件中的接口密钥、登录凭证和令牌不得提交到版本库。建议将以下内容加入 .gitignore：.env
.venv/
__pycache__/
runs/
logs/
.agentchat-chrome/
*.log使用示例默认并发模式python main.py \
  "请审查一个基于 Playwright 的多标签页并发系统，重点检查竞态条件、资源泄漏和超时传播。"执行流程：ChatGPT 分析工程实现和错误处理。Kimi 查找相关基准与常见故障模式。Gemini 分析并发边界、反例和隐含假设。DeepSeek 对三个结果进行评分和统一裁决。极简模式python main.py \
  --mode SIMPLE \
  "什么是 Chrome CDP？"该模式适合不需要多模型交叉验证的简单问题。共识升级模式python main.py \
  --mode CONSENSUS \
  "在共享 BrowserContext 中并发运行多个 Worker 是否安全？请分析不同实现方案的风险。"该模式会提高证据要求，并在主要结论无法收敛时启动额外 Worker。从文件读取问题python main.py \
  --input question.txt \
  --mode PARALLEL输出结构化结果python main.py \
  --mode PARALLEL \
  --output result.json \
  --format json \
  "分析当前架构中可能导致静默数据损坏的路径。"结构化输出示例：{
  "状态": "成功",
  "## 执行模式": "PARALLEL",
  "最终答案": "最终裁决后的完整答案",
  "共识区": [
    "三个 Worker 共同确认的结论"
  ],
  "特色区": {
      "工程实现方面的独有发现"
    ],
      "文献或基准方面的独有发现"
    ],
    "Gemini": [
      "复杂推理方面的独有发现"
    ]
  },
  "冲突区": [
    {
      "主题": "存在分歧的问题",
      "采用结论": "裁决器最终采用的结论",
      "裁决理由": "证据权重和推理依据"
    }
  ],
  "Worker状态": {
    "ChatGPT": "成功",
    "Kimi": "成功",
    "Gemini": "成功"
  },
  "是否发生降级": false
}作为 Python 模块调用import asyncio

from agentchat import AgentChat
from agentchat.models import ExecutionMode


async def main() -> None:
    client = AgentChat.from_config("config.yaml")

    result = await client.run(
        question="如何改进异步任务取消时的资源清理完整性？",
        mode=ExecutionMode.PARALLEL,
    )

    print(result.final_answer)


if __name__ == "__main__":
    asyncio.run(main())项目结构AgentChat/
├── main.py                     # 命令行入口
├── orchestrator.py             # 多阶段调度与执行模式控制
├── connection.py               # Chrome CDP 连接与重连管理
├── heartbeat.py                # 浏览器和标签页健康检查
├── common.py                   # 公共数据结构、错误类型和工具函数
├── config.yaml                 # 默认运行配置
├── .env.example                # 环境变量示例
├── requirements.txt            # Python 依赖
├── adapters/
│   ├── __init__.py             # 平台适配器注册
│   ├── base.py                 # 适配器基础接口
│   ├── chatgpt.py              # ChatGPT 网页适配器
│   ├── kimi.py                 # Kimi 网页适配器
│   ├── gemini.py               # Gemini 网页适配器
│   ├── qianwen.py              # 千问替补适配器
│   ├── claude.py               # Claude 高难度适配器
│   ├── deepseek.py             # DeepSeek 裁决器
│   └── components/
│       ├── gemini_editor.py     # Gemini 输入与发送控制
│       ├── gemini_completion.py # Gemini 完成状态检测
│       ├── gemini_extraction.py # Gemini 响应提取
│       └── gemini_mode.py       # Gemini 深度思考模式控制
├── pipeline/
│   ├── decomposition.py        # 问题拆解与视角提示词生成
│   ├── collection.py           # 多 Worker 并发证据采集
│   ├── compression.py          # 共识区、特色区和冲突区压缩
│   └── arbitration.py          # 评分、仲裁和最终合成
├── models/
│   ├── result.py               # 统一结果结构
│   ├── error.py                # 错误分类与错误传播模型
│   └── worker.py               # Worker 状态与执行记录
├── tests/
│   ├── test_connection.py      # 连接与重连测试
│   ├── test_heartbeat.py       # 健康检查测试
│   ├── test_adapters.py        # 平台适配器测试
│   ├── test_pipeline.py        # 多阶段管道测试
│   └── test_orchestrator.py    # 端到端调度测试
├── reference/
│   └── platform-maturity.md    # 平台成熟度与兼容性记录
├── scripts/
│   └── start-chrome-debug.sh   # Chrome 调试模式启动脚本
├── runs/                       # 结构化运行报告
└── README.md验证数据AgentChat 已经过持续迭代验证，覆盖多模型调度、浏览器异常、超时恢复、结果裁决和降级链路。验证项目当前数据完整验证轮次20 轮以上独立任务评估100 次以上默认并发 Worker3 个支持的执行模式3 种主要免费网页模型3 个自动替补平台千问高难度兜底平台Claude最终裁决模型DeepSeek V4 Pro核心证据分区共识区、特色区、冲突区重点验证场景包括：Chrome CDP 首次连接失败。浏览器运行过程中断开。标签页崩溃或被用户关闭。Worker 生成超时。网页平台额度耗尽。页面结构变化导致选择器失效。返回空响应或不完整响应。多个 Worker 结论相互冲突。并发任务取消时的资源清理。连接恢复后的页面租约一致性。最少成功 Worker 数量不足。裁决接口超时或返回异常。用户通过 Ctrl+C 中断运行。长时间运行中的标签页轮换。结构化结果字段一致性。验证目标不是证明所有模型始终正确，而是确保系统在模型失败、网页变化、浏览器断线和观点冲突时仍能提供可解释、可恢复且可追踪的结果。许可证本项目采用 MIT ## 许可证。你可以自由使用、复制、修改、合并、发布和分发本项目，但必须保留原始版权声明和许可证声明。详细条款请参阅项目根目录中的 LICENSE 文件。
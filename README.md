AgentChat面向 Web LLM 的并发证据采集、质量校验、故障恢复与独立裁决 Skill。AgentChat 不是一个让多个模型轮流发言的聊天界面。它将多个 Web LLM 视为相互独立、可能失败、可能冲突的证据源，通过浏览器并发采集答案，再交给独立裁决器完成评分、仲裁与合成。目录概述核心设计理念系统架构执行模式平台与角色稳健性设计快速开始配置说明使用方法输出格式项目结构开发与测试验证数据已知限制许可证概述AgentChat 是一条面向复杂问题的多智能体证据流水线。它通过 Chrome DevTools Protocol 连接本地持久化浏览器，使用 Playwright 驱动多个 AI 网站，并将不同平台的输出压缩为可审计的证据矩阵。项目的完整实现位于 skills/multiagent/，其中包含连接管理、浏览器心跳、页面租约、平台适配器、单元测试和契约测试。skills/multiagent-pipeline/ 保留为较轻量的兼容实现；本文档以 skills/multiagent/ 版本 0.2.0 为准。典型流程包含四个阶段：阶段名称职责P1问题分解提取不可变任务核心，为不同 Worker 生成差异化视角P2并发采集驱动 ChatGPT、千问、Gemini 并发回答并执行质量校验P3证据压缩整理共识、特色信息和冲突，形成结构化矩阵P4裁决合成将证据矩阵发送给 DeepSeek API，完成评分、仲裁与最终合成其中，orchestrator.py 直接实现 P2 和 P4；P1、P3、模式选择及提前退出策略由宿主 Agent 或 Skill 运行时负责。核心设计理念证据采集与最终判断分离Web Worker 只负责提供证据，不负责决定最终答案。即使某个平台输出得更长、更自信，也不会天然获得更高权重。最终裁决器需要根据证据完整性、逻辑质量、可验证性和平台间冲突独立判断。不可变任务核心每个 Worker Prompt 都应保留同一个 task_core，避免在视角分解过程中改变原问题。推荐 Prompt 组成：部分建议占比作用任务核心约 80%保证所有 Worker 回答同一个问题专属视角约 15%引导工程、研究或推理方向的差异交叉覆盖不超过 5%防止某个视角遗漏关键问题差异化并行，而不是重复投票默认 Worker 分工如下：ChatGPT：工程实践、实现细节、边界条件与可维护性千问：中文语境、系统化归纳、方案覆盖与替代路径Gemini：深层推理、反例、跨领域联系与长链分析这种分工不是永久绑定。Worker Prompt 中的任务核心必须一致，差异仅来自分析视角。Fire-and-Collect推荐入口不会要求所有 Worker 在同一个屏障后同时发送。每个 Worker 完成页面准备后即可独立提交，失败或超时不会阻塞其他 Worker。最终阶段按照实际获得的有效证据计算 Quorum，而不是等待最慢的平台。显式降级，而不是静默成功系统将 P2 结果划分为四级：状态含义healthy所有选定 Worker 均提供可进入 Quorum 的结果degraded至少两个 Worker 提供可用结果low_confidence仅有一个 Worker 提供可用结果failed没有获得可用证据调用方可以据此决定继续裁决、升级到共识模式，或停止输出。先提取，再清理，再验证平台回答不会被直接送入后续阶段。适配器统一执行：连接页面
  → 建立新会话
  → 等待编辑器可用
  → 清空输入
  → 注入 Prompt
  → 等待完成
  → 提取回答
  → 清理界面噪声
  → 校验质量质量校验会识别空响应、Prompt 回显、错误页、界面文本占比过高、DOM 变化和提取不完整等情况。系统架构                         ┌───────────────────────────┐
                         │         用户问题          │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│ P1：问题分解                                                       │
│                                                                    │
│ task_core ─────────────────────────────────────────────────────┐   │
│                                                               │   │
│ worker_prompts                                                │   │
│ ├─ chatgpt：工程实践 / 边界条件                                │   │
│ ├─ qianwen：系统归纳 / 替代方案                                │   │
│ └─ gemini：深层推理 / 反例                                     │   │
└───────────────────────────────────┬────────────────────────────┘   │
                                    │                                │
                                    ▼                                │
┌────────────────────────────────────────────────────────────────────┐
│ P2：浏览器并发证据采集                                             │
│                                                                    │
│                    ConnectionManager                               │
│                   浏览器生命周期唯一所有者                         │
│                            │                                       │
│              ┌─────────────┴─────────────┐                         │
│              │ browser_epoch             │                         │
│              │ PageLeaseRegistry         │                         │
│              │ HeartbeatMonitor          │                         │
│              └─────────────┬─────────────┘                         │
│                            │                                       │
│          ┌─────────────────┼─────────────────┐                     │
│          ▼                 ▼                 ▼                     │
│   ChatGPTAdapter     QianwenAdapter      GeminiAdapter             │
│          │                 │                 │                     │
│          └─────────────────┼─────────────────┘                     │
│                            ▼                                       │
│                 提取 → 清理 → 验证 → Quorum                       │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│ P3：自适应证据压缩                                                 │
│                                                                    │
│ ├─ 共识区：多个平台一致支持的结论                                  │
│ ├─ 特色区：单个平台提供的高价值信息                                │
│ └─ 冲突区：结论、事实、假设或优先级上的分歧                        │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                 ┌───────────┴───────────┐
                 │ 满足提前退出条件？    │
                 └──────┬─────────┬──────┘
                        │是       │否
                        ▼         ▼
                 宿主直接合成     P4：DeepSeek API
                                  评分 → 仲裁 → 合成
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │   最终答案   │
                                  └──────────────┘当前 orchestrator.py 的 P2 核心 Worker 为 ChatGPT、千问和 Gemini。它为浏览器断连、任务取消、部分提取、Quorum 计算和一次浏览器级恢复提供了统一路径。代码职责边界能力Skill 或宿主 Agentorchestrator.py判断任务难度是否选择 SIMPLE、PARALLEL、CONSENSUS是否生成差异化 Worker Prompt是否驱动 Web Worker否是页面质量校验否是计算 P2 Quorum否是构造共识、特色、冲突矩阵是否判断是否提前退出是否调用 DeepSeek 裁决否是执行模式模式只能单向升级：SIMPLE → PARALLEL → CONSENSUS不允许在同一次任务中从高成本模式退回低成本模式，以免丢失已经发现的风险或冲突。模式适用场景典型行为SIMPLE简单事实、低风险问答、无需多方证据宿主直接回答，或只调用一个 WorkerPARALLEL默认模式；工程分析、方案比较、代码审查三个核心 Worker 并发采集，随后压缩证据CONSENSUS高风险决策、平台严重冲突、低置信度结果增加备用 Worker、扩展验证，再执行强制裁决建议的提前退出条件：有效 Worker 数量 >= 2
且主要结论形成共识
且宿主评估置信度 >= 0.70
且不存在未解决的高风险冲突提前退出属于 Skill 层策略，不是 orchestrator.py phase2 命令的自动行为。平台与角色核心 Worker平台适配器默认进入 P2主要能力ChatGPTChatGPTAdapter是工程分析、边界条件、实现建议千问QianwenAdapter是中文表达、系统归纳、替代方案GeminiGeminiAdapter是Extended Thinking、反例和长链推理Gemini 已拆分为编辑器控制、完成检测、响应提取、模式控制和协议定义等独立组件，降低单文件复杂度并方便 DOM 契约测试。备用与兼容平台平台适配器定位KimiKimiAdapter核心 Worker 不可用时的备用中文长文本平台ClaudeClaudeAdapter棘手问题的升级 Worker，需注意账户额度和限流DeepSeek WebDeepSeekAdapter兼容入口中的可选 Web Worker，与 P4 API 裁决器不是同一角色豆包_deprecated.py已弃用，依赖脆弱的界面选择器，仅适合手动实验完整适配器注册表位于 adapters/__init__.py。稳健性设计浏览器生命周期唯一所有者ConnectionManager 是 Playwright 和浏览器连接生命周期的唯一所有者。适配器、Worker 和心跳组件不得自行重连整个浏览器，从而避免多个协程同时重启连接、关闭新页面或覆盖状态。每次连接或重连都会生成新的 browser_epoch。旧 Epoch 中仍在运行的任务即使延迟返回，也不能操作新连接中的资源。页面租约PageLeaseRegistry 使用以下信息标识页面所有权：platform
page object id
run_id
browser_epoch
attempt
generation页面关闭或复用前必须同时通过 Epoch 和 Generation 校验。这可以防止：旧 Worker 关闭新 Worker 已接管的页面心跳组件误删业务标签页两个 Worker 同时使用同一页面浏览器重连后旧任务继续写入共享状态心跳只报告故障HeartbeatMonitor 和 Tab Supervisor 只负责检测并发出信号，不直接执行浏览器重连、页面刷新或共享存储清理。默认检测策略：对象检测间隔单次超时连续失败阈值浏览器30 秒10 秒3 次页面15 秒10 秒2 次真正的恢复动作由 Orchestrator 和 ConnectionManager 协调完成。原生断连事件与慢速心跳竞速P2 同时监听：Playwright 原生 browser.on("disconnected")浏览器心跳故障信号Worker 聚合任务完成信号原生断连可以快速发现浏览器崩溃，心跳用于覆盖页面卡死或 CDP 无响应等场景。浏览器死亡时，系统会：取消旧 Epoch Worker
  → 有界等待任务退出
  → 停止旧心跳
  → 原子重连浏览器
  → 创建新 Epoch
  → 重新执行 P2当前最多执行一次浏览器级恢复。熔断与新标签页重试每个平台拥有独立熔断器：连续失败两次后进入 OpenOpen 持续 30 秒之后进入 Half-OpenHalf-Open 只允许一个探测请求探测成功后恢复 Closed当响应因空文本、Prompt 回显、错误模式、DOM 改动或界面噪声而不可用时，Worker 可以在同一 Chrome 会话内打开新标签页重试一次。部分结果优先发生超时时，系统会尝试提取页面上已经生成的文本。只要部分文本达到最低可用标准，就会作为降级证据保留，而不是将整个平台结果直接丢弃。安全清理资源清理遵循以下规则：只关闭当前 Worker 持有有效租约的页面不清理共享 Cookie、Local Storage 或登录状态不因单个标签页失败而关闭整个浏览器保留健康页面供后续任务复用普通平台默认复用三次，Gemini 默认每次轮换页面快速开始环境要求依赖要求Python>=3.11,<3.15Playwright>=1.49,<1.52浏览器Chromium、Chrome 或兼容的 CDP 浏览器平台账户至少登录 ChatGPT、千问、GeminiDeepSeek API Key仅执行 P4 时需要操作系统启动脚本主要面向 Linux 或 macOS Bash 环境项目元数据声明 Python 3.11 至 3.14，并为异步 P4 调用提供可选的 httpx 依赖。1. 克隆仓库git clone https://github.com/ziwang-Physics/Test.git
cd Test/skills/multiagent2. 创建虚拟环境python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[async]"
python -m playwright install chromium3. 启动持久化浏览器回到仓库根目录：cd ../..

PROXY_SERVER=http://127.0.0.1:7897 \
bash scripts/start-chrome-debug.sh请将 PROXY_SERVER 替换为本机可访问的代理地址。启动器默认：只在 127.0.0.1 上开放 CDP使用端口 9222使用持久化配置目录 ~/.chrome-debug-profile生成权限受限的 CDP Token保留平台登录状态在浏览器异常退出时执行守护恢复然后导出 Token：export CHROME_CDP_TOKEN="$(
  cat ~/.chrome-debug-profile/.cdp_token
)"启动器及 CDP 安全检查会限制本地监听地址，并检查调试端口是否意外暴露到外部网络。4. 登录平台在启动的浏览器中手动登录：ChatGPT千问Gemini登录信息保存在持久化浏览器 Profile 中。不要将 Profile、Cookie 或 .cdp_token 提交到 Git。5. 创建 Worker Prompt进入完整实现目录：cd skills/multiagent
mkdir -p .work创建 .work/prompts.json：{
  "task_core": "评估一个异步 Python 服务的稳健性，并给出可执行的改进方案。",
  "worker_prompts": {
    "chatgpt": "围绕工程实现、异常传播、资源清理和并发安全分析。任务核心不得改变。",
    "qianwen": "围绕系统设计、降级策略、可维护性和替代方案分析。任务核心不得改变。",
    "gemini": "围绕深层因果、反例、极端边界和隐藏假设分析。任务核心不得改变。"
  }
}平台键必须使用规范小写名称：chatgpt
qianwen
gemini6. 执行 P2 并发采集python orchestrator.py phase2 \
  --file .work/prompts.json \
  --timeout 300 \
  --json \
  > .work/phase2.json虽然 P2 默认超时为 60 秒，但对于 Extended Thinking 或复杂工程问题，建议显式设置为 180 至 300 秒。7. 构造 P3 证据矩阵宿主 Agent 应读取 .work/phase2.json，将有效回答压缩为：# 共识区

- 多个平台共同支持的结论
- 已得到交叉验证的事实
- 一致认可的高优先级建议

# 特色区


- 仅 ChatGPT 提出的高价值工程细节


- 仅千问提出的系统化替代方案

## Gemini

- 仅 Gemini 提出的反例、风险或深层推理

# 冲突区

- 冲突主题
- 各平台观点
- 证据依据
- 尚未解决的问题建议根据估算 Token 数选择压缩策略：P2 总量P3 策略少于 64K Token可跳过深度压缩，仅统一格式64K 至 128K Token轻量去重和冲突提取不少于 128K Token完整共识、特色、冲突矩阵8. 执行 P4 裁决export DEEPSEEK_API_KEY="你的 API Key"

python orchestrator.py phase4 \
  --file .work/matrix.md \
  --prompts-file .work/prompts.json \
  --task-core "评估一个异步 Python 服务的稳健性，并给出可执行的改进方案。" \
  > .work/final.mdP4 会将裁决规则放在独立的 System 消息中，并将 Worker 输出作为不可信证据数据传入，降低间接 Prompt Injection 改写裁决规则的风险。配置说明环境变量变量默认值是否必需说明CHROME_CDP_TOKEN无推荐CDP 连接认证 TokenDEEPSEEK_API_KEY无P4 必需DeepSeek 裁决 API KeyCDP_PORT9222否本地 Chrome 调试端口PROXY_SERVERhttp://127.0.0.1:7897否浏览器代理服务器HEADLESSfalse否是否以无头模式启动CHROME_PROFILE~/.chrome-debug-profile否持久化浏览器配置目录CHROMIUM_PATH自动检测否手动指定浏览器可执行文件运行时默认值配置项默认值P2 单平台超时60 秒main.py 单平台超时300 秒Worker 启动间隔1.5 秒熔断触发阈值连续失败 2 次熔断 Open 时间30 秒浏览器级恢复次数1 次普通页面最大复用次数3 次Gemini 页面最大复用次数1 次P4 请求超时120 秒P4 最大输出 Token4096单次响应提取上限约 500 KBP4 当前代码配置接口：
https://api.deepseek.com/anthropic/v1/messages

模型标识：
deepseek-v4-pro该模型标识和兼容接口必须在你的账户中实际可用。若服务端配置不同，请同步修改 orchestrator.py。使用方法从标准输入执行 P2cat .work/prompts.json |
python orchestrator.py phase2 \
  --timeout 300 \
  --json运行后关闭 Worker 标签页默认情况下，健康页面会被保留供后续任务复用。需要任务结束后关闭页面时：python orchestrator.py phase2 \
  --file .work/prompts.json \
  --timeout 300 \
  --close-tabs \
  --json只运行 P4cat .work/matrix.md |
python orchestrator.py phase4 \
  --task-core "原始任务核心"使用兼容并发入口main.py 可以让多个平台回答同一个 Prompt：python main.py \
  --adapters chatgpt,qianwen,gemini \
  --timeout 300 \
  --json \
  "请分析该系统的并发安全问题"查看适配器成熟度：python main.py --maturity默认适配器集合为：gemini,chatgpt,claude,kimi,qianwen,deepseek建议显式指定平台，避免无意触发未登录、额度不足或成熟度较低的适配器。main.py 默认使用发送屏障，让所有已就绪 Worker 尽量同时提交。关闭屏障：python main.py \
  --no-barrier \
  --adapters chatgpt,qianwen,gemini \
  "你的问题"--no-barrier 只表示各 Worker 准备好后立即发送，任务本身仍然并发执行，并不等价于串行模式。对需要浏览器断连恢复、页面 Epoch、租约校验、心跳和 Quorum 的生产流程，应优先使用 orchestrator.py phase2。作为本地 Skill 安装mkdir -p ~/.claude/skills
cp -R skills/multiagent ~/.claude/skills/multiagent安装后，宿主 Agent 可以读取 SKILL.md，负责模式选择、P1 Prompt 分解、P3 证据压缩和提前退出判断。输出格式P2 输出示例{
  "success": true,
  "quorum": "healthy",
  "success_count": 3,
  "timeout_count": 0,
  "recovery_count": 0,
  "results": [
    {
      "platform": "chatgpt",
      "success": true,
      "quorum_eligible": true,
      "response": "清理后的回答正文",
      "length": 4280,
      "timeout": false,
      "error": "",
      "quality": "OK"
    },
    {
      "platform": "qianwen",
      "success": true,
      "quorum_eligible": true,
      "response": "清理后的回答正文",
      "length": 3612,
      "timeout": false,
      "error": "",
      "quality": "OK"
    },
    {
      "platform": "gemini",
      "success": true,
      "quorum_eligible": true,
      "response": "清理后的回答正文",
      "length": 5790,
      "timeout": false,
      "error": "",
      "quality": "DEGRADED_BUT_USABLE"
    }
  ]
}success_count 表示可进入 Quorum 的结果数量，不只是适配器内部的布尔成功数量。当前可进入 Quorum 的质量状态包括：OK
UI_CHROME_DOMINANT
DEGRADED_BUT_USABLE单 Worker 字段字段类型说明platform字符串规范化平台名称success布尔值适配器是否获得可用文本quorum_eligible布尔值是否可以参与 Quorumresponse字符串清理后的回答length整数回答字符数timeout布尔值是否在超时后提取部分结果error字符串截断后的错误信息quality字符串响应质量分类实际 P2 返回结构由 phase2_dispatch() 统一生成。项目结构Test/
├── README.md
├── CHANGELOG.md
├── scripts/
│   ├── start-chrome-debug.sh
│   └── start-chrome-debug.py
├── skills/
│   ├── multiagent/
│   │   ├── SKILL.md
│   │   ├── pyproject.toml
│   │   ├── requirements.txt
│   │   ├── orchestrator.py
│   │   ├── main.py
│   │   ├── common.py
│   │   ├── connection.py
│   │   ├── heartbeat.py
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── chatgpt.py
│   │   │   ├── qianwen.py
│   │   │   ├── gemini.py
│   │   │   ├── kimi.py
│   │   │   ├── claude.py
│   │   │   ├── deepseek.py
│   │   │   ├── _deprecated.py
│   │   │   └── components/
│   │   │       ├── protocols.py
│   │   │       ├── gemini_editor.py
│   │   │       ├── gemini_completion.py
│   │   │       ├── gemini_extraction.py
│   │   │       └── gemini_mode.py
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   └── contracts/
│   │   ├── reference/
│   │   └── .github/
│   │       └── workflows/
│   │           └── ci.yml
│   └── multiagent-pipeline/
│       └── 兼容实现
└── loop_results/
    └── SUMMARY.md核心文件说明：文件职责SKILL.mdSkill 层工作流、模式和 Prompt 规范orchestrator.py推荐入口；执行 P2 和 P4main.py多平台同题并发兼容入口common.py公共常量、错误类型、结果结构、日志和屏障connection.pyPlaywright 生命周期、重连、Epoch 和页面租约heartbeat.py浏览器与页面故障检测adapters/base.py注入、等待、提取、清理、验证的统一管线adapters/各平台 DOM 自动化实现tests/unit/生命周期、公共组件和边界逻辑测试tests/contracts/平台 DOM 选择器和适配器契约测试仓库当前完整实现的目录结构及适配器文件以 skills/multiagent/ 为准。开发与测试安装开发依赖cd skills/multiagent
python -m pip install -e ".[dev]"运行单元测试pytest tests/unit/ -v运行适配器契约测试pytest tests/contracts/ -v运行静态检查ruff check .
ruff format --check .
mypy --ignore-missing-imports .包目录中提供了 CI 配置模板，覆盖：Python 3.11、3.12、3.13 的 Ruff 和 MyPyPython 3.11、3.12、3.13 的单元测试Python 3.12 的适配器契约测试工作日定时 E2E Smoke 入口注意：GitHub 只自动识别仓库根目录下的 .github/workflows/。当前工作流位于 skills/multiagent/.github/workflows/；如需启用 GitHub Actions，应将其移动到仓库根目录，并同步修正工作目录。当前可见测试树包含 unit/ 和 contracts/。CI 中预留的 tests/e2e/ 任务需要在补充相应测试后再启用。验证数据仓库中的 loop_results/SUMMARY.md 记录了 30 轮浏览器采集验证：指标结果验证轮次30验证平台ChatGPT、千问每轮成功情况30 轮均为 2/2Worker 成功执行数60/60总采集字符数199,118ChatGPT 总字符数133,095ChatGPT 平均字符数4,436千问总字符数66,023千问平均字符数2,200这些数据证明了特定环境下 ChatGPT 与千问双 Worker 的连续采集能力，但不应被解读为完整生产可用性指标。当前验证记录尚未完整覆盖：Gemini 三 Worker Quorum浏览器崩溃后的自动恢复Circuit Breaker Half-Open 探测长时间运行时的页面轮换P3 证据压缩质量P4 裁决正确率平台 DOM 大版本更新不同网络、账户和地区环境已知限制Web DOM 不是稳定 API平台界面可能随时调整：编辑器选择器发送按钮停止生成按钮Thinking 状态回答容器错误提示登录与额度弹窗适配器已提供多级选择器和通用回退，但无法保证在平台更新后始终可用。依赖本地账户状态项目复用本地浏览器登录态，不会代替用户注册、登录或绕过平台限制。实际可用性受以下因素影响：账户套餐地区限制每日额度并发限制验证码风控策略平台服务条款P1 和 P3 不是独立 CLI 阶段orchestrator.py 目前只直接提供：phase2
phase4P1 Prompt 分解和 P3 证据压缩依赖宿主 Agent 按照 SKILL.md 执行。仅运行 CLI 不等于执行完整四阶段流水线。main.py 是兼容入口main.py 适合快速获得多个平台对同一 Prompt 的回答，但它不具备推荐 Orchestrator 的全部能力，例如：Browser Epoch 恢复页面租约校验浏览器心跳竞速Quorum 分级浏览器死亡后整轮重跑P4 失败不会自动伪造答案当 DEEPSEEK_API_KEY 缺失、接口超时或服务端返回错误时，P4 返回空结果并记录错误。调用方应保留 P3 矩阵，并选择：重试 API更换裁决器由宿主 Agent 基于矩阵合成明确向用户报告裁决失败当前仍处于 Alpha版本元数据将项目标记为 Alpha。对于医疗、法律、金融、安全响应或其他高风险决策，不应在缺少人工复核的情况下直接采用最终输出。许可证skills/multiagent/pyproject.toml 当前声明使用 MIT 许可证。MIT License仓库根目录当前未见独立的 LICENSE 文件。为消除分发和贡献授权上的歧义，正式发布前应在仓库根目录补充完整的 MIT License 文本。
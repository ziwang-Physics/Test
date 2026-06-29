<p align="center">
  <strong>Free Web-SubAgent Workflow for Multi-LLM Evidence Collection, Deliberation, and Arbitration</strong>
</p><p align="center">
  基于浏览器自动化的多 Web LLM 证据采集、协作推理与统一仲裁系统
</p><p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white">
  <img alt="Playwright" src="https://img.shields.io/badge/Playwright-CDP_Automation-2EAD33?logo=playwright&logoColor=white">
  <img alt="Architecture" src="https://img.shields.io/badge/Architecture-Multi--Agent-7C3AED">
  <img alt="Workflow" src="https://img.shields.io/badge/Workflow-Evidence_Driven-0EA5E9">
  <img alt="Status" src="https://img.shields.io/badge/Status-Actively_Validated-success">
  <img alt="License" src="https://img.shields.io/badge/License-See_LICENSE-blue">
</p>OverviewAgentChat is an evidence-driven multi-AI collaboration system built on browser automation.Instead of asking one model to produce a final answer directly, AgentChat decomposes the task into complementary research perspectives, dispatches them to multiple Web LLMs in parallel, compresses the collected evidence into a structured comparison matrix, and performs a final one-shot arbitration through DeepSeek V4 Pro.AgentChat is not merely a multi-model chat interface.It is an asynchronous evidence collection pipeline with an explicit judge.AgentChat 不只是“多模型聊天框”，而是一套带有统一裁决器的异步证据协作系统。The workflow is designed around four phases:PhaseResponsibilityOutputP1 — DecomposeSplit the original question into three complementary perspectivesPerspective-specific promptsP2 — CollectRun ChatGPT, Kimi, and Gemini concurrently through browser CDP sessionsIndependent evidence packagesP3 — CompressNormalize responses into consensus, unique insights, and conflictsStructured evidence matrixP4 — ArbitrateScore, reconcile, and synthesize all evidence with DeepSeek V4 ProFinal answerWhy AgentChat?A single LLM may:overlook an important perspective;become overconfident in an unsupported assumption;reproduce the same reasoning pattern across retries;provide polished conclusions without sufficient evidence;fail silently when context, quota, or browser state changes.AgentChat reduces these risks through:perspective diversity — 多视角问题分解;independent generation — 独立证据采集;explicit disagreement tracking — 显式冲突识别;structured arbitration — 评分、仲裁与合成;quota-aware degradation — 额度感知降级;browser-session reuse — 复用用户现有 Web LLM 会话.ValidationThe workflow has been refined through:more than 20 iterative validation loops;more than 100 independent expert evaluations;repeated failure-path testing across browser disconnections, quota exhaustion, empty responses, timeouts, and partial worker failures.Architecture┌─────────────────────────────────────────────────────────────────────────────┐
│                               User Question                                 │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ P1 · Perspective Decomposition                                               │
│                                                                             │
│  ① Engineering Practice       工程实践                                       │
│  ② Literature & Benchmarks    文献基准                                       │
│  ③ Reasoning Depth            推理深度                                       │
└───────────────┬─────────────────────┬─────────────────────┬─────────────────┘
                │                     │                     │
                ▼                     ▼                     ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│ ChatGPT Web           │ │ Kimi Web              │ │ Gemini Pro Web        │
│ Browser/CDP Worker    │ │ Browser/CDP Worker    │ │ Extended Thinking     │
└───────────────┬───────┘ └───────────────┬───────┘ └───────────────┬───────┘
                │                         │                         │
                └─────────────────────────┼─────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ P3 · Evidence Compression                                                    │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Consensus Zone  │  │ Unique Zone     │  │ Conflict Zone               │  │
│  │ 共识区          │  │ 特色区          │  │ 冲突区                      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ P4 · DeepSeek V4 Pro One-Shot Arbitration                                    │
│                                                                             │
│  Score → Verify → Resolve Conflicts → Synthesize                             │
│  评分  → 证据审查 → 冲突仲裁 → 最终合成                                      │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Final Answer                                   │
└─────────────────────────────────────────────────────────────────────────────┘Runtime ModesAgentChat selects one of three execution modes according to task complexity and expected disagreement.ModeTypical usageBehaviorPARALLELDefault for more than 90% of tasksRuns independent Web LLM workers concurrently, then performs structured arbitrationSIMPLEExtremely simple factual questionsUses a reduced path to avoid unnecessary orchestration overheadCONSENSUSHigh-risk, ambiguous, or strongly conflicting questionsExpands verification and escalates disagreement resolution                          ┌──────────────┐
                          │ User Request │
                          └──────┬───────┘
                                 │
                         Complexity Analysis
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
        ┌──────────┐       ┌──────────┐       ┌───────────┐
        │  SIMPLE  │       │ PARALLEL │       │ CONSENSUS │
        └──────────┘       └──────────┘       └───────────┘
          Low cost           Default path       Conflict-awareDegradation and EscalationAgentChat is designed to continue producing useful results even when one or more providers are unavailable.Gemini quota exhausted ─┐
                        ├──► Qwen Deep Thinking replacement
ChatGPT quota exhausted ┘

High-complexity task
        │
        └──► Claude escalation for additional analysis

Partial worker failure
        │
        ├──► Continue when quorum is still valid
        └──► Mark missing evidence explicitlyThe degradation chain follows three principles:Never hide a failed source.失败来源必须显式标记，不能伪装成成功结果。Preserve source independence.A replacement worker should generate its own answer rather than rewrite another worker's response.Prefer a transparent partial result over silent fabrication.宁可返回可解释的部分结果，也不静默补全不存在的证据。Quick StartPrerequisitesBefore running AgentChat, prepare:Python 3;Google Chrome or Chromium;an authenticated browser session for the enabled Web LLM platforms;Playwright and the required Python dependencies;a DeepSeek API key for final arbitration;optional access to Qwen and Claude for fallback or escalation.1. Clone the Repositorygit clone <repository-url>
cd AgentChat2. Create a Virtual Environmentpython -m venv .venvActivate it:# Linux / macOS
source .venv/bin/activate# Windows PowerShell
.venv\Scripts\Activate.ps13. Install Dependenciespip install -r requirements.txt
playwright install chromium4. Configure Environment VariablesCreate a local environment file:cp .env.example .envAt minimum, configure the DeepSeek API key:DEEPSEEK_API_KEY=your_deepseek_api_keyDo not commit .env, browser profiles, session cookies, API keys, or generated authentication state.5. Start Chrome with Remote DebuggingLinux or macOS:./start-chrome-debug.shA typical manual command is:google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.agentchat/chrome-profile"Windows example:chrome.exe `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:USERPROFILE\.agentchat\chrome-profile"Log in to the required Web LLM platforms in this browser profile before running AgentChat.6. Run AgentChatpython main.py "Review this architecture and identify the highest-risk failure modes."Explicitly select a mode:python main.py \
  --mode parallel \
  "Compare three approaches to reliable browser-session recovery."For structured output:python main.py \
  --mode consensus \
  --output-format json \
  "Evaluate the safety and correctness of this concurrent orchestration design."UsageBasic Querypython main.py "Explain the trade-offs between polling and event-driven browser monitoring."Engineering Reviewpython main.py \
  --mode parallel \
  "Review this async Python architecture for race conditions, resource leaks, and timeout bugs."Literature and Benchmark Comparisonpython main.py \
  --mode parallel \
  "Compare current long-context evaluation methods and identify limitations in their benchmark design."High-Conflict AnalysisUse CONSENSUS mode when:the answer may influence an important engineering decision;available sources are likely to disagree;the question contains ambiguous assumptions;independent verification is more important than latency;the first-pass workers return materially different conclusions.python main.py \
  --mode consensus \
  "Should this browser automation system use one shared BrowserContext or isolated contexts per worker?"Simple ModeUse SIMPLE mode for low-complexity tasks that do not justify full multi-agent execution.python main.py \
  --mode simple \
  "What does CDP stand for?"Read from Standard Inputcat prompt.txt | python main.py --stdinSave the Final Resultpython main.py \
  --output result.md \
  "Produce a deployment-readiness review for this repository."JSON Outputpython main.py \
  --output-format json \
  "Analyze the failure modes of the worker lifecycle."Example response shape:{
  "status": "success",
  "mode": "parallel",
  "query": "Analyze the failure modes of the worker lifecycle.",
  "result": {
    "summary": "Final synthesized answer",
    "consensus": [],
    "unique_insights": [],
    "conflicts": [],
    "recommendations": []
  },
  "workers": {
    "chatgpt": {
      "status": "success"
    },
    "kimi": {
      "status": "success"
    },
    "gemini": {
      "status": "degraded",
      "replacement": "qwen"
    }
  }
}Python Integrationimport asyncio

from orchestrator import AgentChatOrchestrator


async def main() -> None:
    orchestrator = AgentChatOrchestrator()

    result = await orchestrator.run(
        query=(
            "Review this distributed workflow for race conditions, "
            "silent failures, and recovery gaps."
        ),
        mode="parallel",
    )

    print(result.final_answer)


if __name__ == "__main__":
    asyncio.run(main())ConfigurationAgentChat can be configured through environment variables, command-line arguments, or a project configuration file.A recommended precedence order is:CLI arguments
    ↓
Environment variables
    ↓
Configuration file
    ↓
Built-in defaultsEnvironment Variables# ---------------------------------------------------------------------------
# Required
# ---------------------------------------------------------------------------

DEEPSEEK_API_KEY=your_deepseek_api_key

# ---------------------------------------------------------------------------
# Browser / CDP
# ---------------------------------------------------------------------------

AGENTCHAT_CDP_ENDPOINT=http://127.0.0.1:9222
AGENTCHAT_BROWSER_CONNECT_TIMEOUT=15
AGENTCHAT_PAGE_READY_TIMEOUT=30
AGENTCHAT_GENERATION_TIMEOUT=180

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

AGENTCHAT_MODE=parallel
AGENTCHAT_MAX_CONCURRENCY=3
AGENTCHAT_MIN_QUORUM=2
AGENTCHAT_MAX_RETRIES=2

# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------

AGENTCHAT_ENABLE_CHATGPT=true
AGENTCHAT_ENABLE_KIMI=true
AGENTCHAT_ENABLE_GEMINI=true
AGENTCHAT_ENABLE_QWEN_FALLBACK=true
AGENTCHAT_ENABLE_CLAUDE_ESCALATION=true

# ---------------------------------------------------------------------------
# Output and observability
# ---------------------------------------------------------------------------

AGENTCHAT_LOG_LEVEL=INFO
AGENTCHAT_LOG_FORMAT=json
AGENTCHAT_OUTPUT_FORMAT=markdown
AGENTCHAT_ARTIFACT_DIR=./artifactsConfiguration FileExample agentchat.yaml:runtime:
  mode: parallel
  max_concurrency: 3
  minimum_quorum: 2
  max_retries: 2

browser:
  cdp_endpoint: http://127.0.0.1:9222
  connect_timeout_seconds: 15
  page_ready_timeout_seconds: 30
  generation_timeout_seconds: 180
  rotate_tab_after_uses: 20

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

  qwen:
    enabled: true
    fallback_for:
      - chatgpt
      - gemini
    deep_thinking: true

  claude:
    enabled: true
    escalation_only: true

arbitration:
  provider: deepseek
  model: deepseek-v4-pro
  strategy: one_shot
  require_conflict_resolution: true

output:
  format: markdown
  include_worker_metadata: true
  include_conflict_matrix: true
  artifact_directory: ./artifacts

logging:
  level: INFO
  format: json
  redact_sensitive_values: trueRun with a configuration file:python main.py \
  --config agentchat.yaml \
  "Audit the reliability of this browser automation pipeline."Key OptionsOptionDefaultDescriptionmodeparallelRuntime strategy: simple, parallel, or consensusmax_concurrency3Maximum number of concurrent browser workersminimum_quorum2Minimum successful independent responses requiredmax_retries2Maximum retry count for retryable worker failuresgeneration_timeout_seconds180Per-worker generation deadlinerotate_tab_after_uses20Number of runs before a reused tab is rotatedextended_thinkingtrueEnables Gemini Extended Thinking when availableescalation_onlytruePrevents Claude from running on ordinary requestsredact_sensitive_valuestrueRemoves tokens and session secrets from logsPlatform RolesThe default roles are intentionally asymmetric.PlatformPrimary role中文说明ChatGPTEngineering feasibility and implementation details工程实践KimiSource discovery, literature context, and benchmark coverage文献基准Gemini Pro Extended ThinkingDeep reasoning, edge cases, and alternative hypotheses推理深度Qwen Deep ThinkingQuota fallback and replacement worker深度思考替补ClaudeEscalation for unusually difficult or unresolved tasks棘手问题升级DeepSeek V4 ProFinal scoring, conflict resolution, and synthesis终审裁决These roles are defaults, not hard restrictions. The orchestrator may modify prompts according to the task.File StructureAgentChat/
├── main.py                         # Primary CLI entry point
├── orchestrator.py                 # Four-phase orchestration workflow
├── common.py                       # Shared models, enums, errors, deadlines
├── connection.py                   # CDP connection and reconnection manager
├── heartbeat.py                    # Browser and tab health supervision
│
├── adapters/
│   ├── __init__.py                 # Adapter registry
│   ├── base.py                     # Base injection/extraction pipeline
│   ├── chatgpt.py                  # ChatGPT Web adapter
│   ├── kimi.py                     # Kimi Web adapter
│   ├── gemini.py                   # Gemini Web adapter
│   ├── qianwen.py                  # Qwen fallback adapter
│   ├── claude.py                   # Claude escalation adapter
│   ├── deepseek.py                 # DeepSeek arbitration client
│   ├── _deprecated.py              # Retired compatibility adapters
│   │
│   └── components/
│       ├── gemini_editor.py        # Gemini prompt injection and submission
│       ├── gemini_completion.py    # Generation completion detection
│       ├── gemini_extraction.py    # Response extraction
│       └── gemini_mode.py          # Extended Thinking mode control
│
├── prompts/
│   ├── decomposition.md            # P1 perspective decomposition
│   ├── engineering.md              # Engineering-practice worker prompt
│   ├── literature.md               # Literature and benchmark worker prompt
│   ├── reasoning.md                # Deep-reasoning worker prompt
│   ├── compression.md              # P3 evidence compression prompt
│   └── arbitration.md              # P4 final judge prompt
│
├── reference/
│   ├── platform-maturity.md        # Platform support and maturity matrix
│   ├── error-taxonomy.md           # Error classification reference
│   └── architecture.md             # Detailed architecture notes
│
├── tests/
│   ├── test_orchestrator.py        # End-to-end orchestration tests
│   ├── test_connection.py          # Reconnect and epoch tests
│   ├── test_heartbeat.py           # Browser/tab supervision tests
│   ├── test_adapters.py            # Adapter contract tests
│   ├── test_error_propagation.py   # Error classification and propagation
│   └── fixtures/                   # Browser and response fixtures
│
├── artifacts/                      # Generated reports and evidence packages
├── start-chrome-debug.sh           # Chrome CDP startup helper
├── agentchat.yaml                  # Example runtime configuration
├── .env.example                    # Environment variable template
├── requirements.txt                # Python dependencies
├── SKILL.md                        # Agent/skill integration contract
├── LICENSE
└── README.mdDesign1. Evidence Before SynthesisAgentChat separates evidence collection from final answer generation.Workers do not collaboratively edit one shared draft. Each worker receives an independent prompt and produces an independent evidence package.This avoids:early anchoring;majority imitation;shared hallucination propagation;one dominant model suppressing minority evidence.Independent Evidence
        │
        ▼
Structured Comparison
        │
        ▼
Explicit Arbitration
        │
        ▼
Final Synthesis2. Perspective-Oriented DecompositionP1 creates three prompts with distinct objectives.Engineering Practice — 工程实践Focus areas include:implementation feasibility;operational failure modes;concurrency and lifecycle correctness;performance and resource usage;maintainability;concrete code-level recommendations.Literature and Benchmarks — 文献基准Focus areas include:published methods;standard terminology;benchmark design;comparable systems;empirical evidence;limitations of existing evaluations.Reasoning Depth — 推理深度Focus areas include:hidden assumptions;second-order effects;adversarial cases;alternative explanations;logical consistency;unresolved uncertainty.3. Structured Evidence MatrixP3 does not simply concatenate worker responses.It converts them into three explicit regions:RegionMeaning中文说明Consensus ZoneClaims supported independently by multiple workers共识区Unique ZoneValuable insights raised by only one worker特色区Conflict ZoneClaims, assumptions, or recommendations that disagree冲突区Example:## Consensus Zone

- Browser disconnection must be propagated through a shared lifecycle signal.
- Worker retries must use a fresh browser epoch.
- Timeouts should be classified separately from confirmed browser death.

## Unique Zone

- Gemini identified a potential stale DOM completion signal.
- Kimi found a comparable failure mode in an external implementation.
- ChatGPT proposed a lease-based cleanup invariant.

## Conflict Zone

| Topic | Position A | Position B | Required decision |
|---|---|---|---|
| BrowserContext reuse | More efficient | Higher shared-state risk | Isolate only high-risk workers |4. One-Shot ArbitrationThe final judge receives the compressed matrix rather than an unbounded transcript.Its responsibilities are:evaluate evidence quality;detect unsupported agreement;preserve important minority findings;resolve contradictions where possible;expose unresolved uncertainty;synthesize an actionable final answer.The judge should not treat majority agreement as proof.Agreement ≠ Correctness
Disagreement ≠ Failure
Minority Evidence ≠ Noise5. Quorum-Aware ExecutionA single worker failure should not always invalidate the full run.AgentChat can continue when:enough independent workers completed successfully;the missing worker is clearly identified;the remaining evidence satisfies the configured quorum;the final judge receives accurate worker-status metadata.A run should fail or escalate when:quorum cannot be reached;all surviving workers are derived from the same fallback source;evidence is empty or structurally invalid;browser state is no longer trustworthy;the judge cannot distinguish successful and degraded inputs.6. Failure ClassificationFailures are classified by meaning rather than by raw exception text.Recommended categories include:CONFIGURATION_ERROR
AUTHENTICATION_REQUIRED
QUOTA_EXHAUSTED
RATE_LIMITED
NAVIGATION_FAILED
INJECTION_FAILED
GENERATION_TIMEOUT
EMPTY_RESPONSE
EXTRACTION_FAILED
TAB_CRASHED
BROWSER_DISCONNECTED
ARBITRATION_FAILED
CANCELLED
INTERNAL_ERROREach error should carry structured context:{
  "code": "GENERATION_TIMEOUT",
  "platform": "gemini",
  "retryable": true,
  "degraded": false,
  "message": "Gemini did not finish before the worker deadline.",
  "action": "Retry once, then replace the worker with Qwen Deep Thinking."
}7. Browser Lifecycle SafetyBrowser automation is treated as an unreliable distributed boundary.Important invariants include:a page lease belongs to exactly one browser epoch;pages from an old epoch must never be reused after reconnect;cleanup must be idempotent;worker cancellation must be awaited and drained;a slow CDP response must not automatically imply browser death;tab failure and browser failure must remain distinguishable;user interruption must trigger complete resource cleanup.8. Quota-Aware FallbackFallback is based on explicit failure classification.Primary worker succeeds
        │
        └──► Keep original result

Primary worker reports quota exhaustion
        │
        └──► Start independent Qwen replacement

Primary worker times out
        │
        ├──► Retry when browser remains healthy
        └──► Replace only after retry policy is exhausted

Task remains unresolved
        │
        └──► Escalate to ClaudeFallback results must record:the original provider;the reason for replacement;the replacement provider;whether the replacement is independent;whether quorum semantics changed.9. Observable by DefaultA failed run should be diagnosable from one trace.Recommended structured fields:{
  "run_id": "run_20260630_001",
  "phase": "P2",
  "platform": "chatgpt",
  "attempt": 2,
  "browser_epoch": 4,
  "page_lease_id": "lease_018",
  "elapsed_ms": 18420,
  "status": "failed",
  "error_code": "BROWSER_DISCONNECTED"
}Useful metrics include:total runs;successful and degraded runs;per-platform success rate;fallback frequency;quorum failures;generation latency;browser reconnect count;timeout count;empty-response count;arbitration failures.10. Security and PrivacyAgentChat controls already-authenticated browser sessions. Treat the browser profile as sensitive.Do not:commit browser profiles;export cookies into logs;print API keys;store full prompts indefinitely by default;expose the CDP endpoint to untrusted networks;connect to a CDP hostname without validating its resolved address;run untrusted prompts with unrestricted local file access.Recommended practices:bind CDP to 127.0.0.1;use a dedicated browser profile;redact secrets in structured logs;limit artifact retention;validate all configured endpoints;sanitize control characters before prompt injection;keep arbitration credentials separate from browser credentials.Adding a New Platform AdapterA platform adapter should implement the common adapter contract.from adapters.base import BaseAdapter
from common import PlatformId


class ExampleAdapter(BaseAdapter):
    platform_id = PlatformId.EXAMPLE

    async def probe(self) -> bool:
        """Return whether the platform page is usable."""
        ...

    async def inject_prompt(self, prompt: str) -> None:
        """Insert the prompt without submitting it multiple times."""
        ...

    async def trigger_send(self) -> None:
        """Submit exactly once."""
        ...

    async def wait_for_completion(self) -> None:
        """Wait until generation completes or the deadline expires."""
        ...

    async def extract_response(self) -> str:
        """Return the complete assistant response."""
        ...

    async def cleanup(self) -> None:
        """Restore the page to a reusable state."""
        ...Then register it:from adapters.example import ExampleAdapter

ADAPTER_REGISTRY["example"] = ExampleAdapterEvery new adapter should include tests for:empty responses;delayed rendering;partial streaming;duplicate submission prevention;changed DOM selectors;quota and authentication messages;generation timeout;tab crash;browser disconnect;cancellation during generation;cleanup idempotency.DevelopmentRun Testspytest -qRun reliability-focused tests:pytest -q \
  tests/test_connection.py \
  tests/test_heartbeat.py \
  tests/test_error_propagation.pyRun with coverage:pytest \
  --cov=. \
  --cov-report=term-missing \
  --cov-report=htmlStatic Checksruff check .
mypy .Formatruff format .Debug LoggingAGENTCHAT_LOG_LEVEL=DEBUG \
AGENTCHAT_LOG_FORMAT=json \
python main.py "Diagnose this worker failure."Graceful InterruptionAgentChat should support interruption through Ctrl+C.Expected behavior:stop accepting new work;signal all active workers;cancel pending generation tasks;await cancelled tasks;release page leases;stop heartbeat supervisors;close owned resources;preserve externally managed Chrome sessions;return a meaningful process exit code.LimitationsAgentChat relies on Web LLM interfaces, which can change without notice.Potential limitations include:DOM selector drift;authentication expiration;provider-side rate limits;quota exhaustion;delayed or virtualized response rendering;incomplete extraction after UI changes;model availability differences between accounts;non-deterministic Extended Thinking behavior;increased latency in CONSENSUS mode;provider terms that may restrict certain automation patterns.Browser automation should be treated as a compatibility layer, not a stable public API.Before production use:review each platform's terms of service;validate adapters against the current UI;keep fallback paths tested;monitor extraction quality;inspect degraded results before relying on them.RoadmapTyped configuration schemaAdapter capability negotiationAutomatic selector-drift diagnosticsEvidence provenance scoringPersistent run replayWeb-based observability dashboardProvider-independent arbitration interfaceConfigurable perspective templatesDynamic worker selectionLocal-model evidence workersReproducible benchmark suiteAutomated chaos testing for browser failuresContributingContributions are welcome.Useful contribution areas include:new platform adapters;selector-resilience improvements;browser lifecycle fixes;structured error classification;timeout and cancellation tests;prompt-compression improvements;evidence quality evaluation;documentation and examples.Recommended workflow:git checkout -b feature/your-change
pytest -q
git commit -m "feat: describe your change"
git push origin feature/your-changeWhen submitting a pull request, include:the problem being solved;affected platforms;failure behavior before the change;expected behavior after the change;tests covering the change;screenshots or sanitized logs when UI behavior is involved.LicenseThis project is distributed under the terms defined in the repository's LICENSE file.Third-party services, models, websites, and automation targets remain subject to their own licenses, usage policies, and terms of service.<p align="center">
  <strong>AgentChat</strong><br>
  Independent evidence. Explicit disagreement. Structured arbitration.
</p><p align="center">
  独立采集证据，显式保留分歧，统一完成仲裁。
</p>
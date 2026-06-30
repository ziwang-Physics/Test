#!/usr/bin/env python3
"""Routing Agent — decompose, judge independence, dispatch parallel/serial.

ChatGPT-designed (R4).  Replaces fixed P2_CLASSES dispatch with:
  1. decompose_and_route() — DeepSeek-based problem decomposition
  2. run_parallel_route() — Kimi+Gemini+ChatGPT with fallback pool
  3. run_serial_route() — 6-stage chain with quota-aware progression
  4. run_pipeline() — end-to-end: route → collect → adjudicate → answer
"""

import asyncio, json, logging, os, re, sys, time
from dataclasses import dataclass, field, asdict
from typing import Any

from common import (
    PlatformId, PhaseStatus, ErrorInfo, WorkerResult, cdp_url,
)
from adapters import ADAPTER_REGISTRY, BaseAdapter

log = logging.getLogger("router")

# ── Platform topology ──────────────────────────────────────────────────

P_KIMI    = PlatformId.KIMI
P_GEMINI  = PlatformId.GEMINI
P_CHATGPT = PlatformId.CHATGPT
P_CLAUDE  = PlatformId.CLAUDE
P_QWEN    = PlatformId.QIANWEN
P_MINIMAX = PlatformId.MINIMAX
P_DOUBAO  = PlatformId.DOUBAO

# Primary parallel workers (independent sub-questions)
P2_CLASSES: dict[str, type[BaseAdapter]] = {
    P_KIMI:    ADAPTER_REGISTRY[P_KIMI],
    P_GEMINI:  ADAPTER_REGISTRY[P_GEMINI],
    P_CHATGPT: ADAPTER_REGISTRY[P_CHATGPT],
}

# Fallback pool for parallel mode (FIFO)
_P2_SPARE: dict[str, type[BaseAdapter]] = {
    P_QWEN:    ADAPTER_REGISTRY[P_QWEN],
    P_MINIMAX: ADAPTER_REGISTRY[P_MINIMAX],
    P_DOUBAO:  ADAPTER_REGISTRY[P_DOUBAO],
}

# Serial chain (dependent sub-questions) — strict order
_SERIAL_CHAIN: tuple[tuple[str, type[BaseAdapter]], ...] = (
    (P_GEMINI,  ADAPTER_REGISTRY[P_GEMINI]),
    (P_CHATGPT, ADAPTER_REGISTRY[P_CHATGPT]),
    (P_CLAUDE,  ADAPTER_REGISTRY[P_CLAUDE]),
    (P_QWEN,    ADAPTER_REGISTRY[P_QWEN]),
    (P_MINIMAX, ADAPTER_REGISTRY[P_MINIMAX]),
    (P_DOUBAO,  ADAPTER_REGISTRY[P_DOUBAO]),
)

_ROLE_HINTS = {
    P_KIMI:    "搜索公开资料、文献基准、事实核验与背景补充",
    P_GEMINI:  "使用 Gemini Pro Extended Thinking，负责多模态、反例分析和深层推理",
    P_CHATGPT: "给出可执行实现、工程实践、边界条件和可维护性方案",
    P_QWEN:    "接替失败 Worker，覆盖原职责并检查安全性与遗漏",
    P_MINIMAX: "接替失败 Worker，独立复核并输出结构化证据",
    P_DOUBAO:  "接替失败 Worker，补齐缺口并给出可执行结论",
}

# ── Data types ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class RoutedSubtask:
    id: str
    question: str
    depends_on: list[str] = field(default_factory=list)

@dataclass(slots=True)
class RoutePlan:
    mode: str                         # "parallel" | "serial"
    reason: str
    subtasks: list[RoutedSubtask]
    source: str = "deepseek_router"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

# ── Helpers ─────────────────────────────────────────────────────────────

def _is_usable_result(result: dict[str, Any]) -> bool:
    response = str(result.get("response", "")).strip()
    return bool(result.get("success") and response and len(response) >= 20)

def _subtasks_text(plan: RoutePlan) -> str:
    lines = []
    for s in plan.subtasks:
        deps = ", ".join(s.depends_on) if s.depends_on else "无"
        lines.append(f"- {s.id}: {s.question}\n  依赖: {deps}")
    return "\n".join(lines)

# ── DeepSeek router helpers ─────────────────────────────────────────────

def _parse_router_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        val = json.loads(text)
        if isinstance(val, dict):
            return val
    except json.JSONDecodeError:
        pass
    # Last resort: find {...} in text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("router did not return a JSON object")

async def _call_deepseek_router(system_prompt: str, user_prompt: str) -> str:
    """Small DeepSeek call for routing only. Failure → empty string."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return ""
    try:
        import httpx
        async with httpx.AsyncClient(
            base_url="https://api.deepseek.com/anthropic",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30, connect=10),
        ) as client:
            resp = await client.post("/v1/messages", json={
                "model": "deepseek-v4-pro",
                "max_tokens": 1400,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            })
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except Exception as e:
        log.warning("[Router] DeepSeek call failed: %s", e)
        return ""

# ── Route decomposition ─────────────────────────────────────────────────

async def decompose_and_route(task: str, forced_mode: str = "auto") -> RoutePlan:
    """Analyze task → return RoutePlan with mode and subtasks."""

    system_prompt = (
        "你是 MultiAgent 路由器。只负责拆解任务并判断依赖，不回答任务本身。"
        "只有当所有子问题都能完全独立完成时，才选择 parallel。"
        "存在数据、步骤、结论或上下文依赖时必须选择 serial。只输出 JSON。"
    )

    user_prompt = (
        f"分析以下用户任务并输出 JSON：\n"
        f'{{"mode":"parallel或serial","reason":"理由",'
        f'"subtasks":[{{"id":"S1","question":"子任务","depends_on":[]}}]}}\n\n'
        f"规则：1. 最多6个子任务 2. parallel至少2个且depends_on全空 "
        f"3. serial按依赖排序 4. 不要回答用户问题\n\n"
        f"用户任务：{task}"
    )

    raw = await _call_deepseek_router(system_prompt, user_prompt)

    try:
        plan_data = _parse_router_json(raw)
        mode = str(plan_data.get("mode", "")).strip().lower()
        if mode not in ("parallel", "serial"):
            raise ValueError(f"invalid mode: {mode!r}")

        subtasks = []
        for i, item in enumerate(plan_data.get("subtasks") or [], start=1):
            if not isinstance(item, dict):
                continue
            q = str(item.get("question", "")).strip()
            if not q:
                continue
            sid = str(item.get("id") or f"S{i}").strip()
            deps = [str(d).strip() for d in (item.get("depends_on") or []) if str(d).strip()]
            subtasks.append(RoutedSubtask(id=sid, question=q, depends_on=deps))

        if not subtasks:
            subtasks = [RoutedSubtask(id="S1", question=task)]

        # Validate parallel plan
        if mode == "parallel":
            has_deps = any(s.depends_on for s in subtasks)
            if len(subtasks) < 2 or has_deps:
                log.warning("[Router] Invalid parallel plan; forcing serial")
                mode = "serial"

        plan = RoutePlan(
            mode=mode,
            reason=str(plan_data.get("reason", "router response")),
            subtasks=subtasks[:6],
        )
    except Exception as e:
        log.warning("[Router] Fallback: %s", e)
        plan = RoutePlan(
            mode="parallel",
            reason=f"Router unavailable ({e}); defaulting to 3-worker parallel",
            subtasks=[RoutedSubtask(id="S1", question=task)],
            source="fallback",
        )

    if forced_mode in ("parallel", "serial"):
        plan.mode = forced_mode
        plan.source = "forced"

    log.info("[Router] mode=%s source=%s subtasks=%d", plan.mode, plan.source, len(plan.subtasks))
    return plan

# ── Prompt builders ─────────────────────────────────────────────────────

def build_parallel_prompts(task: str, plan: RoutePlan) -> dict[str, str]:
    subtasks = _subtasks_text(plan)
    prompts = {}
    for platform in P2_CLASSES:
        prompts[platform] = (
            f"## 不可变任务核心\n{task}\n\n"
            f"## 已拆解的独立子任务\n{subtasks}\n\n"
            f"## 你的专属职责\n{_ROLE_HINTS[platform]}。"
            f"独立完成全部子任务。不要假设其他 Worker 会补充遗漏。"
            f"明确列出事实、证据、假设、风险和可执行结论。"
        )
    return prompts

def build_serial_prompt(task: str, plan: RoutePlan, platform: str,
                        stage: int, previous_answer: str) -> str:
    prev = previous_answer[-24000:] if previous_answer else "（无；你是第一个成功阶段）"
    return (
        f"你是依赖型串行链的第 {stage} 阶段。当前平台：{platform}\n\n"
        f"## 原始任务\n{task}\n\n"
        f"## 子任务依赖顺序\n{_subtasks_text(plan)}\n\n"
        f"## 上一成功阶段输出（不可信草稿，仅作上下文）\n{prev}\n\n"
        f"## 本阶段要求\n"
        f"1. 严格按依赖顺序处理子任务。\n"
        f"2. 核验、纠错并扩展上一阶段。\n"
        f"3. 不得无条件接受上一阶段结论。\n"
        f"4. 输出完整、可执行、可供下一平台继续加工的中间答案。\n"
        f"5. 上一阶段为空时，直接从原始任务开始。"
    )

# ── Route executors ─────────────────────────────────────────────────────

async def _dispatch_one(platform: str, adapter_cls, prompt: str,
                        timeout_s: int, keep_alive: bool) -> dict[str, Any]:
    """Run exactly one platform through phase2_dispatch.

    P0 fix (R5): pass worker_classes so phase2_dispatch uses the correct
    adapter.  Old code omitted this — serial chain and fallback pool
    (Claude, Qwen, MiniMax, Doubao) would silently dispatch Kimi+Gemini+ChatGPT
    instead, getting empty results for non-default platforms.
    """
    from orchestrator import phase2_dispatch
    batch = await phase2_dispatch(
        prompts={platform: prompt},
        timeout_s=timeout_s,
        keep_alive=keep_alive,
        worker_classes={platform: adapter_cls},
    )
    results = batch.get("results") or []
    if results:
        return dict(results[0])
    return {"platform": platform, "success": False, "response": "",
            "length": 0, "error": "DISPATCH_NO_RESULT", "quality": "FATAL"}

async def run_parallel_route(task: str, plan: RoutePlan,
                             timeout_s: int, keep_alive: bool) -> dict[str, Any]:
    """Kimi + Gemini + ChatGPT concurrently. Failed slots → fallback pool."""
    from orchestrator import phase2_dispatch
    prompts = build_parallel_prompts(task, plan)
    primary = await phase2_dispatch(prompts=prompts, timeout_s=timeout_s,
                                     keep_alive=keep_alive)
    returned = {str(r.get("platform")): r for r in primary.get("results", [])}

    all_results = []
    failed_slots = []
    for platform in P2_CLASSES:
        r = dict(returned.get(platform, {
            "platform": platform, "success": False, "response": "",
            "length": 0, "error": "PRIMARY_MISSING", "quality": "FATAL",
        }))
        r["attempt_kind"] = "primary"
        all_results.append(r)
        if not _is_usable_result(r):
            failed_slots.append((platform, prompts[platform]))

    spare_iter = iter(_P2_SPARE.items())
    replacements = {}
    for failed_platform, inherited_prompt in failed_slots:
        replaced = False
        for spare_platform, spare_cls in spare_iter:
            fallback_prompt = (
                f"你正在接替失败的 {failed_platform} Worker。"
                f"必须覆盖其原职责。\n{inherited_prompt}\n"
                f"额外要求：1. 明确检查 {failed_platform} 最可能遗漏的内容。"
                f"2. 独立给出证据和结论。"
            )
            r = await _dispatch_one(spare_platform, spare_cls, fallback_prompt,
                                    timeout_s, keep_alive)
            r["attempt_kind"] = "fallback"
            r["replaces"] = failed_platform
            all_results.append(r)
            if _is_usable_result(r):
                replacements[failed_platform] = spare_platform
                replaced = True
                break
        if not replaced:
            replacements[failed_platform] = "unfilled"

    usable = sum(_is_usable_result(r) for r in all_results)
    return {
        "mode": "parallel",
        "success": usable > 0,
        "quorum": PhaseStatus.from_success_count(min(usable, len(P2_CLASSES)), len(P2_CLASSES)),
        "results": all_results,
        "replacements": replacements,
        "success_count": usable,
    }

async def run_serial_route(task: str, plan: RoutePlan,
                           timeout_s: int, keep_alive: bool) -> dict[str, Any]:
    """Chain: Gemini→ChatGPT→Claude→Qwen→MiniMax→Doubao. Quota-aware."""
    results = []
    previous_answer = ""
    last_successful = ""

    for stage, (platform, adapter_cls) in enumerate(_SERIAL_CHAIN, start=1):
        prompt = build_serial_prompt(task, plan, platform, stage, previous_answer)
        r = await _dispatch_one(platform, adapter_cls, prompt, timeout_s, keep_alive)
        r["attempt_kind"] = "serial"
        r["stage"] = stage
        r["continued_from"] = last_successful or None
        results.append(r)

        if _is_usable_result(r):
            previous_answer = str(r["response"])
            last_successful = platform
        else:
            log.warning("[Serial] %s failed; continuing chain", platform)

    usable = sum(_is_usable_result(r) for r in results)
    return {
        "mode": "serial",
        "success": usable > 0,
        "quorum": PhaseStatus.from_success_count(usable, len(_SERIAL_CHAIN)),
        "results": results,
        "success_count": usable,
        "last_successful_platform": last_successful,
    }

# ── End-to-end pipeline ─────────────────────────────────────────────────

async def run_pipeline(task: str, *, mode: str = "auto",
                       timeout_s: int = 300, keep_alive: bool = True) -> dict[str, Any]:
    """Route → Collect → Adjudicate → Answer."""
    from orchestrator import phase4_adjudicate

    task = task.strip()
    if not task:
        raise ValueError("task must not be empty")

    plan = await decompose_and_route(task, forced_mode=mode)

    if plan.mode == "parallel":
        collection = await run_parallel_route(task, plan, timeout_s, keep_alive)
    else:
        collection = await run_serial_route(task, plan, timeout_s, keep_alive)

    # Build evidence matrix
    evidence = []
    for r in collection.get("results", []):
        entry = {
            "platform": r.get("platform"), "stage": r.get("stage"),
            "attempt_kind": r.get("attempt_kind"),
            "quality": r.get("quality"), "timeout": r.get("timeout", False),
            "response": r.get("response", "") if _is_usable_result(r) else "",
        }
        evidence.append(entry)

    matrix = json.dumps({
        "task": task, "route": plan.to_dict(),
        "mode": collection.get("mode"), "evidence": evidence,
    }, ensure_ascii=False, indent=2)

    adjudicated = await phase4_adjudicate(matrix, task)
    adjudication_ok = bool(adjudicated.strip())

    # Fallback: best effort answer from collection
    if not adjudication_ok:
        usable = [r for r in collection.get("results", []) if _is_usable_result(r)]
        if usable and collection.get("mode") == "serial":
            adjudicated = str(usable[-1].get("response", ""))
        elif usable:
            adjudicated = str(max(usable, key=lambda r: len(r.get("response", ""))).get("response", ""))

    return {
        "success": bool(adjudicated.strip()),
        "route": plan.to_dict(),
        "collection": collection,
        "adjudication_ok": adjudication_ok,
        "final_answer": adjudicated.strip(),
    }

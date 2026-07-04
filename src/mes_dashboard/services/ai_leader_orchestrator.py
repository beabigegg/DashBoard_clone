# -*- coding: utf-8 -*-
"""AI Leader Orchestrator — leader/subagent pipeline for AI_MODE=leader.

分層設計：
  Leader（本模組）負責與使用者對話：規劃 → 委派 → 彙整。
  Subagent（ai_agent_loop.process_agent_turn）負責單一查詢子任務：
    優先函式路由（ai_functions.yaml registry 工具）；判斷無合適函式時
    fallback 到 query_database（text2sql pipeline，含 schema/業務規則注入
    與 SQL reviewer 審查）。

Pipeline（每個使用者問題最多 2 + N 次 LLM call，N = 子任務內部輪次）：
  1. Planning  — 一次 LLM call 判斷 respond（直接回覆/澄清）或
                 delegate（拆解為 1..MAX_TASKS 個自足的查詢子任務）
  2. Dispatch  — 每個子任務交給一個 query subagent 執行（失敗互相隔離）
  3. Synthesis — 以使用者原始問題 + 全部子任務結果做最終彙整回覆
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from mes_dashboard.services.ai_agent_loop import (
    _generate_clarification_suggestions,
    process_agent_turn,
)
from mes_dashboard.services.ai_query_service import _call_llm, call_llm_text
from mes_dashboard.services.ai_query_understanding import (
    append_to_chat_history,
    get_chat_history,
)

logger = logging.getLogger("mes_dashboard.ai_leader_orchestrator")

MAX_TASKS = 3


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_leader_plan_prompt() -> str:
    """Planning prompt: decide respond vs delegate, and split into subtasks.

    The leader does NOT see tool schemas — it only knows what the query
    subagent is capable of, and must write each subtask as a self-contained
    natural-language goal (the subagent sees only the goal text).
    """
    from datetime import date

    from mes_dashboard.services.ai_business_context import (
        BUSINESS_TERMINOLOGY,
        SYSTEM_OVERVIEW,
    )

    today = date.today().isoformat()

    lines = [
        "你是 MES Dashboard AI 助手的主控（Leader）。你負責與使用者對話，",
        "並決定是否把資料查詢工作委派給查詢子代理（query subagent）。",
        f"今天日期：{today}",
        "",
        "## 系統背景",
        SYSTEM_OVERVIEW,
        "",
        "## 業務術語",
        BUSINESS_TERMINOLOGY,
        "",
        "## 查詢子代理能力",
        "子代理可以查詢：在製品 WIP、Hold、良率、不良、設備狀態/稼動、",
        "停機分析、批次歷程、材料追溯、異常偵測等 MES 生產資料。",
        "子代理會優先使用系統預先註冊的查詢函式；若沒有合適函式，",
        "會自動改用 SQL 生成方式查詢資料庫（已內建完整 schema 與業務規則知識）。",
        "",
        "## 決策規則",
        "- 問候、閒聊、與 MES 資料無關的問題 → action=respond，直接用中文回覆",
        "- 問題缺少關鍵資訊（無法確定查什麼）→ action=respond，用中文提出澄清問題",
        f"- 資料查詢需求 → action=delegate，拆解為 1 到 {MAX_TASKS} 個子任務",
        "- 單一面向的問題只拆 1 個子任務；只有問題明確涉及多個獨立面向"
        "（例如同時要不良率趨勢與 Hold 狀況）才拆多個",
        "",
        "## 子任務撰寫規則",
        "- 每個子任務必須是自足的中文查詢描述：子代理只看得到子任務文字，"
        "看不到使用者原始問題",
        "- 把日期範圍、工站名稱、批次/工單號碼等條件明確寫進每個子任務",
        "- 不要在子任務中指定函式名稱或 SQL——查詢方式由子代理自行決定",
        "",
        "## 回覆格式（嚴格 JSON，禁止其他文字）",
        "委派查詢：",
        '{"action": "delegate", "tasks": ["子任務描述1", "子任務描述2"]}',
        "",
        "直接回覆或澄清：",
        '{"action": "respond", "answer": "<中文回覆內容>"}',
    ]
    return "\n".join(lines)


def build_leader_synthesis_prompt() -> str:
    """Synthesis prompt: merge subtask results into the final user-facing answer."""
    lines = [
        "你是 MES Dashboard AI 助手的主控（Leader），負責彙整查詢子代理的結果，",
        "用繁體中文回答使用者的原始問題。",
        "",
        "## 回覆規則（必須嚴格遵守）",
        "- 直接回答使用者的問題，不要重述問題、不要描述子任務流程",
        "- 只陳述子任務結果中明確存在的事實與數據，不要揣測原因、"
        "不要推論趨勢、不要給出資料中沒有依據的建議",
        "- 跨子任務的結果要整合成連貫的回答，點出 2-3 個最關鍵的數據",
        "- 若某個子任務失敗或無結果，簡短說明該部分查詢未成功，不要編造數據",
        "- 回覆不超過 8 句話",
        "- 不要回覆 JSON、程式碼或 markdown 格式",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_leader_turn(
    question: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Run the leader/subagent pipeline for one user question.

    Returns the AI-03 response shape plus an additive `subtasks` field:
        {
            "answer": str,
            "chart_data": Any,
            "query_used": "leader" | None,
            "params_used": None,
            "suggestions": list[str],
            "needs_clarification": bool,
            "tool_trace": list[dict],
            "subtasks": list[{"goal", "answer", "success"}],
        }

    Raises:
        TimeoutError / ConnectionError: planning LLM call transport failures
        （與其他 pipeline 相同，由 route 層轉為對應錯誤回應）.
    """
    tool_trace: list[dict[str, Any]] = []

    # ── Phase 1: Planning ───────────────────────────────────────────────────
    history = get_chat_history(conversation_id) if conversation_id else []
    plan_messages = [
        {"role": "system", "content": build_leader_plan_prompt()},
        *history,
        {"role": "user", "content": question},
    ]

    try:
        plan = _call_llm(plan_messages)
    except requests.Timeout as exc:
        raise TimeoutError("LLM API 回應逾時") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("LLM API 連線失敗") from exc
    except RuntimeError as exc:
        # Malformed planning JSON — degrade to delegating the whole question
        # as a single subtask instead of failing the turn.
        logger.warning("Leader planning returned unparseable output, degrading: %s", exc)
        plan = {"action": "delegate", "tasks": [question]}

    action = str(plan.get("action") or "").strip().lower()
    tasks = plan.get("tasks") or []
    tasks = [str(t).strip() for t in tasks if str(t).strip()][:MAX_TASKS]

    # ── Respond path: direct answer / clarification, no subagents ───────────
    if action == "respond":
        answer = (plan.get("answer") or "").strip() or "抱歉，我無法理解這個查詢，請換個方式描述。"
        needs_clarification = "?" in answer or "？" in answer
        tool_trace.append({
            "step": 1,
            "function": "leader_plan",
            "summary": f"action=respond: {answer[:80]}",
        })
        return {
            "answer": answer,
            "chart_data": None,
            "query_used": None,
            "params_used": None,
            "suggestions": (
                _generate_clarification_suggestions(question, answer)
                if needs_clarification else []
            ),
            "needs_clarification": needs_clarification,
            "tool_trace": tool_trace,
            "subtasks": [],
        }

    # Delegate path — malformed/empty tasks fall back to the whole question
    if not tasks:
        tasks = [question]

    tool_trace.append({
        "step": 1,
        "function": "leader_plan",
        "summary": f"action=delegate, {len(tasks)} 個子任務: " + " / ".join(t[:40] for t in tasks),
    })
    logger.info("Leader delegating %d subtask(s): %s", len(tasks), tasks)

    # ── Phase 2: Dispatch to query subagents ────────────────────────────────
    subtasks: list[dict[str, Any]] = []
    last_chart_data: Any = None

    for idx, goal in enumerate(tasks, 1):
        try:
            result = process_agent_turn(goal)
            success = True
            sub_answer = result.get("answer") or "（無結果）"
            sub_chart = result.get("chart_data")
            sub_trace = result.get("tool_trace") or []
        except Exception as exc:  # noqa: BLE001 — isolate subagent failures
            logger.warning("Subagent %d failed for goal %r: %s", idx, goal, exc)
            success = False
            sub_answer = f"（子任務執行失敗：{exc}）"
            sub_chart = None
            sub_trace = []

        for entry in sub_trace:
            tool_trace.append({
                "step": len(tool_trace) + 1,
                "function": f"subagent{idx}.{entry.get('function', '')}",
                "summary": entry.get("summary", ""),
                "error": entry.get("error"),
            })

        if sub_chart is not None:
            last_chart_data = sub_chart

        subtasks.append({"goal": goal, "answer": sub_answer, "success": success})

    # ── Phase 3: Synthesis ──────────────────────────────────────────────────
    if not any(st["success"] for st in subtasks):
        # All subagents failed — no data to synthesize, report failure directly.
        answer = "查詢執行失敗：\n" + "\n".join(
            f"- {st['goal']}：{st['answer']}" for st in subtasks
        )
    else:
        lines = [question, "", "## 子任務查詢結果"]
        for idx, st in enumerate(subtasks, 1):
            lines.append(f"### 子任務 {idx}：{st['goal']}")
            lines.append(st["answer"])
        synthesis_messages = [
            {"role": "system", "content": build_leader_synthesis_prompt()},
            {"role": "user", "content": "\n".join(lines)},
        ]
        try:
            answer = (call_llm_text(synthesis_messages) or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Leader synthesis LLM call failed, using fallback: %s", exc)
            answer = ""
        if not answer:
            # Fallback: concatenate subagent answers so data is never lost.
            answer = "\n".join(
                f"{st['goal']}：{st['answer']}" for st in subtasks
            )

    tool_trace.append({
        "step": len(tool_trace) + 1,
        "function": "leader_synthesize",
        "summary": "彙整完成",
    })

    if conversation_id:
        append_to_chat_history(conversation_id, question, answer)

    return {
        "answer": answer,
        "chart_data": last_chart_data,
        "query_used": "leader",
        "params_used": None,
        "suggestions": [],
        "needs_clarification": False,
        "tool_trace": tool_trace,
        "subtasks": subtasks,
    }

# -*- coding: utf-8 -*-
"""AI Agent Loop — orchestrated agentic loop for AI_MODE=agent.

Each request to process_agent_turn() runs up to MAX_ROUNDS independent LLM
calls.  The system assembles each round's prompt from the original question
plus summaries of all previously executed tools.

LLM response format (prompt-based, no native tool calling):
    <tool_call>{"name": "...", "arguments": {...}}</tool_call>

Exits the loop when:
  - LLM response has no <tool_call> tags (final answer)
  - MAX_ROUNDS reached (fallback answer)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mes_dashboard.services.ai_function_registry import build_agent_system_prompt
from mes_dashboard.services.ai_query_service import call_llm_text
from mes_dashboard.services.ai_tool_executor import execute_tool

logger = logging.getLogger("mes_dashboard.ai_agent_loop")

MAX_ROUNDS = 5
_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


def process_agent_turn(question: str) -> dict[str, Any]:
    """Run the agentic loop for one user question.

    Returns:
        {
            "answer": str,
            "chart_data": Any,
            "query_used": str | None,
            "params_used": dict | None,
            "suggestions": list[str],
            "needs_clarification": bool,
            "tool_trace": list[dict],
        }
    """
    system_prompt = build_agent_system_prompt()

    # Accumulated state
    tool_results: list[dict[str, Any]] = []   # {"name": ..., "summary": ..., "chart_data": ...}
    tool_trace: list[dict[str, Any]] = []
    executed_calls: set[str] = set()           # json repr of (name, frozen_args) for dedup
    last_chart_data: Any = None
    last_query_used: str | None = None

    final_answer: str = ""

    for round_num in range(1, MAX_ROUNDS + 1):
        user_message = _build_user_message(question, tool_results)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            llm_response = call_llm_text(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Agent loop Round %d LLM call failed: %s", round_num, exc)
            if tool_results:
                final_answer = _fallback_answer(tool_results)
            else:
                final_answer = f"AI 服務暫時不可用，請稍後再試。({exc})"
            break

        # Parse tool calls from LLM response
        tool_calls = _parse_tool_calls(llm_response)
        had_tool_call_tags = bool(_TOOL_CALL_RE.search(llm_response))

        if not tool_calls:
            if had_tool_call_tags:
                # Tool call blocks present but all failed to parse (malformed JSON).
                # Per spec: skip and continue the loop so LLM can try again.
                logger.warning("Round %d: all <tool_call> blocks failed JSON parse, continuing", round_num)
                continue
            # No tool call tags at all → this is the final answer
            final_answer = _strip_tool_calls(llm_response).strip()
            break

        # Execute tool calls (may be multiple per round)
        for call in tool_calls:
            name = call.get("name", "")
            arguments = call.get("arguments") or {}

            # Dedup check
            call_key = json.dumps({"name": name, "args": arguments}, sort_keys=True, ensure_ascii=False)
            if call_key in executed_calls:
                logger.debug("Skipping duplicate tool call: %s", call_key)
                continue
            executed_calls.add(call_key)

            logger.info("Agent Round %d: executing tool %s with %s", round_num, name, arguments)
            result = execute_tool(name, arguments)

            step = len(tool_trace) + 1
            trace_entry = {
                "step": step,
                "function": name,
                "summary": result.get("result_summary", "")[:200],
                "error": result.get("error"),
            }
            tool_trace.append(trace_entry)

            if result.get("success"):
                tool_results.append({
                    "name": name,
                    "summary": result["result_summary"],
                    "chart_data": result.get("chart_data"),
                })
                if result.get("chart_data") is not None:
                    last_chart_data = result["chart_data"]
                    last_query_used = name
            else:
                # Inform LLM about the error in next round
                tool_results.append({
                    "name": name,
                    "summary": f"（執行失敗：{result.get('error', '未知錯誤')}）",
                    "chart_data": None,
                })

        # After executing tools, continue to next round for final answer
        if round_num == MAX_ROUNDS:
            # Force exit with fallback
            final_answer = _fallback_answer(tool_results)

    # Determine needs_clarification
    # Use len(tool_trace) (attempted) not just successful — if LLM tried a tool
    # but it failed, this is still a data-retrieval attempt, not a clarification.
    tool_calls_attempted = len(tool_trace)
    needs_clarification = (
        tool_calls_attempted == 0
        and ("?" in final_answer or "？" in final_answer)
    )

    suggestions = (
        _generate_clarification_suggestions(question, final_answer)
        if needs_clarification
        else []
    )

    return {
        "answer": final_answer,
        "chart_data": last_chart_data,
        "query_used": last_query_used,
        "params_used": None,
        "suggestions": suggestions,
        "needs_clarification": needs_clarification,
        "tool_trace": tool_trace,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_user_message(question: str, tool_results: list[dict]) -> str:
    """Build the user message for each round: original question + accumulated results."""
    if not tool_results:
        return question

    lines = [question, "", "## 已取得的查詢結果"]
    for tr in tool_results:
        lines.append(f"### {tr['name']}")
        lines.append(tr["summary"])

    return "\n".join(lines)


def _parse_tool_calls(llm_response: str) -> list[dict[str, Any]]:
    """Extract and parse all <tool_call>...</tool_call> blocks from LLM response."""
    calls: list[dict[str, Any]] = []
    for match in _TOOL_CALL_RE.finditer(llm_response):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "name" in parsed:
                calls.append(parsed)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse tool_call JSON: %s", raw[:200])
    return calls


def _strip_tool_calls(text: str) -> str:
    """Remove all <tool_call>...</tool_call> blocks from text."""
    return _TOOL_CALL_RE.sub("", text)


def _generate_clarification_suggestions(question: str, answer: str) -> list[str]:
    """Generate contextual suggestions when the LLM asks for clarification.

    Scans the original question and the clarification answer for category
    keywords, then returns up to 5 actionable follow-up suggestions.
    """
    _CATEGORY_SUGGESTIONS: dict[str, list[str]] = {
        "不良": ["焊接_DB 今日不良率", "全站本週不良率趨勢", "不良原因排行"],
        "良率": ["焊接站今日良率", "全站本週良率趨勢"],
        "在製": ["全站在製品摘要", "站別在製矩陣"],
        "wip": ["全站在製品摘要", "站別在製矩陣"],
        "hold": ["Hold 摘要", "Hold 原因排行"],
        "設備": ["設備稼動率摘要", "設備異常警示"],
        "稼動": ["設備稼動率摘要", "稼動率趨勢"],
        "kpi": ["全廠設備 KPI 總覽"],
        "異常": ["異常偵測總覽", "不良量突增警示"],
    }

    combined = (question + " " + answer).lower()
    seen: set[str] = set()
    suggestions: list[str] = []
    for keyword, suggs in _CATEGORY_SUGGESTIONS.items():
        if keyword in combined:
            for s in suggs:
                if s not in seen:
                    seen.add(s)
                    suggestions.append(s)

    return suggestions[:5]


def _fallback_answer(tool_results: list[dict]) -> str:
    """Generate a fallback answer when max rounds is reached."""
    if not tool_results:
        return "已達查詢輪次上限，未能取得資料。"
    summaries = []
    for tr in tool_results:
        summaries.append(f"- {tr['name']}: {tr['summary'][:300]}")
    return "已達查詢輪次上限，以下是已取得的資料摘要：\n" + "\n".join(summaries)

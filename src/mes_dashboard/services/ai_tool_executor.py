# -*- coding: utf-8 -*-
"""AI Tool Executor — unified dispatcher for agent tool calls.

execute_tool(name, arguments) is the single entry point.  It routes to:
  - YAML registry tools: validate → call service fn → normalize → summarize
  - query_database special tool: delegates to process_query_text2sql()
  - search_tools special tool: keyword search across REGISTRY
  - unknown tool: returns structured error
"""

from __future__ import annotations

import logging
from typing import Any

from mes_dashboard.services.ai_function_registry import (
    REGISTRY,
    get_service_function,
    validate_intent,
)
from mes_dashboard.services.ai_query_service import (
    normalize_chart_data,
    summarize_for_llm,
)

logger = logging.getLogger("mes_dashboard.ai_tool_executor")

_RESULT_MAX_CHARS = 1500


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call and return a standardized result dict.

    Returns:
        {
            "success": bool,
            "result_summary": str,   # LLM-readable text (≤ _RESULT_MAX_CHARS)
            "chart_data": Any,       # normalized chart payload or None
            "error": str | None,
        }
    """
    try:
        if name == "query_database":
            return _execute_query_database(arguments)
        if name == "search_tools":
            return _execute_search_tools(arguments)
        if name in REGISTRY:
            return _execute_yaml_tool(name, arguments)
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"未知工具: {name}",
        }
    except Exception as exc:  # noqa: BLE001 — intentional catch-all
        logger.warning("execute_tool %s raised unexpected error: %s", name, exc)
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"工具執行失敗: {exc}",
        }


# ---------------------------------------------------------------------------
# Internal handlers
# ---------------------------------------------------------------------------

def _execute_yaml_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool from the YAML function registry."""
    # Fill defaults from schema before validation
    entry = REGISTRY[name]
    params_schema = entry.get("params") or {}
    filled: dict[str, Any] = {}
    for pname, pspec in params_schema.items():
        if pname in arguments:
            filled[pname] = arguments[pname]
        elif pspec.get("default") is not None:
            filled[pname] = pspec["default"]

    # Also pass through any extra arguments not in schema (defensive)
    for k, v in arguments.items():
        if k not in filled:
            filled[k] = v

    # Validate
    valid, reason = validate_intent(name, filled)
    if not valid:
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"參數錯誤: {reason}",
        }

    # Call service function
    try:
        service_fn = get_service_function(name)
        raw = service_fn(**filled)
    except TypeError as exc:
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"參數錯誤: {exc}",
        }
    except (KeyError, AttributeError, ImportError) as exc:
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"服務函式載入失敗: {exc}",
        }

    chart_data = normalize_chart_data(name, raw)
    summary = summarize_for_llm(name, chart_data, max_chars=_RESULT_MAX_CHARS)

    return {
        "success": True,
        "result_summary": summary,
        "chart_data": chart_data,
        "error": None,
    }


def _execute_query_database(arguments: dict[str, Any]) -> dict[str, Any]:
    """Delegate to the text2sql pipeline for ad-hoc natural language queries."""
    # Import here to avoid circular imports
    from mes_dashboard.services.ai_query_service import process_query_text2sql

    question = arguments.get("question", "")
    if not question:
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": "query_database 缺少必填參數: question",
        }

    try:
        result = process_query_text2sql(question)
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": f"SQL 查詢失敗: {exc}",
        }

    answer = result.get("answer", "")
    chart_data = result.get("chart_data")
    summary = answer[:_RESULT_MAX_CHARS] if answer else "（查詢無結果）"

    return {
        "success": True,
        "result_summary": summary,
        "chart_data": chart_data,
        "error": None,
    }


def _execute_search_tools(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search REGISTRY by keyword and return matching tool names + descriptions."""
    keyword = str(arguments.get("keyword", "")).strip().lower()
    if not keyword:
        return {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": "search_tools 缺少必填參數: keyword",
        }

    matches: list[str] = []
    for tool_name, entry in REGISTRY.items():
        desc = entry.get("description", "")
        if keyword in tool_name.lower() or keyword in desc.lower():
            matches.append(f"- {tool_name}: {desc}")

    if not matches:
        summary = f"沒有找到包含「{keyword}」的工具。"
    else:
        summary = f"找到 {len(matches)} 個相關工具：\n" + "\n".join(matches)

    return {
        "success": True,
        "result_summary": summary[:_RESULT_MAX_CHARS],
        "chart_data": None,
        "error": None,
    }

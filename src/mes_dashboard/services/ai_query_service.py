# -*- coding: utf-8 -*-
"""AI Query Service — three-round LLM pipeline.

Each user question triggers three sequential internal LLM calls:
  Round 1 — intent classification (function selection)
  Round 2 — parameter filling (single-function schema)
  Round 3 — result summarization (natural language answer)

No conversation history or Redis state between questions.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from mes_dashboard.services.ai_function_registry import (
    REGISTRY,
    build_round1_prompt,
    build_round2_prompt,
    build_round3_prompt,
    get_service_function,
    get_suggestions,
    validate_intent,
)

logger = logging.getLogger("mes_dashboard.ai_query_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_AI_API_URL = os.getenv("AI_API_URL", "https://ollama_pjapi.theaken.com")
_AI_API_KEY = os.getenv("AI_API_KEY", "")
_AI_MODEL = os.getenv("AI_MODEL", "gpt-oss:120b")
_AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", "30"))
_AI_VERIFY_TLS = os.getenv("AI_VERIFY_TLS", "false").strip().lower() in {"1", "true", "yes"}
_AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "500"))

# ID type detection order for auto_resolve_id functions
_ID_RESOLVE_ORDER = ["lot", "workorder"]


# ---------------------------------------------------------------------------
# Auto-resolve ID type
# ---------------------------------------------------------------------------

def _auto_resolve_id(function_name: str, params: dict) -> dict:
    """For functions with auto_resolve_id, detect whether values are LOT IDs or Work Orders.

    Tries LOT mode first via material_trace_service.forward_query;
    if all values are unresolved, retries as workorder.
    """
    if function_name != "material_forward_trace":
        return params

    values = params.get("values", [])
    if not values:
        return params

    from mes_dashboard.services.material_trace_service import forward_query

    wc_groups = params.get("workcenter_groups")

    for mode in _ID_RESOLVE_ORDER:
        try:
            result = forward_query(mode=mode, values=values, workcenter_groups=wc_groups)
            rows = result.get("rows", [])
            unresolved = (result.get("meta") or {}).get("unresolved", [])
            if rows or len(unresolved) < len(values):
                # Found at least some matches — use this mode
                params["mode"] = mode
                logger.info("Auto-resolved ID type: mode=%s (rows=%d, unresolved=%d)",
                            mode, len(rows), len(unresolved))
                # Store the pre-fetched result to avoid double query
                params["_prefetched_result"] = result
                return params
        except Exception:
            logger.warning("Auto-resolve failed for mode=%s, trying next", mode)
            continue

    # All modes failed — default to lot
    params["mode"] = "lot"
    return params


# ---------------------------------------------------------------------------
# LLM API calls
# ---------------------------------------------------------------------------

def _call_llm(messages: list[dict], max_tokens: int | None = None) -> dict:
    """POST to LLM API and return the parsed JSON dict.

    Raises:
        requests.Timeout: on timeout
        requests.ConnectionError: on connection failure
        RuntimeError: on HTTP error or JSON parse failure
    """
    url = f"{_AI_API_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {_AI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": _AI_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens or _AI_MAX_TOKENS,
    }

    response = requests.post(
        url,
        headers=headers,
        json=body,
        verify=_AI_VERIFY_TLS,
        timeout=_AI_REQUEST_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(f"LLM API HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()
    msg = data.get("choices", [{}])[0].get("message", {})
    content = msg.get("content") or msg.get("reasoning_content") or ""

    try:
        return json.loads(content.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to find the last JSON object (LLM sometimes prepends reasoning text)
    for match in reversed(list(re.finditer(r"\{[^{}]*\}", content))):
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            continue

    # Nested JSON fallback (greedy)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    # Last resort: try to find a known function name in the text
    for func_name in REGISTRY:
        if func_name in content:
            logger.warning("LLM returned non-JSON, extracted function name: %s", func_name)
            return {"function": func_name, "explanation": "（自動從 LLM 回應中提取）"}

    raise RuntimeError(f"Could not extract JSON from LLM response: {content[:300]}")


def _call_llm_text(messages: list[dict], max_tokens: int | None = None) -> str:
    """POST to LLM API and return raw text content (no JSON extraction).

    Used for Round 3 where the LLM returns natural language, not JSON.
    Returns empty string on any failure.
    """
    url = f"{_AI_API_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {_AI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": _AI_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens or _AI_MAX_TOKENS,
    }

    response = requests.post(
        url,
        headers=headers,
        json=body,
        verify=_AI_VERIFY_TLS,
        timeout=_AI_REQUEST_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(f"LLM API HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()
    msg = data.get("choices", [{}])[0].get("message", {})
    return msg.get("content") or msg.get("reasoning_content") or ""


# ---------------------------------------------------------------------------
# Result truncation for Round 3
# ---------------------------------------------------------------------------

def _summarize_for_llm(function_name: str, chart_data: Any, max_chars: int = 4500) -> str:
    """Truncate query results to fit within LLM context for Round 3."""
    if chart_data is None:
        return "（查詢結果為空）"

    entry = REGISTRY.get(function_name, {})
    chart_type = entry.get("chart_type", "")

    if chart_type == "pareto":
        # Full — typically 10-20 items
        text = json.dumps(chart_data, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "...(截斷)"

    if chart_type == "trend":
        items = chart_data if isinstance(chart_data, list) else []
        if len(items) > 30:
            head = items[:5]
            tail = items[-5:]
            # Compute numeric stats on first numeric value field
            numeric_vals: list[float] = []
            if items:
                sample_keys = [k for k, v in items[0].items() if isinstance(v, (int, float))]
                val_key = sample_keys[0] if sample_keys else None
                if val_key:
                    numeric_vals = [it[val_key] for it in items if isinstance(it.get(val_key), (int, float))]
            stats: dict[str, Any] = {"共": len(items)}
            if numeric_vals:
                stats["最小"] = min(numeric_vals)
                stats["最大"] = max(numeric_vals)
                stats["平均"] = round(sum(numeric_vals) / len(numeric_vals), 4)
            truncated = {"前5筆": head, "後5筆": tail, "統計": stats}
            text = json.dumps(truncated, ensure_ascii=False)
        else:
            text = json.dumps(chart_data, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "...(截斷)"

    if chart_type == "heatmap":
        if isinstance(chart_data, dict):
            data_points = chart_data.get("data", [])
            sorted_points = sorted(data_points, key=lambda p: p[2] if len(p) > 2 else 0, reverse=True)
            top10 = sorted_points[:10]
            truncated = {
                "xAxis": chart_data.get("xAxis", []),
                "yAxis": chart_data.get("yAxis", []),
                "top10_cells": top10,
                "總計格數": len(data_points),
            }
            text = json.dumps(truncated, ensure_ascii=False)
        else:
            text = json.dumps(chart_data, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "...(截斷)"

    if chart_type == "kpi":
        text = json.dumps(chart_data, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "...(截斷)"

    if chart_type == "table":
        rows = chart_data if isinstance(chart_data, list) else []
        total = len(rows)
        if total > 10:
            # Keep first 10 rows, limit to 5 important columns
            subset = rows[:10]
            if subset and isinstance(subset[0], dict):
                keys = list(subset[0].keys())[:5]
                subset = [{k: row.get(k) for k in keys} for row in subset]
            text = json.dumps({"共": f"{total}筆", "前10筆": subset}, ensure_ascii=False)
        else:
            text = json.dumps(chart_data, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "...(截斷)"

    # Fallback
    text = json.dumps(chart_data, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(截斷)"


# ---------------------------------------------------------------------------
# Chart data normalisation — raw service output → AiChartRenderer format
# ---------------------------------------------------------------------------

def _normalize_chart_data(function_name: str, raw: Any) -> Any:
    """Transform raw service output into the shape AiChartRenderer expects."""
    if raw is None:
        return None

    if isinstance(raw, tuple):
        raw = raw[0] if raw else None
        if raw is None:
            return None

    fn = function_name or ""

    # ── Dashboard ──────────────────────────────────────────────────────────
    if fn == "dashboard_kpi":
        if not isinstance(raw, dict):
            return raw
        return [
            {"label": "設備總數", "value": raw.get("total", 0)},
            {"label": "生產中 (PRD)", "value": raw.get("prd", 0)},
            {"label": "待機 (SBY)", "value": raw.get("sby", 0)},
            {"label": "非計畫停機 (UDT)", "value": raw.get("udt", 0)},
            {"label": "計畫停機 (SDT)", "value": raw.get("sdt", 0)},
            {"label": "工程時間 (EGT)", "value": raw.get("egt", 0)},
            {"label": "稼動率 OU%", "value": round(raw.get("ou_pct", 0), 1)},
        ]

    if fn == "ou_trend":
        if not isinstance(raw, list):
            return raw
        return [
            {
                "date": it.get("date", ""),
                "ou_pct": round(it.get("ou_pct", 0), 1),
                "prd_hours": round(it.get("prd_hours", 0), 1),
            }
            for it in raw
        ]

    if fn == "utilization_heatmap":
        if not isinstance(raw, list):
            return raw
        workcenters = sorted(set(it.get("workcenter", "") for it in raw))
        dates = sorted(set(it.get("date", "") for it in raw))
        lookup = {(it.get("workcenter"), it.get("date")): it.get("prd_pct", 0) for it in raw}
        data_points = []
        for xi, wc in enumerate(workcenters):
            for yi, dt in enumerate(dates):
                val = lookup.get((wc, dt), 0)
                if val:
                    data_points.append([xi, yi, round(val, 1)])
        return {"xAxis": workcenters, "yAxis": dates, "data": data_points}

    # ── Reject ─────────────────────────────────────────────────────────────
    if fn == "reject_summary":
        if not isinstance(raw, dict):
            return raw
        return [
            {"label": "投入量", "value": raw.get("MOVEIN_QTY", 0)},
            {"label": "不良總數", "value": raw.get("REJECT_TOTAL_QTY", 0)},
            {"label": "不良率 %", "value": round(raw.get("REJECT_RATE_PCT", 0), 2)},
            {"label": "缺陷數", "value": raw.get("DEFECT_QTY", 0)},
            {"label": "缺陷率 %", "value": round(raw.get("DEFECT_RATE_PCT", 0), 2)},
            {"label": "影響批次", "value": raw.get("AFFECTED_LOTS", 0)},
        ]

    if fn in ("reject_reason_pareto", "hold_reason_pareto", "reject_dimension_pareto"):
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        categories = []
        values = []
        for item in items:
            categories.append(
                item.get("reason") or item.get("name") or item.get("label")
                or item.get("dimension_value") or ""
            )
            values.append(
                item.get("metric_value") or item.get("qty") or item.get("value") or 0
            )
        return {"categories": categories, "values": values}

    if fn == "reject_trend":
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        return [
            {
                "date": it.get("bucket_date", ""),
                "reject_rate": it.get("REJECT_RATE_PCT", 0),
                "movein_qty": it.get("MOVEIN_QTY", 0),
            }
            for it in items
        ]

    # ── Yield ──────────────────────────────────────────────────────────────
    if fn == "yield_summary":
        if not isinstance(raw, dict):
            return raw
        summary = raw.get("summary", raw)
        return [
            {"label": "投入量", "value": summary.get("transaction_qty", 0)},
            {"label": "報廢數", "value": summary.get("scrap_qty", 0)},
            {"label": "良率 %", "value": round(summary.get("yield_pct", 0), 2)},
        ]

    if fn == "yield_trend":
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        return [
            {
                "date": it.get("date_bucket", it.get("date", "")),
                "yield_pct": round(it.get("yield_pct", 0), 2),
                "transaction_qty": it.get("transaction_qty", 0),
            }
            for it in items
        ]

    if fn == "yield_anomaly_drilldown":
        items = raw if isinstance(raw, list) else raw.get("items", []) if isinstance(raw, dict) else []
        return [
            {
                "date": it.get("date", ""),
                "yield_pct": it.get("yield_pct", 0),
                "transaction_qty": it.get("transaction_qty", 0),
            }
            for it in items
        ]

    # ── WIP ────────────────────────────────────────────────────────────────
    if fn == "wip_matrix":
        workcenters = raw.get("workcenters", [])
        packages = raw.get("packages", [])
        matrix = raw.get("matrix", {})
        data_points = []
        for xi, wc in enumerate(workcenters):
            wc_row = matrix.get(wc, {})
            for yi, pkg in enumerate(packages):
                val = wc_row.get(pkg, 0)
                if val:
                    data_points.append([xi, yi, val])
        return {"xAxis": workcenters, "yAxis": packages, "data": data_points}

    if fn == "wip_summary":
        by_status = raw.get("byWipStatus", {})
        return [
            {"label": "總批次", "value": raw.get("totalLots", 0)},
            {"label": "RUN", "value": (by_status.get("run") or {}).get("lots", 0)},
            {"label": "QUEUE", "value": (by_status.get("queue") or {}).get("lots", 0)},
            {"label": "HOLD", "value": (by_status.get("hold") or {}).get("lots", 0)},
            {"label": "品質 Hold", "value": (by_status.get("qualityHold") or {}).get("lots", 0)},
        ]

    if fn == "wip_hold_summary":
        return [
            {"label": "Hold 批次", "value": raw.get("totalLots", 0)},
            {"label": "Hold 數量", "value": raw.get("totalQty", 0)},
            {"label": "平均天數", "value": round(raw.get("avgAge", 0), 1)},
            {"label": "最長天數", "value": round(raw.get("maxAge", 0), 1)},
            {"label": "涉及站別", "value": raw.get("workcenterCount", 0)},
        ]

    # ── Hold ───────────────────────────────────────────────────────────────
    if fn == "hold_history_trend":
        days = raw.get("days", []) if isinstance(raw, dict) else raw
        return [
            {
                "date": d.get("date", ""),
                "hold_qty": (d.get("all") or {}).get("holdQty", 0),
                "new_hold": (d.get("all") or {}).get("newHoldQty", 0),
                "release": (d.get("all") or {}).get("releaseQty", 0),
            }
            for d in days
        ]

    if fn == "hold_duration_distribution":
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        categories = []
        values = []
        for item in items:
            categories.append(item.get("range_label", ""))
            values.append(item.get("count", 0))
        return {"categories": categories, "values": values}

    # ── Equipment ──────────────────────────────────────────────────────────
    if fn == "equipment_status_summary":
        by_status = raw.get("by_status_category", raw.get("by_status", {}))
        items = [{"label": "設備總數", "value": raw.get("total_count", 0)}]
        for k, v in by_status.items():
            items.append({"label": k, "value": v})
        ou = raw.get("ou_pct")
        if ou is not None:
            items.append({"label": "稼動率 %", "value": round(ou, 1)})
        return items

    if fn == "equipment_recent_jobs":
        if isinstance(raw, dict):
            return raw.get("data", [])
        return raw

    if fn == "job_txn_history":
        if isinstance(raw, dict):
            return raw.get("data", [])
        return raw

    if fn == "workcenter_status_matrix":
        # Already list of dicts with workcenter_group + status counts
        if isinstance(raw, list):
            return raw
        return raw

    # ── Anomaly overview ───────────────────────────────────────────────────
    if fn == "anomaly_summary":
        if not isinstance(raw, dict):
            return raw
        items = [{"label": "異常總數", "value": raw.get("total", 0)}]
        by_detector = raw.get("by_detector", {})
        _labels = {"yield": "良率異常", "reject": "不良突增", "hold": "Hold 異常", "equipment": "設備異常"}
        for det, label in _labels.items():
            count = by_detector.get(det, {}).get("count", 0) if isinstance(by_detector.get(det), dict) else by_detector.get(det, 0)
            items.append({"label": label, "value": count})
        severity = raw.get("severity", "")
        if severity:
            items.append({"label": "嚴重程度", "value": severity})
        return items

    # ── Table types (extract items from wrapper) ───────────────────────────
    if fn in (
        "reject_spike_alerts",
        "yield_anomaly_alerts",
        "hold_outlier_alerts",
        "equipment_deviation_alerts",
        "reject_lot_list",
        "hold_lot_list",
        "yield_alert_candidates",
        "wip_workcenter_detail",
    ):
        if isinstance(raw, dict):
            return raw.get("items", raw.get("lots", []))
        return raw

    if fn == "hold_overview_treemap":
        # Treemap returns nested structure; flatten to table
        if isinstance(raw, dict):
            items = raw.get("children", raw.get("items", []))
            if isinstance(items, list):
                return items
        return raw

    # ── Lot investigation ──────────────────────────────────────────────────
    if fn == "lot_query":
        if isinstance(raw, dict) and "items" not in raw:
            return [raw]
        return raw

    if fn in ("lot_production_history", "lot_rejects", "lot_holds",
              "lot_materials", "adjacent_lots"):
        if isinstance(raw, dict):
            rows = raw.get("rows", raw.get("items", raw.get("data", [])))
            # Preserve unresolved info for empty results
            unresolved = (raw.get("meta") or {}).get("unresolved") or (raw.get("quality_meta") or {}).get("unresolved")
            if not rows and unresolved:
                return {"items": [], "unresolved": unresolved}
            return rows
        return raw

    # ── Material trace ─────────────────────────────────────────────────────
    if fn in ("material_forward_trace", "material_reverse_trace"):
        if isinstance(raw, dict):
            rows = raw.get("rows", raw.get("items", []))
            unresolved = (raw.get("meta") or {}).get("unresolved") or (raw.get("quality_meta") or {}).get("unresolved")
            if not rows and unresolved:
                return {"items": [], "unresolved": unresolved}
            return rows
        return raw

    # ── Resource status history ────────────────────────────────────────────
    if fn == "resource_status_history":
        if isinstance(raw, dict):
            items = raw.get("items", raw.get("rows", []))
            return [
                {
                    "date": it.get("date", it.get("DATE", "")),
                    "ou_pct": round(it.get("ou_pct", it.get("OU_PCT", 0)), 1),
                    "prd_hours": round(it.get("prd_hours", it.get("PRD_HOURS", 0)), 1),
                }
                for it in items
            ] if items else raw
        return raw

    # ── Mid-section defect ─────────────────────────────────────────────────
    if fn == "mid_section_defect_analysis":
        if isinstance(raw, dict):
            # Extract station-level summary or items
            stations = raw.get("stations", raw.get("items", []))
            if isinstance(stations, list):
                return stations
            return raw
        return raw

    return raw


# ---------------------------------------------------------------------------
# Main entry point — three-round pipeline
# ---------------------------------------------------------------------------

def process_query(question: str) -> dict[str, Any]:
    """Process a user question through the three-round LLM pipeline.

    Args:
        question: Natural language question in Chinese.

    Returns:
        dict with keys: answer, chart_data, query_used, params_used, suggestions

    Raises:
        TimeoutError: EXTERNAL_SERVICE_TIMEOUT
        ConnectionError: EXTERNAL_SERVICE_ERROR
        ValueError: VALIDATION_ERROR — invalid intent params
    """
    # ── Round 1: Intent classification ─────────────────────────────────────
    r1_messages = [
        {"role": "system", "content": build_round1_prompt()},
        {"role": "user", "content": question},
    ]
    try:
        r1_result = _call_llm(r1_messages, max_tokens=200)
    except requests.Timeout as exc:
        raise TimeoutError("LLM API 回應逾時") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("LLM API 連線失敗") from exc
    except RuntimeError as exc:
        raise ConnectionError(str(exc)) from exc

    function_name = r1_result.get("function")
    explanation = r1_result.get("explanation", "")
    logger.info("Round 1 result: function=%s, explanation=%s", function_name, explanation)

    # Null intent — LLM cannot match any function
    if not function_name:
        return {
            "answer": explanation or "抱歉，我無法理解這個查詢，請換個方式描述",
            "chart_data": None,
            "query_used": None,
            "params_used": None,
            "suggestions": [],
        }

    # ── Round 2: Parameter filling ──────────────────────────────────────────
    try:
        r2_system = build_round2_prompt(function_name)
    except KeyError:
        raise ValueError(f"未知函式：{function_name}")

    r2_messages = [
        {"role": "system", "content": r2_system},
        {"role": "user", "content": question},
    ]
    try:
        r2_result = _call_llm(r2_messages, max_tokens=300)
    except requests.Timeout as exc:
        raise TimeoutError("LLM API 回應逾時") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("LLM API 連線失敗") from exc
    except RuntimeError as exc:
        raise ConnectionError(str(exc)) from exc

    params = r2_result.get("params") or {}
    clarification = r2_result.get("clarification")
    logger.info("Round 2 result: params=%s, clarification=%s", params, clarification)

    # If LLM needs more info from user, return clarification directly
    if clarification:
        return {
            "answer": clarification,
            "chart_data": None,
            "query_used": function_name,
            "params_used": params,
            "suggestions": get_suggestions(function_name),
        }

    # Fill default params from YAML schema
    entry = REGISTRY.get(function_name, {})
    for param_name, pspec in (entry.get("params") or {}).items():
        if param_name not in params and "default" in pspec:
            params[param_name] = pspec["default"]

    # Auto-resolve ID type for functions that support it
    if entry.get("auto_resolve_id") and "values" in params:
        params = _auto_resolve_id(function_name, params)

    # Validate params
    valid, reason = validate_intent(function_name, params)
    if not valid:
        raise ValueError(reason)

    # ── Service dispatch ────────────────────────────────────────────────────
    # Use prefetched result from auto_resolve_id if available
    prefetched = params.pop("_prefetched_result", None)
    try:
        if prefetched is not None:
            chart_data = prefetched
        else:
            service_fn = get_service_function(function_name)
            chart_data = service_fn(**params)
    except (KeyError, AttributeError, ImportError) as exc:
        logger.error("Service dispatch failed for %s: %s", function_name, exc)
        raise ConnectionError(f"服務函式載入失敗：{exc}") from exc
    except TypeError as exc:
        logger.error("Service function %s called with wrong params %s: %s", function_name, params, exc)
        raise ValueError(f"參數不符合服務函式要求：{exc}") from exc

    logger.info("Service %s returned type=%s, is_none=%s", function_name, type(chart_data).__name__, chart_data is None)
    chart_data = _normalize_chart_data(function_name, chart_data)
    logger.info("Normalized chart_data type=%s, is_none=%s, len=%s",
                type(chart_data).__name__, chart_data is None,
                len(chart_data) if isinstance(chart_data, (list, dict)) else "N/A")

    # ── Check for empty / unresolved results ─────────────────────────────────
    _is_empty = (
        chart_data is None
        or chart_data == []
        or chart_data == {}
        or (isinstance(chart_data, dict) and not chart_data.get("items") and chart_data.get("unresolved"))
    )

    if _is_empty:
        # Build informative message without wasting a Round 3 LLM call
        if isinstance(chart_data, dict) and chart_data.get("unresolved"):
            unresolved_ids = ", ".join(chart_data["unresolved"])
            answer = f"找不到以下項目：{unresolved_ids}。請確認 ID 是否正確。"
            chart_data = None
        else:
            answer = f"查詢完成，但 {function_name} 沒有回傳任何資料。可能該條件下無符合的紀錄。"
    else:
        # ── Round 3: Result summarization ──────────────────────────────────
        truncated_result = _summarize_for_llm(function_name, chart_data)
        r3_user_content = f"{question}\n\n## 查詢結果（{function_name}）\n{truncated_result}"
        r3_messages = [
            {"role": "system", "content": build_round3_prompt()},
            {"role": "user", "content": r3_user_content},
        ]

        try:
            answer = _call_llm_text(r3_messages, max_tokens=500)
            if not answer:
                answer = "查詢完成，請參考圖表。"
        except Exception:
            logger.warning("Round 3 summarization failed for %s, using fallback", function_name)
            answer = "查詢完成，請參考圖表。"

    suggestions = get_suggestions(function_name)

    return {
        "answer": answer,
        "chart_data": chart_data,
        "query_used": function_name,
        "params_used": params,
        "suggestions": suggestions,
    }

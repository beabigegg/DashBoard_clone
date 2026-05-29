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
    build_stage1_prompt,
    build_stage2_prompt,
    get_service_function,
    get_suggestions,
    validate_intent,
)
from mes_dashboard.services.ai_query_understanding import advance_query_state

import pandas as pd

logger = logging.getLogger("mes_dashboard.ai_query_service")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_AI_API_URL = os.getenv("AI_API_URL", "https://ollama_pjapi.theaken.com")
_AI_API_KEY = os.getenv("AI_API_KEY", "")
_AI_MODEL = os.getenv("AI_MODEL", "mlx-community/gpt-oss-120b-MXFP4-Q4")
_AI_REQUEST_TIMEOUT = int(os.getenv("AI_REQUEST_TIMEOUT", "60"))
_AI_VERIFY_TLS = os.getenv("AI_VERIFY_TLS", "false").strip().lower() in {"1", "true", "yes"}
# Disable reasoning/thinking for structured JSON calls (default: disabled).
# Set AI_ENABLE_THINK=true only if the model supports it and you want reasoning traces.
_AI_ENABLE_THINK: bool = os.getenv("AI_ENABLE_THINK", "false").strip().lower() in {"1", "true", "yes", "on"}
# Force the model to output only valid JSON (OpenAI-compatible response_format).
# Disable with AI_FORCE_JSON_FORMAT=false if the model rejects the parameter.
_AI_FORCE_JSON_FORMAT: bool = os.getenv("AI_FORCE_JSON_FORMAT", "true").strip().lower() not in {"0", "false", "no", "off"}
# No max_tokens cap — internal LLM with 131K context, no token cost.
_AI_MODE = os.getenv("AI_MODE", "text2sql")  # "text2sql" | "function"

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

def _repair_json_strings(text: str) -> str:
    """Escape unescaped control characters inside JSON string values.

    Reasoning models sometimes emit literal newlines/tabs inside JSON strings
    instead of the required \\n/\\t escape sequences.  This function uses a
    simple state machine that tracks whether the current position is inside a
    quoted string (handling backslash escapes) and replaces bare control chars
    with their JSON escape equivalents.  Characters outside strings are left
    unchanged, so structural newlines (pretty-printing) survive intact.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\" and in_string:
            out.append(ch)
            escaped = True
        elif ch == '"':
            in_string = not in_string
            out.append(ch)
        elif in_string and ch == "\n":
            out.append("\\n")
        elif in_string and ch == "\r":
            out.append("\\r")
        elif in_string and ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


def _try_parse_json(text: str) -> dict | None:
    """Try json.loads; on failure, try again after repairing literal control chars."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    repaired = _repair_json_strings(text)
    try:
        return json.loads(repaired)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_json_from_text(text: str) -> dict | None:
    """Extract the last valid JSON object from text.

    Handles: <think>…</think> tags, ```json code blocks, inline JSON objects
    with arbitrary nesting, and literal newlines inside JSON strings (repaired
    via _repair_json_strings).  Returns the *last* match because reasoning
    models typically put the final answer at the end.
    """
    if not text:
        return None

    # 1. Strip <think>…</think> blocks, then try direct parse (with repair)
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped:
        result = _try_parse_json(stripped)
        if result is not None:
            return result

    # 2. Extract from the last ```json … ``` or ``` … ``` code block
    for m in reversed(list(re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL))):
        result = _try_parse_json(m.group(1))
        if result is not None:
            return result

    # 3. Brace-depth scan — find all *top-level* JSON objects, return the last valid one.
    # Only consider positions where the brace depth was 0 (not nested inside another object).
    top_level_starts: list[int] = []
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                top_level_starts.append(i)
            depth += 1
        elif ch == "}":
            depth -= 1

    for start in reversed(top_level_starts):
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    result = _try_parse_json(text[start : i + 1])
                    if result is not None:
                        return result
                    break  # this start position failed; try the next

    return None


def _call_llm(messages: list[dict]) -> dict:
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
    body: dict = {
        "model": _AI_MODEL,
        "messages": messages,
        "stream": False,
        "think": _AI_ENABLE_THINK,  # False by default; suppresses reasoning preamble
    }
    if _AI_FORCE_JSON_FORMAT:
        # OpenAI-compatible standard parameter
        body["response_format"] = {"type": "json_object"}
        # Ollama-specific extension: also accepted on /v1/chat/completions
        body["format"] = "json"

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
    content: str = msg.get("content") or ""
    reasoning: str = msg.get("reasoning_content") or ""

    # Happy path: content has JSON directly
    result = _extract_json_from_text(content)
    if result is not None:
        return result

    # Thinking model: content is empty but reasoning_content has the full chain.
    # 1. Try to find a JSON object embedded in the reasoning text.
    if reasoning:
        result = _extract_json_from_text(reasoning)
        if result is not None:
            return result

        # 2. Model finished reasoning but forgot to output the JSON answer.
        #    Make a focused follow-up call with the reasoning as context.
        logger.debug("Content empty after reasoning (%d chars) — making extraction call", len(reasoning))
        extraction_body: dict = {
            "model": _AI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"你已完成分析：\n{reasoning[:2000]}\n\n"
                        "現在請只輸出 JSON 答案，不要任何說明文字。"
                    ),
                }
            ],
            "stream": False,
            "format": "json",
            "response_format": {"type": "json_object"},
        }
        try:
            extraction_resp = requests.post(
                url, headers=headers, json=extraction_body,
                verify=_AI_VERIFY_TLS, timeout=_AI_REQUEST_TIMEOUT,
            )
            if extraction_resp.ok:
                ex_msg = extraction_resp.json().get("choices", [{}])[0].get("message", {})
                extracted_content = ex_msg.get("content") or ""
                result = _extract_json_from_text(extracted_content)
                if result is not None:
                    return result
        except Exception as exc:
            logger.debug("Extraction follow-up call failed: %s", exc)

    # Last resort: find a known function name in combined text
    combined = content + reasoning
    for func_name in REGISTRY:
        if func_name in combined:
            logger.warning("LLM returned non-JSON, extracted function name: %s", func_name)
            return {"function": func_name, "explanation": "（自動從 LLM 回應中提取）"}

    logger.debug("Full LLM content (%d chars): %s", len(content or reasoning), (content or reasoning)[:600])
    raise RuntimeError(f"Could not extract JSON from LLM response: {(content or reasoning)[:300]}")


def call_llm_text(messages: list[dict]) -> str:
    """POST to LLM API and return raw text content (no JSON extraction).

    Used by Round 3 (natural language answer) and the agent loop.
    Raises RuntimeError on HTTP failure.
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

def summarize_for_llm(function_name: str, chart_data: Any, max_chars: int = 20000) -> str:
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
        if len(items) > 200:
            head = items[:20]
            tail = items[-20:]
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
            truncated = {"前20筆": head, "後20筆": tail, "統計": stats}
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
        if total > 50:
            subset = rows[:50]
            text = json.dumps({"共": f"{total}筆", "前50筆": subset}, ensure_ascii=False)
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

def normalize_chart_data(function_name: str, raw: Any) -> Any:
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
# Text-to-SQL helpers
# ---------------------------------------------------------------------------

def _coerce_date_params(params: dict) -> dict:
    """Convert date-like string params to datetime objects.

    LLM often generates date params as:
      - 'YYYY-MM-DD' strings  →  convert to datetime
      - 'SYSDATE', 'SYSDATE-7' etc.  →  resolve to actual datetime

    Oracle bind variables need Python datetime objects; passing string
    literals like 'SYSDATE-7' causes ORA-01858/ORA-01861.
    """
    from datetime import datetime, timedelta

    now = datetime.now()

    result = {}
    for key, value in params.items():
        if not isinstance(value, str):
            result[key] = value
            continue

        v = value.strip().upper()

        # Handle SYSDATE / SYSDATE-N / SYSDATE+N
        if v.startswith("SYSDATE"):
            offset_days = 0
            rest = v[7:].strip()
            if rest:
                m = re.match(r"^([+-])\s*(\d+)", rest)
                if m:
                    offset_days = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
            result[key] = now + timedelta(days=offset_days)
            continue

        # Handle YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            try:
                result[key] = datetime.strptime(value, "%Y-%m-%d")
                continue
            except ValueError:
                pass

        result[key] = value
    return result


# ---------------------------------------------------------------------------
# SQL reviewer — LLM-based logic validation before execution
# ---------------------------------------------------------------------------

def _review_sql(
    question: str,
    sql: str,
    params: dict,
    domains: list[str],
) -> str:
    """Review generated SQL for business logic errors using LLM.

    The reviewer only identifies issues — it does NOT rewrite SQL.
    Issues are fed back to Stage 2 LLM for correction.

    Returns:
        issue_summary — empty string if approved, otherwise a description of problems.
    """
    deterministic_issues = _deterministic_review_issues(question, sql, domains)
    if deterministic_issues:
        issue_summary = "; ".join(deterministic_issues)
        logger.info("Reviewer deterministically rejected SQL: %s", issue_summary)
        return issue_summary

    from mes_dashboard.services.ai_function_registry import build_reviewer_prompt

    review_messages = [
        {"role": "system", "content": build_reviewer_prompt(domains)},
        {"role": "user", "content": (
            f"使用者問題：{question}\n"
            f"選定的 domain：{', '.join(domains)}\n\n"
            f"生成的 SQL：\n{sql}\n\n"
            f"參數：{json.dumps(params, ensure_ascii=False)}\n\n"
            f"請審查此 SQL 是否正確回答使用者的問題。"
        )},
    ]

    try:
        result = _call_llm(review_messages)
    except Exception as exc:
        # Fail-closed: if the reviewer is unavailable, refuse to execute rather
        # than silently approving — a downed reviewer must not become a bypass.
        logger.warning("Reviewer LLM call failed, rejecting SQL: %s", exc)
        return "LLM 審查服務暫時不可用，拒絕執行"

    if result.get("approved", True):
        return ""

    issues = result.get("issues", [])
    issue_summary = "; ".join(issues) if issues else "審查未通過"
    logger.info("Reviewer rejected SQL: %s", issue_summary)
    return issue_summary


def _deterministic_review_issues(question: str, sql: str, domains: list[str]) -> list[str]:
    """Run deterministic SQL checks for known business-critical rules.

    These checks catch high-frequency logical misses before asking LLM reviewer.
    """
    issues: list[str] = []
    q = (question or "").strip()
    sql_upper = (sql or "").upper()
    domain_set = {d.strip().lower() for d in (domains or [])}

    is_rate_query = any(token in q for token in ("良率", "不良率", "報廢率", "yield", "reject rate"))
    mentions_station = any(token in q for token in ("站點", "站別", "工站"))
    rate_domain = bool(domain_set.intersection({"yield", "reject"}))

    if is_rate_query and mentions_station and rate_domain:
        has_station_group = "WORKCENTER_GROUP" in sql_upper or "WORK_CENTER_GROUP" in sql_upper
        grouped_by_station_name = bool(re.search(r"GROUP\s+BY[\s\S]*WORKCENTERNAME", sql_upper))
        if grouped_by_station_name and not has_station_group:
            issues.append(
                "問題在問站點層級統計時應以 WORKCENTER_GROUP 彙總，不可僅以 WORKCENTERNAME 分組。"
                "請改用 WORKCENTER_GROUP（或透過 SPEC 對照映射後再分組）。"
            )

    uses_reject_history = "DW_MES_LOTREJECTHISTORY" in sql_upper
    if is_rate_query and rate_domain and uses_reject_history:
        has_exclusion_table = "ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE" in sql_upper
        has_reason_not_in = (
            ("LOSSREASON_CODE" in sql_upper and "NOT IN" in sql_upper)
            or ("LOSSREASONNAME" in sql_upper and "NOT IN" in sql_upper)
            or has_exclusion_table
        )
        has_prefix_policy = "REGEXP_LIKE" in sql_upper and ("^[0-9]{3}_" in sql_upper or "^(XXX|ZZZ)_" in sql_upper)
        has_material_filter = (
            ("SCRAP_OBJECTTYPE" in sql_upper and "MATERIAL" in sql_upper)
            or ("OBJECTTYPE" in sql_upper and "MATERIAL" in sql_upper)
        )
        if not (has_reason_not_in and has_prefix_policy and has_material_filter):
            issues.append(
                "使用 LOTREJECTHISTORY 計算良率/不良率時，需套用報表口徑的 Reject 排除規則"
                "（MATERIAL 報廢、排除清單原因、以及原因碼前綴規則）。目前 SQL 未完整套用。"
            )

    return issues


# ---------------------------------------------------------------------------
# SQL sanitizer — deterministic fixes for known Oracle issues
# ---------------------------------------------------------------------------

# Only these statement types are allowed through the AI pipeline.
_ALLOWED_SQL_STARTS = frozenset({"SELECT", "WITH"})


def _assert_select_only(sql: str) -> None:
    """Raise ValueError if the first SQL keyword is not SELECT or WITH.

    Strips leading whitespace and -- / /* */ comments before checking so that
    a comment-prefixed DROP TABLE cannot bypass the guard.
    """
    text = sql.lstrip()
    while text:
        if text[:2] == "--":
            end = text.find("\n")
            text = text[end + 1 :].lstrip() if end != -1 else ""
        elif text[:2] == "/*":
            end = text.find("*/")
            text = text[end + 2 :].lstrip() if end != -1 else ""
        else:
            break
    m = re.match(r"\w+", text)
    first_kw = m.group(0).upper() if m else ""
    if first_kw not in _ALLOWED_SQL_STARTS:
        raise ValueError(
            f"只允許 SELECT 查詢，拒絕執行 '{first_kw or text[:20]}' 語句"
        )


# Mixed-case columns that Oracle requires double-quoting.
_MIXED_CASE_COLUMNS: dict[str, str] = {
    "Package": '"Package"',
    "Function": '"Function"',
}

# Valid column names per table (lazy-loaded from table_schema_info.json).
_VALID_COLUMNS: dict[str, set[str]] | None = None


def _load_valid_columns() -> dict[str, set[str]]:
    """Load valid column names from table_schema_info.json (cached)."""
    global _VALID_COLUMNS
    if _VALID_COLUMNS is not None:
        return _VALID_COLUMNS

    import pathlib
    schema_path = pathlib.Path(__file__).resolve().parents[3] / "data" / "table_schema_info.json"
    try:
        raw = json.loads(schema_path.read_text(encoding="utf-8"))
        _VALID_COLUMNS = {}
        for short_name, info in raw.items():
            full_name = f"DWH.{short_name}"
            cols = set(info.get("column_comments", {}).keys())
            # Also add upper-case versions for case-insensitive matching
            cols |= {c.upper() for c in cols}
            _VALID_COLUMNS[full_name] = cols
    except Exception as exc:
        logger.warning("Failed to load table_schema_info.json: %s", exc)
        _VALID_COLUMNS = {}
    return _VALID_COLUMNS


def _sanitize_sql(sql: str) -> str:
    """Apply deterministic fixes to LLM-generated SQL before execution.

    Fixes:
      0. Statement type guard — only SELECT/WITH allowed (raises ValueError otherwise)
      1. Mixed-case columns (Package, Function) → auto-quote
      2. Unquoted Oracle reserved words used as aliases
      3. Validate column names against schema (log warnings)
    """
    # 0. Reject non-SELECT statements before any other processing.
    _assert_select_only(sql)

    # 1. Auto-quote mixed-case columns.
    #    Match word boundary around the column name, but skip if already quoted.
    for col, quoted in _MIXED_CASE_COLUMNS.items():
        # Match: e.Package or just Package (not already inside quotes)
        # Replace with: e."Package" or "Package"
        sql = re.sub(
            rf'(?<!")(?<!\w){re.escape(col)}(?!")(?!\w)',
            quoted,
            sql,
        )

    # 2. Validate column names — extract table.column references and check.
    #    This is best-effort; we log warnings but don't block execution.
    valid_cols = _load_valid_columns()
    if valid_cols:
        # Find FROM/JOIN table references: DWH.TABLE_NAME [alias]
        table_aliases: dict[str, str] = {}  # alias -> full_table_name
        for m in re.finditer(
            r"(DWH\.\w+)\s+(\w+)", sql, re.IGNORECASE
        ):
            full_name = m.group(1).upper()
            alias = m.group(2).upper()
            if alias not in ("ON", "WHERE", "GROUP", "ORDER", "FETCH", "SET", "AND", "OR", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS"):
                table_aliases[alias] = full_name

        # Find alias.COLUMN references
        for m in re.finditer(r"(\w+)\.(\w+)", sql):
            alias = m.group(1).upper()
            col_name = m.group(2)
            if alias == "DWH":
                continue  # This is DWH.TABLE_NAME, not alias.column
            full_table = table_aliases.get(alias)
            if full_table and full_table in valid_cols:
                col_upper = col_name.upper()
                if col_upper not in valid_cols[full_table] and col_name not in valid_cols[full_table]:
                    logger.warning(
                        "Column '%s' not found in %s (alias %s). Valid columns: check table_schema_info.json",
                        col_name, full_table, alias,
                    )

    return sql


def _extract_oracle_error(exc: Exception) -> str:
    """Extract ORA-xxxxx error code and message from an exception.

    Returns a concise string like "ORA-00904: invalid identifier" or the
    full str(exc) if no ORA- pattern is found.
    """
    msg = str(exc)
    match = re.search(r"ORA-\d+[^\n]*", msg)
    if match:
        return match.group(0).strip()
    return msg[:300]


def _summarize_dataframe(df: "pd.DataFrame", max_chars: int = 20000) -> str:
    """Truncate a DataFrame to a LLM-digestible text format.

    Shows first 50 rows for large DataFrames; always stays within max_chars.
    """
    if df is None or df.empty:
        return "（查詢結果為空）"

    total = len(df)
    if total > 50:
        subset = df.head(50)
        text = f"共 {total} 筆，顯示前 50 筆：\n{subset.to_string(index=False)}"
    else:
        text = df.to_string(index=False)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(截斷)"
    return text


# ---------------------------------------------------------------------------
# Text-to-SQL pipeline
# ---------------------------------------------------------------------------

def process_query_text2sql(question: str) -> dict[str, Any]:
    """3-stage Text-to-SQL pipeline: classify → generate SQL → execute → summarize.

    Returns:
        dict with keys: answer, chart_data, query_used, params_used,
                        sql_used, tool_trace, suggestions
    """
    from mes_dashboard.core.database import read_sql_df

    tool_trace: list[dict[str, Any]] = []

    # ── Stage 1: Domain classification ─────────────────────────────────────
    s1_messages = [
        {"role": "system", "content": build_stage1_prompt()},
        {"role": "user", "content": question},
    ]
    try:
        s1_result = _call_llm(s1_messages)
    except requests.Timeout as exc:
        raise TimeoutError("LLM API 回應逾時") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("LLM API 連線失敗") from exc
    except RuntimeError as exc:
        raise ConnectionError(str(exc)) from exc

    domains: list[str] = s1_result.get("domains") or []
    thought: str = s1_result.get("thought", "")
    logger.info("Stage 1 result: domains=%s, thought=%s", domains, thought)
    tool_trace.append({"step": 1, "function": "stage1_classify", "summary": f"domains={domains}"})

    # No matching domain → return thought as answer
    if not domains:
        return {
            "answer": thought or "抱歉，我無法判斷這個問題屬於哪個資料領域，請換個方式描述",
            "chart_data": None,
            "query_used": "text2sql",
            "params_used": {},
            "sql_used": None,
            "tool_trace": tool_trace,
            "suggestions": [],
        }

    # ── Stage 2: SQL generation + retry loop ────────────────────────────────
    s2_system = build_stage2_prompt(domains)
    s2_messages: list[dict[str, Any]] = [
        {"role": "system", "content": s2_system},
        {"role": "user", "content": question},
    ]

    MAX_RETRIES = 5
    last_error: str = ""
    df: "pd.DataFrame | None" = None
    sql_used: str | None = None
    params_used: dict = {}

    for attempt in range(MAX_RETRIES):
        try:
            s2_result = _call_llm(s2_messages)
        except requests.Timeout as exc:
            raise TimeoutError("LLM API 回應逾時") from exc
        except requests.ConnectionError as exc:
            raise ConnectionError("LLM API 連線失敗") from exc
        except RuntimeError as exc:
            raise ConnectionError(str(exc)) from exc

        sql: str | None = s2_result.get("sql")
        params: dict = s2_result.get("params") or {}
        explanation: str = s2_result.get("explanation", "")
        logger.info("Stage 2 attempt %d: sql_len=%s, explanation=%s\nSQL: %s\nParams: %s",
                    attempt + 1, len(sql) if sql else 0, explanation, sql, params)

        if not sql:
            tool_trace.append({
                "step": 2 + attempt,
                "function": "stage2_generate_sql",
                "summary": f"LLM 無法生成 SQL: {explanation}",
            })
            return {
                "answer": explanation or "抱歉，無法生成對應的 SQL 查詢",
                "chart_data": None,
                "query_used": "text2sql",
                "params_used": {},
                "sql_used": None,
                "tool_trace": tool_trace,
                "suggestions": [],
            }

        sql_used = sql
        params_used = params
        tool_trace.append({
            "step": 2 + attempt,
            "function": "stage2_generate_sql",
            "summary": f"生成 SQL (attempt {attempt + 1}): {sql[:80]}...",
        })

        # ── Reviewer: check SQL logic before execution ───────────────────────
        review_issue = _review_sql(question, sql, params, domains)
        if review_issue:
            logger.info("Reviewer flagged issue: %s", review_issue)
            tool_trace.append({
                "step": 2 + attempt,
                "function": "reviewer",
                "summary": f"審查不通過: {review_issue[:80]}",
            })
            # Feed reviewer issues back to Stage 2 for correction (don't execute)
            if attempt < MAX_RETRIES - 1:
                s2_messages.append({"role": "assistant", "content": json.dumps(s2_result, ensure_ascii=False)})
                s2_messages.append({
                    "role": "user",
                    "content": (
                        f"SQL 審查發現以下業務邏輯問題：\n{review_issue}\n\n"
                        f"請根據上述問題修正 SQL，重新生成。"
                    ),
                })
                continue  # Skip execution, go to next attempt
            # Reviewer rejected on every attempt — abort without executing.
            return {
                "answer": f"SQL 審查未通過（已重試 {MAX_RETRIES} 次）：{review_issue}",
                "chart_data": None,
                "query_used": "text2sql",
                "params_used": params_used,
                "sql_used": sql_used,
                "tool_trace": tool_trace,
                "suggestions": [],
            }

        # ── Execute SQL ──────────────────────────────────────────────────────
        params = _coerce_date_params(params)
        try:
            sql = _sanitize_sql(sql)  # raises ValueError for non-SELECT
            df = read_sql_df(sql, params)
            logger.info("SQL executed successfully: %d rows", len(df) if df is not None else 0)
            tool_trace.append({
                "step": 3 + attempt,
                "function": "execute_sql",
                "summary": f"執行成功，回傳 {len(df) if df is not None else 0} 筆",
            })
            break  # Success — exit retry loop
        except ValueError as san_exc:
            last_error = str(san_exc)
            logger.warning("SQL rejected by security policy (attempt %d): %s", attempt + 1, last_error)
            tool_trace.append({
                "step": 3 + attempt,
                "function": "sanitize_sql",
                "summary": f"安全性拒絕: {last_error[:80]}",
            })
            if attempt < MAX_RETRIES - 1:
                s2_messages.append({"role": "assistant", "content": json.dumps(s2_result, ensure_ascii=False)})
                s2_messages.append({
                    "role": "user",
                    "content": f"SQL 安全規則不允許：{last_error}\n請只生成 SELECT 查詢，重新生成。",
                })
            df = None
        except Exception as exc:
            from mes_dashboard.core.database import DatabaseDegradedError
            last_error = _extract_oracle_error(exc)
            logger.warning("SQL execution failed (attempt %d): %s", attempt + 1, last_error)
            tool_trace.append({
                "step": 3 + attempt,
                "function": "execute_sql",
                "summary": f"執行失敗 (attempt {attempt + 1})",
                "error": last_error,
            })
            # Timeout / pool-exhaustion / circuit-breaker → no point retrying
            if isinstance(exc, (DatabaseDegradedError, TimeoutError)):
                return {
                    "answer": f"資料庫連線異常，無法執行查詢：{last_error}",
                    "chart_data": None,
                    "query_used": "text2sql",
                    "params_used": params_used,
                    "sql_used": sql_used,
                    "tool_trace": tool_trace,
                    "suggestions": [],
                }
            if attempt < MAX_RETRIES - 1:
                # Feed error back to LLM for correction
                s2_messages.append({"role": "assistant", "content": json.dumps(s2_result, ensure_ascii=False)})
                s2_messages.append({
                    "role": "user",
                    "content": f"上面的 SQL 執行時發生錯誤：{last_error}\n請修正 SQL 並重新生成。",
                })
            df = None
    else:
        # All retries exhausted
        return {
            "answer": f"SQL 執行失敗（已重試 {MAX_RETRIES} 次）：{last_error}",
            "chart_data": None,
            "query_used": "text2sql",
            "params_used": params_used,
            "sql_used": sql_used,
            "tool_trace": tool_trace,
            "suggestions": [],
        }

    # ── Empty result ────────────────────────────────────────────────────────
    if df is None or df.empty:
        return {
            "answer": "查詢完成，無符合條件的資料。",
            "chart_data": None,
            "query_used": "text2sql",
            "params_used": params_used,
            "sql_used": sql_used,
            "tool_trace": tool_trace,
            "suggestions": [],
        }

    # ── Stage 3: Summarize results ──────────────────────────────────────────
    truncated = _summarize_dataframe(df)
    r3_user_content = f"{question}\n\n## 查詢結果\n{truncated}"
    r3_messages = [
        {"role": "system", "content": build_round3_prompt()},
        {"role": "user", "content": r3_user_content},
    ]
    try:
        answer = call_llm_text(r3_messages)
        if not answer:
            answer = "查詢完成，請參考資料。"
    except Exception:
        logger.warning("Stage 3 summarization failed, using fallback")
        answer = "查詢完成，請參考資料。"

    tool_trace.append({
        "step": len(tool_trace) + 1,
        "function": "stage3_summarize",
        "summary": "LLM 摘要完成",
    })

    # Convert DataFrame to list-of-dicts for chart_data
    # Replace NaN/NaT with None so JSON serialization produces null (not NaN)
    chart_data: list[dict] | None = df.where(df.notna(), other=None).to_dict(orient="records")
    if not chart_data:
        chart_data = None

    return {
        "answer": answer,
        "chart_data": chart_data,
        "query_used": "text2sql",
        "params_used": params_used,
        "sql_used": sql_used,
        "tool_trace": tool_trace,
        "suggestions": [],
    }


# ---------------------------------------------------------------------------
# Main entry point — three-round pipeline (function call mode)
# ---------------------------------------------------------------------------

def process_query_function(question: str) -> dict[str, Any]:
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
        r1_result = _call_llm(r1_messages)
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
        r2_result = _call_llm(r2_messages)
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
    chart_data = normalize_chart_data(function_name, chart_data)
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
        truncated_result = summarize_for_llm(function_name, chart_data)
        r3_user_content = f"{question}\n\n## 查詢結果（{function_name}）\n{truncated_result}"
        r3_messages = [
            {"role": "system", "content": build_round3_prompt()},
            {"role": "user", "content": r3_user_content},
        ]

        try:
            answer = call_llm_text(r3_messages)
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


# ---------------------------------------------------------------------------
# Dispatcher — feature flag selects pipeline
# ---------------------------------------------------------------------------

def process_query(question: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Route to clarification/text2sql/function/agent pipeline based on AI_MODE.

    AI_MODE=text2sql (default) → process_query_text2sql()
    AI_MODE=function            → process_query_function()
    AI_MODE=agent               → process_agent_turn()
    """
    state = advance_query_state(
        conversation_id=conversation_id,
        user_input=question,
        llm_caller=_call_llm,
    )

    if not state.get("ready_to_search"):
        return {
            "answer": state.get("answer") or "請補充查詢條件。",
            "chart_data": None,
            "query_used": None,
            "params_used": None,
            "suggestions": state.get("suggestions") or [],
            "needs_clarification": True,
            "missing_slots": state.get("missing_slots") or [],
            "query_state": state.get("query_state") or {},
        }

    search_question = state.get("search_question") or question
    mode = os.getenv("AI_MODE", "text2sql").strip().lower()
    if mode == "agent":
        from mes_dashboard.services.ai_agent_loop import process_agent_turn
        result = process_agent_turn(search_question)
        result.setdefault("needs_clarification", False)
        result.setdefault("missing_slots", [])
        result.setdefault("query_state", state.get("query_state") or {})
        return result
    if mode == "function":
        result = process_query_function(search_question)
        result.setdefault("needs_clarification", False)
        result.setdefault("missing_slots", [])
        result.setdefault("query_state", state.get("query_state") or {})
        return result
    result = process_query_text2sql(search_question)
    result.setdefault("needs_clarification", False)
    result.setdefault("missing_slots", [])
    result.setdefault("query_state", state.get("query_state") or {})
    return result

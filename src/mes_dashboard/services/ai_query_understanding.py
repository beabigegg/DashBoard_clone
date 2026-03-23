# -*- coding: utf-8 -*-
"""AI query understanding + slot-filling session state.

This module keeps only a compact in-memory clarification state per
conversation_id. It does NOT persist full chat history.

Workflow:
1. Extract/merge structured slots from initial question + latest user input.
2. Determine whether required slots are complete.
3. If incomplete, ask one clarification question and store compact slot state.
4. If complete, build an enriched search question and clear the session.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from copy import deepcopy
from typing import Any, Callable

logger = logging.getLogger("mes_dashboard.ai_query_understanding")

_SESSION_TTL_SECONDS = int(os.getenv("AI_QUERY_SESSION_TTL_SECONDS", "1800"))

_SESSION_LOCK = threading.RLock()
_SESSION_STORE: dict[str, dict[str, Any]] = {}

_VALID_TOPICS = {
    "wip_realtime",
    "hold",
    "reject",
    "equipment",
    "yield",
    "material",
    "lot_history",
    "genealogy",
    "job",
}

_VALID_INTENTS = {
    "summary",
    "detail",
    "trend",
    "ranking",
    "comparison",
    "trace",
    "status",
    "analysis",
    "unknown",
}

_VALID_TARGET_TYPES = {
    "equipment",
    "lot",
    "workorder",
    "workcenter",
    "product",
    "hold_reason",
    "material",
    "unknown",
}

_VALID_TIME_SCOPES = {
    "current",
    "today",
    "last_7_days",
    "last_30_days",
    "custom_range",
    "history",
    "unspecified",
}

_WORKCENTER_KEYWORDS = {
    "DB": "焊接_DB",
    "WB": "焊接_WB",
    "DW": "焊接_DW",
    "成型": "成型",
    "MOLD": "成型",
    "TMTT": "TMTT",
    "測試": "TMTT",
    "品檢": "品檢",
    "FVI": "品檢",
    "FQC": "FQC",
    "切割": "切割",
    "電鍍": "電鍍",
    "吹砂": "水吹砂",
}

_WORKCENTER_TOKEN_PATTERNS = {
    "DB": re.compile(r"(?<![A-Z0-9])DB(?![A-Z0-9])"),
    "WB": re.compile(r"(?<![A-Z0-9])WB(?![A-Z0-9])"),
    "DW": re.compile(r"(?<![A-Z0-9])DW(?![A-Z0-9])"),
    "MOLD": re.compile(r"(?<![A-Z0-9])MOLD(?![A-Z0-9])"),
    "TMTT": re.compile(r"(?<![A-Z0-9])TMTT(?![A-Z0-9])"),
    "FVI": re.compile(r"(?<![A-Z0-9])FVI(?![A-Z0-9])"),
    "FQC": re.compile(r"(?<![A-Z0-9])FQC(?![A-Z0-9])"),
}

_TIME_SCOPE_LABELS = {
    "current": "目前",
    "today": "今天",
    "last_7_days": "近 7 天",
    "last_30_days": "近 30 天",
    "custom_range": "指定日期區間",
    "history": "歷史",
    "unspecified": "未指定",
}


def reset_query_sessions_for_tests() -> None:
    """Clear in-memory sessions. Test-only helper."""
    with _SESSION_LOCK:
        _SESSION_STORE.clear()


def get_query_session_for_tests(conversation_id: str) -> dict[str, Any] | None:
    """Return a copy of a stored session. Test-only helper."""
    with _SESSION_LOCK:
        value = _SESSION_STORE.get(conversation_id)
        return deepcopy(value) if value is not None else None


def advance_query_state(
    conversation_id: str | None,
    user_input: str,
    llm_caller: Callable[[list[dict[str, Any]]], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Advance slot-filling state for one user turn.

    If conversation_id is missing, we bypass clarification state and let the
    existing single-turn pipeline handle the query as-is.
    """
    cleaned_input = (user_input or "").strip()
    if not cleaned_input:
        return {
            "ready_to_search": False,
            "needs_clarification": True,
            "answer": "請先輸入查詢問題。",
            "suggestions": [],
            "missing_slots": ["question"],
            "query_state": {},
        }

    if not conversation_id:
        return {
            "ready_to_search": True,
            "needs_clarification": False,
            "search_question": cleaned_input,
            "query_state": {},
        }

    _cleanup_expired_sessions()
    now = time.time()

    with _SESSION_LOCK:
        state = deepcopy(_SESSION_STORE.get(conversation_id) or {})

    initial_question = (state.get("initial_question") or cleaned_input).strip()
    current_slots = state.get("slots") or {}

    extracted = _extract_query_state(
        initial_question=initial_question,
        latest_input=cleaned_input,
        current_slots=current_slots,
        llm_caller=llm_caller,
    )

    if extracted.get("should_reset_context") and current_slots:
        logger.info("Resetting AI query slot state for conversation_id=%s", conversation_id)
        initial_question = cleaned_input
        current_slots = {}
        extracted = _extract_query_state(
            initial_question=initial_question,
            latest_input=cleaned_input,
            current_slots=current_slots,
            llm_caller=llm_caller,
        )

    merged_slots = _merge_slots(current_slots, extracted.get("slots") or {})
    completion = _compute_completion(merged_slots)
    missing_slots = completion["missing_slots"]

    if missing_slots:
        answer = extracted.get("clarification_question") or _build_default_clarification(
            merged_slots,
            missing_slots,
        )
        suggestions = _normalize_suggestions(extracted.get("suggestions"))
        if not suggestions:
            suggestions = _default_suggestions(merged_slots, missing_slots)

        stored = {
            "initial_question": initial_question,
            "slots": merged_slots,
            "updated_at": now,
        }
        with _SESSION_LOCK:
            _SESSION_STORE[conversation_id] = stored

        return {
            "ready_to_search": False,
            "needs_clarification": True,
            "answer": answer,
            "suggestions": suggestions,
            "missing_slots": missing_slots,
            "query_state": deepcopy(merged_slots),
        }

    with _SESSION_LOCK:
        _SESSION_STORE.pop(conversation_id, None)

    return {
        "ready_to_search": True,
        "needs_clarification": False,
        "search_question": _build_search_question(initial_question, merged_slots),
        "query_state": deepcopy(merged_slots),
    }


def _cleanup_expired_sessions() -> None:
    now = time.time()
    with _SESSION_LOCK:
        expired = [
            cid
            for cid, state in _SESSION_STORE.items()
            if (now - float(state.get("updated_at") or 0.0)) > _SESSION_TTL_SECONDS
        ]
        for cid in expired:
            _SESSION_STORE.pop(cid, None)


def _extract_query_state(
    initial_question: str,
    latest_input: str,
    current_slots: dict[str, Any],
    llm_caller: Callable[[list[dict[str, Any]]], dict[str, Any]] | None,
) -> dict[str, Any]:
    slots = _rule_based_extract(initial_question, latest_input, current_slots)
    llm_result: dict[str, Any] = {}

    if llm_caller is not None:
        messages = _build_understanding_messages(initial_question, latest_input, current_slots)
        try:
            raw = llm_caller(messages)
            if isinstance(raw, dict):
                llm_result = _normalize_understanding_result(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI query understanding failed, fallback to rule-based extraction: %s", exc)

    llm_slots = llm_result.get("slots") or {}
    merged_slots = _merge_slots(slots, llm_slots)

    return {
        "slots": merged_slots,
        "clarification_question": llm_result.get("clarification_question") or "",
        "suggestions": llm_result.get("suggestions") or [],
        "should_reset_context": bool(llm_result.get("should_reset_context")),
    }


def _build_understanding_messages(
    initial_question: str,
    latest_input: str,
    current_slots: dict[str, Any],
) -> list[dict[str, str]]:
    system_prompt = "\n".join([
        "你是 MES Dashboard 的查詢條件抽取器。",
        "目標：根據初始問題、目前已補齊條件、以及最新使用者補充，輸出結構化 JSON。",
        "不要搜尋資料，不要生成 SQL。",
        "",
        "允許的 topic：wip_realtime, hold, reject, equipment, yield, material, lot_history, genealogy, job",
        "允許的 intent：summary, detail, trend, ranking, comparison, trace, status, analysis, unknown",
        "允許的 target_type：equipment, lot, workorder, workcenter, product, hold_reason, material, unknown",
        "允許的 time_scope：current, today, last_7_days, last_30_days, custom_range, history, unspecified",
        "",
        "回覆格式（嚴格 JSON，禁止其他文字）：",
        '{',
        '  "topic": "... 或 null",',
        '  "intent": "... 或 null",',
        '  "target_type": "... 或 null",',
        '  "target_value": "... 或 null",',
        '  "time_scope": "... 或 null",',
        '  "metric": "... 或 null",',
        '  "scope": "... 或 null",',
        '  "group_by": "... 或 null",',
        '  "filters": {},',
        '  "should_reset_context": false,',
        '  "clarification_question": "若缺條件時的單一追問，否則空字串",',
        '  "suggestions": ["最多 4 個建議"]',
        '}',
    ])
    user_prompt = "\n".join([
        f"初始問題：{initial_question}",
        f"目前已補齊條件：{current_slots}",
        f"最新補充：{latest_input}",
    ])
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _normalize_understanding_result(raw: dict[str, Any]) -> dict[str, Any]:
    slots = {
        "topic": _normalize_choice(raw.get("topic"), _VALID_TOPICS),
        "intent": _normalize_choice(raw.get("intent"), _VALID_INTENTS),
        "target_type": _normalize_choice(raw.get("target_type"), _VALID_TARGET_TYPES),
        "target_value": _clean_text(raw.get("target_value")),
        "time_scope": _normalize_choice(raw.get("time_scope"), _VALID_TIME_SCOPES),
        "metric": _clean_text(raw.get("metric")),
        "scope": _clean_text(raw.get("scope")),
        "group_by": _clean_text(raw.get("group_by")),
        "filters": raw.get("filters") if isinstance(raw.get("filters"), dict) else {},
    }
    return {
        "slots": slots,
        "clarification_question": _clean_text(raw.get("clarification_question")) or "",
        "suggestions": _normalize_suggestions(raw.get("suggestions")),
        "should_reset_context": bool(raw.get("should_reset_context")),
    }


def _rule_based_extract(
    initial_question: str,
    latest_input: str,
    current_slots: dict[str, Any],
) -> dict[str, Any]:
    text = f"{initial_question} {latest_input}".strip()
    slots = {
        "topic": None,
        "intent": None,
        "target_type": None,
        "target_value": None,
        "time_scope": None,
        "metric": None,
        "scope": None,
        "group_by": None,
        "filters": {},
    }

    upper_text = text.upper()

    lot_match = re.search(r"\b([A-Z]{2}\d{6,}-[A-Z]\d{2}-\d{3})\b", upper_text)
    if lot_match:
        slots["target_type"] = "lot"
        slots["target_value"] = lot_match.group(1)

    workorder_match = re.search(r"\b(G[AC]\d{6,})\b", upper_text)
    if workorder_match and slots["target_type"] != "lot":
        slots["target_type"] = "workorder"
        slots["target_value"] = workorder_match.group(1)

    equipment_match = re.search(r"\b([A-Z]{2,6}-\d{3,4})\b", upper_text)
    if equipment_match:
        slots["target_type"] = "equipment"
        slots["target_value"] = equipment_match.group(1)

    for key, value in _WORKCENTER_KEYWORDS.items():
        if key in _WORKCENTER_TOKEN_PATTERNS:
            matched = bool(_WORKCENTER_TOKEN_PATTERNS[key].search(upper_text))
        else:
            matched = key in text
        if matched:
            slots["scope"] = value
            if slots["target_type"] is None:
                slots["target_type"] = "workcenter"
                slots["target_value"] = value
            break

    if any(token in text for token in ["目前", "現在", "即時"]):
        slots["time_scope"] = "current"
    elif "今天" in text or "今日" in text:
        slots["time_scope"] = "today"
    elif re.search(r"近\s*7\s*天", text):
        slots["time_scope"] = "last_7_days"
    elif re.search(r"近\s*30\s*天", text):
        slots["time_scope"] = "last_30_days"
    elif any(token in text for token in ["歷史", "趨勢", "最近"]):
        slots["time_scope"] = "history"

    if any(token in text for token in ["趨勢", "trend"]):
        slots["intent"] = "trend"
    elif any(token in text for token in ["排行", "排名", "最多", "最差", "top"]):
        slots["intent"] = "ranking"
    elif any(token in text for token in ["比較", "差異"]):
        slots["intent"] = "comparison"
    elif any(token in text for token in ["歷程", "追溯", "trace"]):
        slots["intent"] = "trace"
    elif any(token in text for token in ["明細", "哪些", "哪幾筆", "清單"]):
        slots["intent"] = "detail"
    elif any(token in text for token in ["狀態", "在跑什麼", "生產什麼"]):
        slots["intent"] = "status"
    elif any(token in text for token in ["摘要", "概況", "概覽"]):
        slots["intent"] = "summary"

    if any(token in text for token in ["不良", "reject", "報廢", "scrap"]):
        slots["topic"] = "reject"
        slots["metric"] = "不良率" if "率" in text else "不良數"
    elif any(token in text for token in ["良率", "yield"]):
        slots["topic"] = "yield"
        slots["metric"] = "良率"
    elif any(token in text for token in ["hold", "HOLD", "鎖批", "解Hold", "暫停"]):
        if slots["time_scope"] == "current":
            slots["topic"] = "wip_realtime"
        else:
            slots["topic"] = "hold"
        slots["metric"] = "Hold 數量"
    elif any(token in text for token in ["稼動", "OU", "機台", "設備"]):
        slots["topic"] = "equipment"
        slots["metric"] = "稼動率" if any(token in text for token in ["稼動", "OU"]) else "設備狀態"
    elif any(token in text for token in ["在製", "WIP"]):
        slots["topic"] = "wip_realtime"
        slots["metric"] = "在製數"
    elif any(token in text for token in ["材料", "線材", "耗材"]):
        slots["topic"] = "material"
        slots["intent"] = slots["intent"] or "detail"
    elif any(token in text for token in ["維修", "job", "故障", "保養"]):
        slots["topic"] = "job"
    elif any(token in text for token in ["歷程", "trackin", "trackout"]) and slots["topic"] is None:
        slots["topic"] = "lot_history"

    if slots["intent"] is None and any(token in text for token in ["狀況", "情況"]):
        slots["intent"] = "unknown"

    if slots["topic"] is None and current_slots:
        slots["topic"] = current_slots.get("topic")
    if slots["intent"] is None and current_slots:
        slots["intent"] = current_slots.get("intent")

    return slots


def _merge_slots(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base or {})
    for key, value in (incoming or {}).items():
        if key == "filters":
            filters = merged.get("filters") or {}
            if isinstance(value, dict):
                for fk, fv in value.items():
                    if fv not in (None, "", [], {}):
                        filters[fk] = fv
            merged["filters"] = filters
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    if "filters" not in merged:
        merged["filters"] = {}
    return merged


def _compute_completion(slots: dict[str, Any]) -> dict[str, Any]:
    topic = slots.get("topic")
    intent = slots.get("intent")
    target_value = slots.get("target_value")
    scope = slots.get("scope")
    time_scope = slots.get("time_scope")

    missing: list[str] = []

    if not topic:
        missing.append("topic")

    if not intent or intent == "unknown":
        if topic in {"reject", "hold", "yield", "equipment", "wip_realtime"}:
            missing.append("intent")

    if topic in {"equipment", "job", "material", "lot_history", "genealogy"} and intent in {"detail", "trace", "status"}:
        if not target_value and not scope:
            missing.append("target")

    if topic in {"reject", "hold", "yield", "job", "material", "lot_history", "genealogy"}:
        if intent in {"trend", "ranking", "comparison", "analysis"} and not time_scope:
            missing.append("time_scope")
        elif intent in {"detail", "trace"} and not time_scope and not target_value:
            missing.append("time_scope")

    if topic == "equipment" and intent in {"trend", "ranking", "comparison", "analysis"} and not time_scope:
        missing.append("time_scope")

    seen: set[str] = set()
    ordered_missing = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            ordered_missing.append(item)

    return {
        "missing_slots": ordered_missing,
        "is_complete": len(ordered_missing) == 0,
    }


def _build_default_clarification(slots: dict[str, Any], missing_slots: list[str]) -> str:
    first = missing_slots[0] if missing_slots else ""
    if first == "topic":
        return "請問您想查的是哪一類資訊？例如：在製 / Hold / 不良 / 設備 / 良率。"
    if first == "intent":
        topic_label = _topic_label(slots.get("topic"))
        return f"請問您想看 {topic_label} 的摘要、明細、趨勢，還是排行？"
    if first == "target":
        topic_label = _topic_label(slots.get("topic"))
        return f"請問您要查哪個對象的 {topic_label}？例如機台、工單、批次或站別。"
    if first == "time_scope":
        return "請問您要看目前、今天、近 7 天，還是近 30 天的資料？"
    return "請再補充查詢條件，我才能為您定位正確資料。"


def _default_suggestions(slots: dict[str, Any], missing_slots: list[str]) -> list[str]:
    first = missing_slots[0] if missing_slots else ""
    if first == "topic":
        return ["在製", "Hold", "不良", "設備", "良率"]
    if first == "intent":
        return ["摘要", "明細", "趨勢", "排行"]
    if first == "time_scope":
        return ["目前", "今天", "近 7 天", "近 30 天"]
    if first == "target" and slots.get("topic") == "equipment":
        return ["某台機台", "某個站別", "全廠摘要"]
    if first == "target" and slots.get("topic") == "reject":
        return ["某個站別", "某張工單", "某個 lot"]
    return []


def _build_search_question(initial_question: str, slots: dict[str, Any]) -> str:
    lines = [
        f"原始問題：{initial_question}",
        "已確認查詢條件：",
    ]

    topic = slots.get("topic")
    intent = slots.get("intent")
    target_type = slots.get("target_type")
    target_value = slots.get("target_value")
    time_scope = slots.get("time_scope")
    metric = slots.get("metric")
    scope = slots.get("scope")
    group_by = slots.get("group_by")

    if topic:
        lines.append(f"- 主題：{_topic_label(topic)}")
    if intent:
        lines.append(f"- 查詢形式：{_intent_label(intent)}")
    if target_type or target_value:
        label = _target_type_label(target_type)
        lines.append(f"- 查詢對象：{label}{' = ' + str(target_value) if target_value else ''}")
    if scope:
        lines.append(f"- 範圍：{scope}")
    if time_scope:
        lines.append(f"- 時間範圍：{_TIME_SCOPE_LABELS.get(time_scope, time_scope)}")
    if metric:
        lines.append(f"- 指標：{metric}")
    if group_by:
        lines.append(f"- 分組方式：{group_by}")
    filters = slots.get("filters") or {}
    for key, value in filters.items():
        lines.append(f"- 篩選 {key}：{value}")

    lines.append("請直接根據以上已確認條件進行查詢與回答，不要再要求補充這些已確認的資訊。")
    return "\n".join(lines)


def _normalize_choice(value: Any, allowed: set[str]) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return cleaned if cleaned in allowed else None


def _normalize_suggestions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        cleaned = _clean_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:4]


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _topic_label(topic: str | None) -> str:
    labels = {
        "wip_realtime": "即時在製 / WIP",
        "hold": "Hold 歷史",
        "reject": "不良 / Reject",
        "equipment": "設備 / 稼動",
        "yield": "良率",
        "material": "材料",
        "lot_history": "批次歷程",
        "genealogy": "批次追溯",
        "job": "維修工單",
    }
    return labels.get(topic or "", topic or "查詢")


def _intent_label(intent: str | None) -> str:
    labels = {
        "summary": "摘要",
        "detail": "明細",
        "trend": "趨勢",
        "ranking": "排行",
        "comparison": "比較",
        "trace": "追溯",
        "status": "狀態",
        "analysis": "分析",
        "unknown": "未明確指定",
    }
    return labels.get(intent or "", intent or "未指定")


def _target_type_label(target_type: str | None) -> str:
    labels = {
        "equipment": "設備",
        "lot": "批次",
        "workorder": "工單",
        "workcenter": "站別",
        "product": "產品",
        "hold_reason": "Hold 原因",
        "material": "材料",
        "unknown": "對象",
    }
    return labels.get(target_type or "", "對象")
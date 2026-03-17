# -*- coding: utf-8 -*-
"""AI Function Registry — loads LLM-callable service functions from YAML.

Startup: loads ai_functions.yaml, expands $ENUM references, and exposes
REGISTRY as a module-level dict.  New functions require only a YAML edit
and service restart.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

import yaml

logger = logging.getLogger("mes_dashboard.ai_function_registry")

_YAML_PATH = os.path.join(os.path.dirname(__file__), "ai_functions.yaml")

# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _load_registry() -> dict[str, dict[str, Any]]:
    """Load ai_functions.yaml, expand $ENUM references, return registry dict."""
    try:
        with open(_YAML_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(
            f"Failed to load AI function registry from {_YAML_PATH}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise RuntimeError(f"ai_functions.yaml must be a mapping, got {type(raw)}")

    enums: dict[str, list] = raw.pop("_enums", {}) or {}

    registry: dict[str, dict[str, Any]] = {}
    for func_name, entry in raw.items():
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"ai_functions.yaml: entry '{func_name}' must be a mapping"
            )
        # Expand $ENUM references in params
        params = entry.get("params") or {}
        for param_name, pspec in params.items():
            if not isinstance(pspec, dict):
                raise RuntimeError(
                    f"ai_functions.yaml: param '{param_name}' in '{func_name}' must be a mapping"
                )
            enum_val = pspec.get("enum")
            if isinstance(enum_val, str) and enum_val.startswith("$"):
                enum_key = enum_val[1:]
                if enum_key not in enums:
                    raise RuntimeError(
                        f"ai_functions.yaml: unknown enum reference ${enum_key} "
                        f"in '{func_name}.{param_name}'"
                    )
                pspec["enum"] = enums[enum_key]
        registry[func_name] = entry

    return registry


REGISTRY: dict[str, dict[str, Any]] = _load_registry()

# Expose workcenter groups for prompt builders (read from any param that uses WORKCENTER_GROUPS)
_WORKCENTER_GROUPS: list[str] = []
for _entry in REGISTRY.values():
    for _pspec in (_entry.get("params") or {}).values():
        _enum = _pspec.get("enum")
        if isinstance(_enum, list) and "切割" in _enum:
            _WORKCENTER_GROUPS = _enum
            break
    if _WORKCENTER_GROUPS:
        break


# ---------------------------------------------------------------------------
# Prompt builders — three rounds
# ---------------------------------------------------------------------------

def build_round1_prompt() -> str:
    """Round 1: compact function list (name + description only, ~400-500 tokens)."""
    lines = [
        "你是 MES Dashboard AI 助手。使用者會用中文描述查詢需求。",
        "從下方函式目錄中選出最合適的函式名稱。",
        "",
        "## 嚴格規則",
        "- 你的回覆必須是且僅是一個 JSON 物件",
        "- 禁止輸出任何推理過程、解釋、markdown 或其他文字",
        "- 直接輸出 JSON，不要用 ```json 包裝",
        "",
        "## 回覆格式",
        '{"function": "<函式名稱>", "explanation": "<一句話說明>"}',
        "",
        "若無合適函式：",
        '{"function": null, "explanation": "<說明原因>"}',
        "",
        "## 函式目錄",
    ]
    for func_name, entry in REGISTRY.items():
        lines.append(f"- {func_name}：{entry['description']}")
    return "\n".join(lines)


def build_round2_prompt(function_name: str) -> str:
    """Round 2: single function full schema + date rules + workcenter list (~500 tokens)."""
    entry = REGISTRY.get(function_name)
    if entry is None:
        raise KeyError(f"Unknown function: {function_name}")

    lines = [
        f"你正在為函式 `{function_name}` 填入參數。",
        "",
        f"## 函式說明：{entry['description']}",
        "",
    ]

    params = entry.get("params") or {}

    # Only show date rules when the function actually has date params
    has_date_params = any(
        "date" in pname for pname in params
    )
    has_workcenter_params = any(
        pname in ("workcenter_group", "workcenter_groups") for pname in params
    )

    if params:
        param_names = list(params.keys())
        lines.append(f"## 可用參數（只允許以下 {len(params)} 個，禁止自行新增）")
        for param_name, pspec in params.items():
            required = "必填" if pspec.get("required") else "選填"
            desc = pspec.get("description", "")
            enum_vals = pspec.get("enum")
            default = pspec.get("default")
            enum_str = f"，可選值：{enum_vals}" if enum_vals else ""
            default_str = f"，預設：{default}" if default is not None else ""
            lines.append(
                f"  - {param_name} ({pspec['type']}, {required}){enum_str}{default_str}：{desc}"
            )
    else:
        param_names = []
        lines.append("## 此函式不需要任何參數")

    lines.append("")

    if has_date_params:
        lines.append("## 日期參數規則")
        lines.append("- 若使用者未指定日期，預設 start_date 為今天往前 7 天，end_date 為今天")
        lines.append("- 日期格式必須是 YYYY-MM-DD")
        lines.append("")

    if has_workcenter_params:
        lines.append("## 站別代碼 enum")
        lines.append("可用值：" + "、".join(_WORKCENTER_GROUPS))
        lines.append("")

    lines.append("## 回覆格式（只回覆此 JSON，不加其他文字）")
    lines.append("正常情況：")
    if params:
        lines.append('{"params": {<僅限上述參數鍵值對>}}')
    else:
        lines.append('{"params": {}}')
    lines.append("")
    lines.append("若使用者提供的資訊不足以填入必填參數，回覆：")
    lines.append('{"params": {<已知參數>}, "clarification": "<用中文詢問缺少的資訊>"}')
    lines.append("")
    lines.append("## 重要規則")
    lines.append(f"- params 內只能包含上述列出的參數名稱{'：' + '、'.join(param_names) if param_names else ''}")
    lines.append("- 絕對不要生成 SQL 或任何資料庫語法")
    lines.append("- 只回覆 JSON，不要加 markdown 包裝或其他說明文字")

    return "\n".join(lines)


def build_round3_prompt() -> str:
    """Round 3: fixed analysis instructions (~200 tokens)."""
    lines = [
        "你是 MES Dashboard AI 助手，負責用中文解讀查詢結果。",
        "",
        "## 回覆規則（必須嚴格遵守）",
        "- 直接回答使用者的問題，不要重述問題",
        "- 點出 2-3 個最關鍵的數據或發現",
        "- 回覆不超過 5 句話",
        "- 不要回覆 JSON、程式碼或 markdown 格式",
        "- 若資料為空或無異常，直接說明「目前無異常」或「查詢無結果」",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent Validation
# ---------------------------------------------------------------------------

def validate_intent(function_name: str, params: dict) -> tuple[bool, str]:
    """Validate that function_name exists and params conform to schema.

    Returns:
        (True, "") on success
        (False, reason_str) on failure
    """
    if function_name not in REGISTRY:
        available = ", ".join(REGISTRY.keys())
        return False, f"未知函式：{function_name}。可用函式：{available}"

    entry = REGISTRY[function_name]
    schema = entry.get("params") or {}

    for param_name, pspec in schema.items():
        if pspec.get("required") and param_name not in params:
            if "default" not in pspec:
                return False, f"缺少必填參數：{param_name}"

        if param_name in params:
            value = params[param_name]
            enum_vals = pspec.get("enum")
            if enum_vals is not None:
                if isinstance(value, list):
                    for v in value:
                        if v not in enum_vals:
                            return False, f"參數 {param_name} 的值 {v!r} 不在允許範圍內：{enum_vals}"
                elif value not in enum_vals:
                    return False, f"參數 {param_name} 的值 {value!r} 不在允許範圍內：{enum_vals}"

    return True, ""


# ---------------------------------------------------------------------------
# Service Function Loader
# ---------------------------------------------------------------------------

def get_service_function(function_name: str):
    """Dynamically import and return the service function for the given intent."""
    if function_name not in REGISTRY:
        raise KeyError(f"Unknown function: {function_name}")

    service_path = REGISTRY[function_name]["service"]
    module_path, func_name = service_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as exc:
        logger.error("Failed to load service function %s: %s", service_path, exc)
        raise


# ---------------------------------------------------------------------------
# Suggestion Builder
# ---------------------------------------------------------------------------

def get_suggestions(function_name: str) -> list[str]:
    """Generate follow-up suggestion texts from drill_down list."""
    if function_name not in REGISTRY:
        return []

    drill_down = REGISTRY[function_name].get("drill_down") or []
    suggestions = []

    _suggestion_labels = {
        # Dashboard
        "dashboard_kpi": "查看全廠設備 KPI",
        "ou_trend": "查看稼動率趨勢",
        "utilization_heatmap": "查看稼動率熱圖",
        # Reject
        "reject_summary": "查看不良率摘要",
        "reject_reason_pareto": "查看不良原因排行",
        "reject_dimension_pareto": "查看不良多維度排行",
        "reject_trend": "查看不良率趨勢",
        "reject_spike_alerts": "查看不良量突增警示",
        "reject_lot_list": "查看不良批次清單",
        # Yield
        "yield_summary": "查看良率摘要",
        "yield_trend": "查看良率趨勢",
        "yield_anomaly_alerts": "查看良率異常警示",
        "yield_anomaly_drilldown": "查看良率異常明細",
        # WIP
        "wip_summary": "查看在製品摘要",
        "wip_matrix": "查看站別在製矩陣",
        "wip_hold_summary": "查看 Hold 摘要",
        # Hold
        "hold_outlier_alerts": "查看 Hold 異常警示",
        "hold_history_trend": "查看 Hold 歷史趨勢",
        "hold_reason_pareto": "查看 Hold 原因排行",
        "hold_duration_distribution": "查看 Hold 時間分佈",
        "hold_lot_list": "查看 Hold 批次清單",
        # Equipment
        "equipment_deviation_alerts": "查看設備異常警示",
        "equipment_status_summary": "查看設備稼動率摘要",
        "workcenter_status_matrix": "查看站別設備狀態矩陣",
        "equipment_recent_jobs": "查看設備近期加工批次",
        "job_txn_history": "查看加工歷程",
        # Lot / Material / Trace
        "lot_query": "查詢批次詳情",
        "lot_production_history": "查看批次生產歷程",
        "lot_rejects": "查看批次不良紀錄",
        "lot_holds": "查看批次 Hold 紀錄",
        "lot_materials": "查看批次材料紀錄",
        "adjacent_lots": "查看前後批",
        "material_forward_trace": "材料正追溯",
        "material_reverse_trace": "材料反追溯",
        # Equipment History
        "resource_status_history": "查看設備狀態歷史",
        # Mid-Section Defect
        "mid_section_defect_analysis": "中段缺陷追溯分析",
        # Anomaly
        "anomaly_summary": "查看異常偵測總覽",
        # Yield
        "yield_alert_candidates": "查看良率風險清單",
        # WIP
        "wip_workcenter_detail": "查看站別在製明細",
        "hold_overview_treemap": "查看 Hold 分佈",
    }

    for fn in drill_down:
        label = _suggestion_labels.get(fn, f"查看 {fn}")
        suggestions.append(label)

    return suggestions

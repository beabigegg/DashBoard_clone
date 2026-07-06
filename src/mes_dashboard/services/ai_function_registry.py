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
# Prompt builders — text2sql two-stage
# ---------------------------------------------------------------------------

def build_stage1_prompt() -> str:
    """Stage 1 prompt: classify user question into MES domains.

    Injects MES domain knowledge (ID formats, station abbreviations, data source
    selection rules) so the LLM can narrow down which tables are relevant.
    """
    from mes_dashboard.services.ai_schema_context import TABLE_DOMAINS
    from mes_dashboard.services.ai_business_context import (
        get_stage1_business_context,
        get_stage1_domain_hints,
    )

    domain_lines = []
    for key, entry in TABLE_DOMAINS.items():
        domain_lines.append(f"  - {key}：{entry['description']}")

    lines = [
        "你是 MES 工廠資料系統的 SQL 分析助手。",
        "根據使用者問題，判斷需要查詢哪些資料領域，並以 JSON 回覆。",
        "",
        get_stage1_business_context(),
        "",
        get_stage1_domain_hints(),
        "",
        "## 可選領域清單",
    ] + domain_lines + [
        "",
        "## 回覆格式（嚴格 JSON，禁止其他文字）",
        '{"domains": ["領域1", "領域2"], "thought": "一句話說明選擇原因"}',
        "",
        "若問題無法對應任何領域：",
        '{"domains": [], "thought": "說明原因"}',
        "",
        "## 規則",
        "- domains 最多 3 個",
        "- 只能從上方清單選取",
        "- 直接輸出 JSON，不要加 markdown 包裝",
    ]
    return "\n".join(lines)


def build_stage2_prompt(domains: list[str]) -> str:
    """Stage 2 prompt: generate Oracle SELECT SQL from domain schemas + few-shot examples."""
    from mes_dashboard.services.ai_schema_context import (
        get_examples_for_domains,
        get_schemas_for_domains,
    )
    from mes_dashboard.services.ai_business_context import (
        get_dynamic_metadata_block,
        SCRAP_EXCLUSION_RULES,
    )
    from mes_dashboard.sql.filters import CommonFilters

    schema_block = get_schemas_for_domains(domains)
    examples_block = get_examples_for_domains(domains)
    metadata_block = get_dynamic_metadata_block(domains)

    from datetime import date, timedelta

    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    non_quality_list = CommonFilters.get_non_quality_reasons_sql()

    lines = [
        "你是 Oracle SQL 生成器。根據使用者問題生成可執行的 Oracle SELECT 語句。",
        f"今天日期：{today.isoformat()}（使用者未指定日期時，預設 start_date={seven_days_ago.isoformat()}, end_date={today.isoformat()}）",
        "",
        "## 資料庫資訊",
        "- Oracle 19c DWH，帳號為 read-only（僅 SELECT）",
        "- 所有表名格式：DWH.TABLE_NAME",
        "- 使用 bind variables（:param_name），不要內嵌字串值",
        "",
        "## 可用表 Schema",
        schema_block,
        "",
        "## SQL 生成規則",
        "1. 只能使用上方列出的表，禁止其他表",
        "2. 只用 SELECT，禁止 INSERT/UPDATE/DELETE/DDL",
        "3. 歷史表（名稱含 HISTORY / MOVETXN / RESOURCESTATUS_SHIFT）必須加日期或 ID 條件",
        "   - 若問題已指定 lot / workorder / container_id / equipment_id 這類明確識別碼，可不加日期限制",
        "   - 只有在未指定明確識別碼、且問題是在做統計/趨勢/排行時，才預設近 7 天",
        "4. 即時 View（DW_MES_LOT_V、DW_MES_EQUIPMENTSTATUS_WIP_V）是當下快照，禁止加 SYS_DATE 日期過濾——問「目前/現在」直接查，不加日期條件",
        "5. 必須加 FETCH FIRST N ROWS ONLY（N 通常為 20-100）",
        "6. 日期條件用 :start_date 和 :end_date bind variable，params 值必須是 YYYY-MM-DD 格式的實際日期（禁止用 SYSDATE）",
        "7. 工站名稱比對：使用者說「DB」「WB」等縮寫時，params 必須轉成系統全名（如 DB→'焊接_DB%', WB→'焊接_WB%', 成型→'成型%'），參考業務術語的工站對照表",
        "8. Hold 原因名稱用 LIKE '%S1%' 模糊比對（使用者說 S1 但實際值可能是 'S1品質異常單(PE)'）",
        "9. 若使用者問『品質異常 Hold / 品質 Hold』，不可用 HOLDREASONNAME LIKE '%品質異常%'；應使用品質 Hold 定義：目前 HOLD 且 (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN (非品質 Hold 清單))",
        f"   非品質 Hold 清單：{non_quality_list}",
        "10. 若使用者提供的是產品型號關鍵字（例如 2N7002K），在即時 WIP 查詢時優先使用 PJ_TYPE，而不是 PRODUCT 精確比對",
        "11. 若使用者提供的是封裝型號（例如 SOT-23），優先使用 PRODUCTLINENAME 或 PACKAGE 類欄位",
        "12. 若使用者輸入 GA/GC 開頭（如 GA26020001），通常是生產工單，查 LOTWIPHISTORY 時優先用 PJ_WORKORDER，而不是 CONTAINERID",
        '13. 混合大小寫欄位必須用雙引號：e."Package", e."Function"（其餘欄位全大寫，不加引號）',
        "14. 若問題是『站點/站別』層級排行或彙總，優先以 WORKCENTER_GROUP（或 WORK_CENTER_GROUP）輸出，不可只用 WORKCENTERNAME 分組",
        "15. 若來源表只有 WORKCENTERNAME，需透過 DWH.DW_MES_SPEC_WORKCENTER_V（以 SPEC 對照）映射成 WORKCENTER_GROUP 後再彙總",
        "16. 若在 reject/yield 分析中使用 LOTREJECTHISTORY，必須套用報表一致的 Reject 排除規則（見下方），避免口徑偏差",
        "17. 若無法生成合理 SQL，回傳 sql: null",
        "",
    ]

    if metadata_block:
        lines += [metadata_block]

    if any(d in ("yield", "reject") for d in domains):
        lines += [
            "## Reject 排除口徑（與報表一致）",
            SCRAP_EXCLUSION_RULES,
            "",
        ]

    if examples_block:
        lines += [
            "## 參考 SQL 範例",
            examples_block,
            "",
        ]

    lines += [
        "## 回覆格式（嚴格 JSON，禁止其他文字）",
        '{"sql": "SELECT ...", "params": {"param1": "value1"}, "explanation": "一句話說明"}',
        "",
        "無法生成時：",
        '{"sql": null, "params": {}, "explanation": "說明原因"}',
    ]
    return "\n".join(lines)


def build_reviewer_prompt(domains: list[str]) -> str:
    """Reviewer prompt: validate generated SQL against known business logic pitfalls.

    This is a lightweight check BEFORE execution to catch "syntactically correct
    but logically wrong" SQL — the class of errors that Oracle won't catch.
    """
    from mes_dashboard.services.ai_business_context import SYSTEM_OVERVIEW
    from mes_dashboard.services.ai_schema_context import TABLE_DOMAINS

    # Build list of allowed tables for these domains
    allowed_tables = []
    for d in domains:
        entry = TABLE_DOMAINS.get(d, {})
        allowed_tables.extend(entry.get("tables", []))
    allowed_tables_str = ", ".join(sorted(set(allowed_tables)))

    return "\n".join([
        "你是 MES Dashboard SQL 審查員。檢查以下 SQL 是否正確回答使用者的問題。",
        "",
        f"## 本次查詢允許使用的表：{allowed_tables_str}",
        "",
        SYSTEM_OVERVIEW,
        "",
        "## 審查重點（已知常見錯誤）",
        "",
        "### 1. 即時 vs 歷史表選擇",
        "- 問「現在/目前」狀態 → 必須用即時 View（LOT_V / EQUIPMENTSTATUS_WIP_V）",
        "- 問「歷史/趨勢/近N天」→ 必須用歷史表（HOLDRELEASEHISTORY / LOTREJECTHISTORY 等）",
        "- 常見錯誤：問「現在 HOLD 多少」卻查 HOLDRELEASEHISTORY",
        "- 即時 View（LOT_V / EQUIPMENTSTATUS_WIP_V）是當下快照，禁止加 SYS_DATE 日期過濾",
        "- 常見錯誤：查 LOT_V 時加了 SYS_DATE BETWEEN 導致查不到資料",
        "- 歷史表若已提供明確識別碼（例如工單、lot、container_id、equipment_id），可以不加日期限制",
        "- 常見錯誤：已指定工單或 lot，卻仍強制加近 7 天條件，導致查不到歷史資料",
        "",
        "### 2. Hold 原因比對方式",
        "- 使用者說 S1/S2 等縮寫，系統中實際值是完整名稱（如 S2品質異常單(PE)）",
        "- 必須用 LIKE '%S1%' 模糊比對，不能用 = 'S1' 精確比對",
        "- 使用者問『品質異常 Hold / 品質 Hold』時，不可用 HOLDREASONNAME LIKE '%品質異常%'",
        "- 正確做法：以目前 HOLD 批次為母集合，排除非品質 Hold 原因後的剩餘批次才是品質 Hold",
        "- 非品質 Hold 原因包含：IQC檢驗(久存品驗證)(QC)、工程驗證(PE)、工程驗證(RD)、指定機台生產、特殊需求(X-Ray全檢)、特殊需求管控、第一次量產QC品質確認(QC)、需綁尾數(PD)、樣品需求留存打樣(樣品)、盤點(收線)需求等",
        "",
        "### 3. 欄位語義正確性",
        "- 不良率分母：用 MOVEINQTY（進站數量），不是 TRACKINQTY 或 QTYTOPROCESS",
        "- WIP 狀態：用 EQUIPMENTCOUNT>0 判斷 RUN，CURRENTHOLDCOUNT>0 判斷 HOLD",
        "- JOBID 是維修工單 ID，JOBORDER/MFGORDERNAME 才是生產工單號",
        "- LOT_V 的工單欄位叫 WORKORDER（非 MFGORDERNAME）",
        "- LOT_V 中 PRODUCT 是完整產品料號；PJ_TYPE 才常對應使用者口中的產品型號（例如 2N7002K）",
        "- 使用者若問『2N7002K 現在在哪些站點生產』，不可寫 PRODUCT = '2N7002K'；應優先考慮 PJ_TYPE = '2N7002K'",
        "- 使用者若問封裝型號（例如 SOT-23），應優先考慮 PRODUCTLINENAME / PACKAGE 類欄位",
        "- 使用者若輸入 GA/GC 開頭（例如 GA26020001），通常是生產工單，不是 CONTAINERID",
        "- 查 LOTWIPHISTORY 時，工單應使用 PJ_WORKORDER；只有 lot 才用 CONTAINERID / LOTID 類欄位",
        "- 查 LOTWIPHISTORY / LOTMATERIALSHISTORY / LOTREJECTHISTORY / HOLDRELEASEHISTORY 這類歷史表時，若使用者給的是 LOTID/CONTAINERNAME，通常要先 resolve 成 CONTAINERID",
        "- FINISHEDRUNCARD 不是通用主鍵；若題目在問 genealogy / 成品流水號關係，應優先考慮 COMBINEDASSYLOTS / lineage 表",
        "",
        "### 4. 混合大小寫欄位",
        '- Package 和 Function 必須用雙引號："Package"、"Function"',
        "",
        "### 5. 日期參數",
        "- params 中的日期必須是 YYYY-MM-DD 格式，不能是 SYSDATE",
        "",
        "### 6. 工站名稱參數",
        "- workcenter_pattern 的值必須用系統全名（如 '焊接_DB%'），不能用縮寫（如 'DB%'）",
        "- 對照：DB→焊接_DB%, WB→焊接_WB%, DW→焊接_DW%, 成型→成型%, TMTT→TMTT%, 品檢→品檢%, FQC→FQC%",
        "",
        "### 7. 站點彙總與 Reject 口徑一致性",
        "- 若問題在問『站點/站別』排行（例如『昨天哪些站點良率較低』），分組欄位應是 WORKCENTER_GROUP（或 WORK_CENTER_GROUP），不可僅以 WORKCENTERNAME 分組",
        "- 若來源只有 WORKCENTERNAME，應透過 DW_MES_SPEC_WORKCENTER_V 以 SPEC 對照映射 WORKCENTER_GROUP",
        "- 若使用 LOTREJECTHISTORY 做良率/不良率分析，需套用 Reject 排除口徑：",
        "  1) 排除 MATERIAL 報廢（透過 container/object type）",
        "  2) 排除 ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE（ENABLE_FLAG='Y'）列出的原因",
        "  3) 排除不符合 ^[0-9]{3}_ 或符合 ^(XXX|ZZZ)_ 的原因",
        "",
        "## 回覆格式（嚴格 JSON）",
        "",
        "審查通過：",
        '{"approved": true}',
        "",
        "審查不通過（只列出問題，不要自己改 SQL）：",
        '{"approved": false, "issues": ["具體問題描述1", "具體問題描述2"]}',
        "",
        "規則：",
        "- 只列出上述 7 類已知問題（含即時 View 禁加日期），不要做其他審查",
        "- issues 要具體說明哪裡錯、應該怎麼做（讓 SQL 生成器能根據 issues 修正）",
        "- 不要自己重寫 SQL",
    ])


# ---------------------------------------------------------------------------
# Prompt builders — combined (D1) and three-round (deprecated R1/R2)
# ---------------------------------------------------------------------------

def build_combined_prompt() -> str:
    """Combined prompt: select function AND fill params in a single LLM call.

    Replaces the two-round R1 (intent select) + R2 (param fill) sequence.
    The model receives all function names + descriptions (same as R1 catalogue)
    plus an instruction to also emit params for the chosen function.

    Output schema: {"function": "<name>", "params": {...}, "explanation": "<string>"}

    Per design D1: does NOT inline full parameter schemas (param correctness is
    enforced post-hoc by validate_intent + YAML default-merge).
    """
    lines = [
        "你是 MES Dashboard AI 助手。使用者會用中文描述查詢需求。",
        "從下方函式目錄中選出最合適的函式，並同時填入該函式所需的參數。",
        "",
        "## 嚴格規則",
        "- 你的回覆必須是且僅是一個 JSON 物件",
        "- 禁止輸出任何推理過程、解釋、markdown 或其他文字",
        "- 直接輸出 JSON，不要用 ```json 包裝",
        "",
        "## 回覆格式",
        '{"function": "<函式名稱>", "params": {<依函式需求填入>}, "explanation": "<一句話說明>"}',
        "",
        "若無合適函式：",
        '{"function": null, "params": {}, "explanation": "<說明原因>"}',
        "",
        "## 參數填寫說明",
        "- params 只填入使用者問題中明確提及的資訊",
        "- 日期格式：YYYY-MM-DD；若未指定，start_date 預設今天往前 7 天，end_date 預設今天",
        "- 不確定的可選參數可省略（留空）",
        "",
        "## 函式目錄",
    ]
    for func_name, entry in REGISTRY.items():
        lines.append(f"- {func_name}：{entry['description']}")
    return "\n".join(lines)


def build_round1_prompt() -> str:
    """Round 1: compact function list (name + description only, ~400-500 tokens).

    # deprecated — use build_combined_prompt()
    """
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
    """Round 2: single function full schema + date rules + workcenter list (~500 tokens).

    # deprecated — use build_combined_prompt()
    """
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
        "- 只陳述查詢結果中明確存在的事實與數據，不要揣測原因、不要推論趨勢、不要給出資料中沒有依據的建議",
        "- 如果資料不足以回答某個面向，直接說明「資料中未包含此資訊」，不要自行補充",
        "- 點出 2-3 個最關鍵的數據",
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


# ---------------------------------------------------------------------------
# Agent system prompt builder
# ---------------------------------------------------------------------------

def build_agent_system_prompt() -> str:
    """Assemble the complete system prompt for AI agent mode.

    Combines: role, business context, tool block, tool_call syntax,
    clarification guidance, response format rules, and current date.
    Target: ~4,000 tokens.
    """
    from datetime import date
    from mes_dashboard.services.ai_business_context import (
        BUSINESS_TERMINOLOGY,
        SYSTEM_OVERVIEW,
    )
    from mes_dashboard.services.ai_tool_definitions import build_tool_prompt_block

    today = date.today().isoformat()
    tool_block = build_tool_prompt_block()

    lines = [
        "你是 MES Dashboard AI 助手，協助工廠人員查詢製造資料並提供分析洞察。",
        f"今天日期：{today}",
        "",
        "## 系統背景",
        SYSTEM_OVERVIEW,
        "",
        "## 業務術語",
        BUSINESS_TERMINOLOGY,
        "",
        "## 可用工具",
        tool_block,
        "",
        "## 工具呼叫語法",
        "當你需要查詢資料時，使用以下格式呼叫工具：",
        "<tool_call>{\"name\": \"工具名稱\", \"arguments\": {\"參數名\": \"參數值\"}}</tool_call>",
        "",
        "規則：",
        "- 一次回覆可以包含多個 <tool_call> 標記",
        "- tool_call 標記外可以寫自然語言說明你的推理過程",
        "- 呼叫工具後，系統會自動執行並將結果注入下一輪 user message",
        "- 如果常駐工具無法滿足需求，先用 search_tools 搜尋更多工具",
        "- 優先使用函式工具；只有當常駐工具與 search_tools 都沒有合適函式時，才使用 query_database 讓系統生成 SQL 查詢",
        "- 不要重複呼叫相同工具（相同名稱+相同參數）",
        "",
        "## Clarification 指引",
        "如果使用者的問題缺少必要資訊（如日期範圍、工站名稱），直接用中文詢問。",
        "此時不要呼叫任何工具，只回覆問題即可。",
        "",
        "## 回應格式規則",
        "- 最終回答用繁體中文，直接回答問題",
        "- 點出 2-3 個關鍵數據或發現",
        "- 回覆不超過 5 句話",
        "- 不要輸出 markdown 標題或程式碼區塊",
        "- 如果資料為空，說明「目前無異常」或「查詢無結果」",
    ]

    return "\n".join(lines)

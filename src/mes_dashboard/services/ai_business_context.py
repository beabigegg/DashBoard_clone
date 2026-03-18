# -*- coding: utf-8 -*-
"""MES Dashboard 業務語境與規則 — 供 AI Text-to-SQL 使用。

本模組從報表系統的實際功能歸納業務語境，非窮舉規則，
而是讓 LLM 理解「這個系統是做什麼的、資料怎麼用」。
"""

# ---------------------------------------------------------------------------
# 系統概述（注入 Stage 1 prompt）
# ---------------------------------------------------------------------------

SYSTEM_OVERVIEW = """
本系統是半導體封裝測試廠的 MES (Manufacturing Execution System) Dashboard。
管理的核心對象：批次(LOT)、設備(機台)、工站(站別)。

## 資料時效性

系統有兩種資料來源，查詢時必須區分：

### 即時資料（View，幾分鐘內更新）
- DW_MES_LOT_V：目前廠內所有在製批次的即時快照（~10K 筆）
- DW_MES_EQUIPMENTSTATUS_WIP_V：所有設備的即時狀態（~2.8K 筆）
- 適用問題：「現在/目前/在線」的狀態查詢

### 歷史資料（Table，累積數據）
- 各種 HISTORY 表：記錄每一次事件（狀態變更、進出站、Hold/Release 等）
- 適用問題：「歷史/趨勢/統計/近N天/排行」的分析查詢
- 查詢時必須加日期範圍條件

## 判斷即時 vs 歷史的關鍵

| 使用者問法 | 資料來源 | 理由 |
|-----------|---------|------|
| 現在 HOLD 有多少/哪些/什麼原因 | LOT_V (即時) | 問的是「目前狀態」 |
| HOLD 歷史/誰 Hold 的/何時 Release | HOLDRELEASEHISTORY (歷史) | 問的是「過去事件」 |
| 機台目前在生產什麼 | EQUIPMENTSTATUS_WIP_V (即時) | 問的是「當下狀態」 |
| 機台近 7 天稼動率 | RESOURCESTATUS_SHIFT (歷史) | 問的是「歷史統計」 |
| 目前 WIP 多少 | LOT_V (即時) | 問的是「當下數量」 |
| 某批次的加工歷程 | LOTWIPHISTORY (歷史) | 問的是「過去軌跡」 |
""".strip()

# ---------------------------------------------------------------------------
# 業務術語對照（注入 Stage 1 prompt）
# ---------------------------------------------------------------------------

BUSINESS_TERMINOLOGY = """
## ID 格式辨識

| 格式 | 類型 | 範例 |
|------|------|------|
| GWXX-NNNN | 設備編號 | GWBK-0247, GWTM-1234, GCBA-0001 |
| GA/GC + 數字 | 生產工單號 | GA26031160, GC25060002 |
| 含連字號長編號 | 批次 Lot ID | GA23100020-A00-011 |
| 16 碼英數 | 內部 CONTAINERID | 系統用，使用者不會直接輸入 |

## 工站（站別）對照

使用者常用縮寫，系統中的 WORKCENTER_GROUP / WORKCENTERNAME 是全名：

| 縮寫 | 系統名稱 | 製程 |
|------|---------|------|
| DB | 焊接_DB | Die Bond（黏晶） |
| WB | 焊接_WB | Wire Bond（焊線） |
| DW | 焊接_DW | Die/Wire |
| MOLD / 成型 | 成型 | Molding（封膠） |
| TMTT / 測試 | TMTT | Testing |
| 切割 | 切割 | Die Saw |
| 品檢 / FVI | 品檢 | Final Visual Inspection |
| FQC | FQC | Final Quality Check |
| 電鍍 | 電鍍 | Plating |
| 吹砂 | 水吹砂 | Deflash |

## Hold 原因代碼（非工站名稱！）

以下是 HOLDREASONNAME 欄位的常見值，使用者提到這些時是指 Hold 原因：
- S1, S2, S3 → 品質異常等級代碼
- Q-Time Fail → 批次在站超時
- YieldLimit → 良率超標
- 產線自檢異常(PD) → 產線品質問題
- 這些都是 Hold 原因，不是工站名稱

## 設備狀態代碼

EQUIPMENTASSETSSTATUS 欄位的值：
- PRD = 生產中（Production）
- SBY = 待機（Standby）
- UDT = 非計畫停機（Unplanned Downtime）
- SDT = 計畫停機（Scheduled Downtime）
- EGT = 工程時間（Engineering Time）
- NST = 未排單（Not Scheduled）

## WIP 批次狀態判斷邏輯

在 DW_MES_LOT_V 中，批次狀態由欄位組合判斷（非直接欄位）：
- EQUIPMENTCOUNT > 0 → RUN（正在加工）
- EQUIPMENTCOUNT = 0 且 CURRENTHOLDCOUNT > 0 → HOLD（被暫停）
- EQUIPMENTCOUNT = 0 且 CURRENTHOLDCOUNT = 0 → QUEUE（排隊等待）

## 稼動率（OU%）計算

OU% = SUM(PRD 狀態小時數) / SUM(所有狀態小時數) × 100
資料來源：DW_MES_RESOURCESTATUS_SHIFT 的 HOURS 欄位，按 OLDSTATUSNAME 分組

## 維修工單 vs 生產工單

系統中有兩種「工單」，容易混淆：
- 生產工單（MFGORDERNAME / JOBORDER / PJ_WORKORDER）：GA/GC 開頭，管理批次生產
- 維修工單（JOBID / JOBORDERNAME）：設備故障報修，關聯 DW_MES_JOB 表
- EQUIPMENTSTATUS_WIP_V 中同時有兩者：JOBORDER=生產工單，JOBID=維修工單
""".strip()

# ---------------------------------------------------------------------------
# 報表功能對照（供 domain 選擇參考）
# ---------------------------------------------------------------------------

REPORT_DOMAIN_MAP = """
## 系統報表與資料領域對照

| 報表頁面 | 主要功能 | 查詢的表 | 對應 domain |
|---------|---------|---------|------------|
| WIP 概覽 | 即時在製品矩陣（工站×封裝型號） | LOT_V | wip_realtime |
| WIP 明細 | 即時批次清單（RUN/HOLD/QUEUE） | LOT_V | wip_realtime |
| Hold 概覽 | 即時 Hold 批次分佈 | LOT_V (CURRENTHOLDCOUNT>0) | wip_realtime |
| Hold 明細 | 特定 Hold 原因的批次清單 | LOT_V | wip_realtime |
| Hold 歷史 | Hold/Release 歷史趨勢分析 | HOLDRELEASEHISTORY | hold |
| Reject 歷史 | 不良/報廢趨勢分析 | LOTREJECTHISTORY, ERP_WIP_MOVETXN | reject |
| 設備狀態 | 即時設備狀態矩陣 | EQUIPMENTSTATUS_WIP_V, RESOURCE | wip_realtime, equipment |
| 設備歷史 | 設備稼動率趨勢/熱力圖 | RESOURCESTATUS_SHIFT, RESOURCE | equipment |
| 維修工單 | 設備維修記錄查詢 | JOB, JOBTXNHISTORY | job |
| 查詢工具 | 批次追蹤（正向/反向） | CONTAINER, LOTWIPHISTORY, 多表 JOIN | lot_history, genealogy |
| 物料追蹤 | 材料耗用追蹤 | LOTMATERIALSHISTORY, CONTAINER | material |
| 良率警報 | 良率異常檢測 | ERP_WIP_MOVETXN_DETAIL, LOTREJECTHISTORY | yield, reject |
| 中段缺陷 | 特定站別缺陷分析 | LOTREJECTHISTORY + 上下游追溯 | reject |
| 異常概覽 | 自動異常檢測（良率/不良/Hold/設備） | 多表（排程計算） | 各領域 |

## 常見問題 → 正確 domain 對照

| 問題類型 | 正確 domain | 錯誤 domain | 原因 |
|---------|------------|------------|------|
| 現在 HOLD 最多的原因 | wip_realtime | hold ❌ | 問「目前狀態」→ LOT_V |
| S1 HOLD 了哪些批次 | wip_realtime | reject ❌ | S1 是 Hold 原因，不是工站 |
| 某機台目前生產什麼 | wip_realtime | equipment ❌ | 問「即時」→ WIP View |
| 近 7 天 Hold 原因排行 | hold | wip_realtime ❌ | 問「歷史統計」→ 歷史表 |
| WB 站 OU% 最差的機台 | equipment | wip_realtime ❌ | OU% 需要歷史統計 |
| 某工單用了什麼線材 | material | lot_history ❌ | 問材料耗用 |
""".strip()

# ---------------------------------------------------------------------------
# 報廢排除規則（影響 reject 查詢的重要業務邏輯）
# ---------------------------------------------------------------------------

SCRAP_EXCLUSION_RULES = """
## 報廢/不良查詢的排除規則

系統在計算不良率時，有 4 層排除邏輯（依序套用）：
1. 排除 SCRAP_OBJECTTYPE = 'MATERIAL'（原物料報廢，非產品不良）
2. 排除 PRODUCTLINENAME LIKE 'PB_%'（PB 系列產品線不計入）
3. 排除 ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE 中 ENABLE_FLAG='Y' 的原因代碼
4. 排除不符合 ^[0-9]{3}_ 格式或符合 ^(XXX|ZZZ)_ 的原因名稱

這些規則已內建在報表頁面中，AI 查詢時若要與報表數據對齊，也應套用。
""".strip()


def get_stage1_business_context() -> str:
    """Return business context to inject into Stage 1 prompt."""
    return f"{SYSTEM_OVERVIEW}\n\n{BUSINESS_TERMINOLOGY}"


def get_stage1_domain_hints() -> str:
    """Return domain selection hints for Stage 1."""
    return REPORT_DOMAIN_MAP


# ---------------------------------------------------------------------------
# 動態 metadata — 從快取或 DB 取得實際資料值，注入 Stage 2 prompt
# ---------------------------------------------------------------------------

import logging
import time

logger = logging.getLogger("mes_dashboard.ai_business_context")

# In-memory cache: key -> (data, timestamp)
_metadata_cache: dict[str, tuple[list[str], float]] = {}
_METADATA_TTL = 600  # 10 minutes


def _get_cached_or_query(cache_key: str, sql: str, ttl: int = _METADATA_TTL) -> list[str]:
    """Query DB for distinct values with in-memory cache."""
    now = time.time()
    cached = _metadata_cache.get(cache_key)
    if cached and (now - cached[1]) < ttl:
        return cached[0]

    try:
        from mes_dashboard.core.database import read_sql_df
        df = read_sql_df(sql)
        values = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
        _metadata_cache[cache_key] = (values, now)
        return values
    except Exception as exc:
        logger.warning("Failed to query metadata [%s]: %s", cache_key, exc)
        # Return stale cache if available
        if cached:
            return cached[0]
        return []


def get_hold_reason_values() -> list[str]:
    """Get distinct HOLDREASONNAME values currently in WIP (LOT_V)."""
    return _get_cached_or_query(
        "hold_reasons",
        "SELECT DISTINCT HOLDREASONNAME FROM DWH.DW_MES_LOT_V "
        "WHERE CURRENTHOLDCOUNT > 0 AND HOLDREASONNAME IS NOT NULL "
        "ORDER BY HOLDREASONNAME",
    )


def get_workcenter_groups() -> list[str]:
    """Get distinct WORKCENTER_GROUP values from WIP."""
    return _get_cached_or_query(
        "workcenter_groups",
        "SELECT DISTINCT WORKCENTER_GROUP FROM DWH.DW_MES_LOT_V "
        "WHERE WORKCENTER_GROUP IS NOT NULL "
        "ORDER BY WORKCENTER_GROUP",
    )


def get_equipment_statuses() -> list[str]:
    """Get distinct EQUIPMENTASSETSSTATUS values."""
    return _get_cached_or_query(
        "equipment_statuses",
        "SELECT DISTINCT EQUIPMENTASSETSSTATUS FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V "
        "WHERE EQUIPMENTASSETSSTATUS IS NOT NULL "
        "ORDER BY EQUIPMENTASSETSSTATUS",
    )


def get_dynamic_metadata_block(domains: list[str]) -> str:
    """Build a metadata block for Stage 2 prompt based on selected domains.

    Injects real data values so LLM knows the exact format of enum fields.
    """
    lines = []

    if any(d in ("wip_realtime", "hold") for d in domains):
        reasons = get_hold_reason_values()
        if reasons:
            lines.append("## 目前系統中的 Hold 原因名稱（HOLDREASONNAME 實際值）")
            lines.append("使用者提到的縮寫要對應到下方完整名稱，用 LIKE 比對：")
            for r in reasons[:30]:
                lines.append(f"  - {r}")
            lines.append("")

    if any(d in ("wip_realtime",) for d in domains):
        wcs = get_workcenter_groups()
        if wcs:
            lines.append("## 目前系統中的工站群組（WORKCENTER_GROUP 實際值）")
            for w in wcs[:20]:
                lines.append(f"  - {w}")
            lines.append("")

    return "\n".join(lines) if lines else ""

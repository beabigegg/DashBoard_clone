# -*- coding: utf-8 -*-
"""AI Schema Context — condensed MES table schemas for Text-to-SQL pipeline.

Source: sql/**/*.sql template analysis × data/table_schema_info.json
Only columns that appear in at least one SQL template are included (10-20 per table).
Not loaded at runtime; imported statically by ai_function_registry.py prompt builders.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain grouping: domain_key -> {tables, keywords, description}
# ---------------------------------------------------------------------------
TABLE_DOMAINS: dict[str, dict] = {
    "wip_realtime": {
        "tables": [
            "DWH.DW_MES_LOT_V",
            "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V",
            "DWH.DW_MES_RESOURCE",
        ],
        "keywords": ["現在", "目前", "即時", "在製", "WIP", "機台狀態", "設備在製"],
        "description": "即時在製品 (WIP) 與設備即時狀態",
    },
    "lot_history": {
        "tables": [
            "DWH.DW_MES_CONTAINER",
            "DWH.DW_MES_LOTWIPHISTORY",
        ],
        "keywords": ["批次歷史", "生產歷程", "加工歷程", "trackin", "trackout", "流程歷史"],
        "description": "批次生產歷程（加工站進出紀錄）",
    },
    "reject": {
        "tables": [
            "DWH.DW_MES_LOTREJECTHISTORY",
            "DWH.ERP_WIP_MOVETXN",
            "DWH.ERP_WIP_MOVETXN_DETAIL",
            "DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE",
        ],
        "keywords": ["不良", "reject", "報廢", "scrap", "NG", "缺陷", "LOSSREASON"],
        "description": "批次不良 / Reject / 報廢歷史",
    },
    "hold": {
        "tables": [
            "DWH.DW_MES_HOLDRELEASEHISTORY",
        ],
        "keywords": ["hold", "Hold", "暫停", "鎖批", "釋放", "解Hold"],
        "description": "批次 Hold / Release 歷史",
    },
    "equipment": {
        "tables": [
            "DWH.DW_MES_RESOURCE",
            "DWH.DW_MES_RESOURCESTATUS",
            "DWH.DW_MES_RESOURCESTATUS_SHIFT",
            "DWH.DW_MES_SPEC_WORKCENTER_V",
            "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V",
            "DWH.DW_MES_JOB",
        ],
        "keywords": ["設備", "機台", "OU", "稼動率", "設備狀態", "resource", "workcenter", "station",
                     "DB", "WB", "MOLD", "TMTT", "FVI", "PRD", "UDT", "SDT", "EGT", "SBY"],
        "description": "設備 / 機台狀態與稼動率",
    },
    "material": {
        "tables": [
            "DWH.DW_MES_LOTMATERIALSHISTORY",
        ],
        "keywords": ["材料", "material", "耗材", "料件", "廠商批號"],
        "description": "批次材料用量歷史",
    },
    "job": {
        "tables": [
            "DWH.DW_MES_JOB",
            "DWH.DW_MES_JOBTXNHISTORY",
            "DWH.DW_MES_MAINTENANCE",
            "DWH.DW_MES_PARTREQUESTORDER",
            "DWH.DW_MES_RESOURCE",
        ],
        "keywords": ["job", "工單", "維修", "保養", "故障", "Job", "symptom", "cause", "repair"],
        "description": "設備工單 / 維修保養歷史",
    },
    "genealogy": {
        "tables": [
            "DWH.DW_MES_HM_LOTMOVEOUT",
            "DWH.DW_MES_PJ_COMBINEDASSYLOTS",
        ],
        "keywords": ["追溯", "genealogy", "合批", "分批", "流水批", "PJ_COMBINEDASSY"],
        "description": "批次追溯 / 合批分批關係",
    },
    "yield": {
        "tables": [
            "DWH.ERP_WIP_MOVETXN",
            "DWH.ERP_WIP_MOVETXN_DETAIL",
            "DWH.DW_MES_LOTREJECTHISTORY",
            "DWH.DW_MES_LOTWIPHISTORY",
        ],
        "keywords": ["良率", "yield", "OU%", "通過率", "pass rate"],
        "description": "良率分析（ERP 投入量為分母，reject 為分子）",
    },
    "wip_data": {
        "tables": [
            "DWH.DW_MES_LOTWIPDATAHISTORY",
            "DWH.DW_MES_WIP",
        ],
        "keywords": ["WIP data", "製程參數", "wip data", "wipdata", "SPC"],
        "description": "批次製程參數數據歷史 & WIP 快照",
    },
    "reference": {
        "tables": [
            "DWH.DW_MES_SPEC_WORKCENTER_V",
        ],
        "keywords": ["製程規格", "工站對照", "SPEC", "規格站別", "工序"],
        "description": "製程規格與工站對照（參考表）",
    },
}

# ---------------------------------------------------------------------------
# Table schemas: table_name -> condensed schema string
# ---------------------------------------------------------------------------
TABLE_SCHEMAS: dict[str, str] = {
    # ── 即時資料 (View) ──────────────────────────────────────────────────
    "DWH.DW_MES_LOT_V": """-- 即時在製品 View（約 9,923 筆，每批次一列）
-- 判斷批次狀態：EQUIPMENTCOUNT>0 → RUN；CURRENTHOLDCOUNT>0 → HOLD；否則 QUEUE
CONTAINERID       CHAR(16)      -- 批次內部 ID（主鍵，16 碼）
LOTID             VARCHAR2(40)  -- 批次編號（使用者可見的 Lot ID，如 GA23100020-A00-011）
STATUS            VARCHAR2(10)  -- 批次狀態（Active / Hold）
WORKORDER         VARCHAR2(40)  -- 生產工單號（GA/GC 開頭，如 GA26031160；注意此欄位非 MFGORDERNAME）
PRODUCTLINENAME   VARCHAR2(40)  -- 封裝型號（如 SOT-23, SOD-323HE, MSOP-8）
PRODUCT           VARCHAR2(40)  -- 產品料號（完整品名，如 SS1060VHEWS_R2_00001；注意此欄位非 PRODUCTNAME）
PJ_TYPE           VARCHAR2(40)  -- 產品類型（TYPE 分類）
PJ_FUNCTION       VARCHAR2(40)  -- 產品功能（FUNCTION 分類）
QTY               NUMBER        -- 在製數量（pcs）
EQUIPMENTCOUNT    NUMBER        -- 正在加工的機台數（>0 表示 RUN 中）
EQUIPMENTS        VARCHAR2      -- 目前加工機台編號清單
CURRENTHOLDCOUNT  NUMBER(10)    -- Hold 次數（>0 表示被 HOLD）
HOLDREASONNAME    VARCHAR2(40)  -- Hold 原因名稱
WORKCENTER_GROUP  VARCHAR2      -- 工站群組（如 焊接_DB, 焊接_WB, 成型, 測試）
WORKCENTERSEQUENCE_GROUP VARCHAR2 -- 工站工序群組序號（用於排序）
SPECNAME          VARCHAR2      -- 製程規格名稱
PACKAGE_LEF       VARCHAR2      -- 封裝 + LeadFrame 資訊
FIRSTNAME         VARCHAR2(40)  -- Wafer LOT ID（晶圓批號，如 GMSN-29383A#SK261296-03P）
WAFERDESC         VARCHAR2      -- Wafer 描述（晶圓規格說明）
SYS_DATE          DATE          -- 資料同步時間戳""",

    "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V": """-- 設備即時狀態 View（約 2,784 筆，每台設備一列）
-- 包含設備稼動狀態 + 當前掛載的生產工單 + 維修工單資訊
RESOURCEID        CHAR(16)      -- 設備內部 ID（主鍵，JOIN 用）
EQUIPMENTID       VARCHAR2(40)  -- 設備編號（使用者可見，如 GWBK-0247, GWTM-1234）
OBJECTCATEGORY    VARCHAR2(40)  -- 設備大類別（ASSEMBLY=後段封裝 / WAFERSORT=前段晶圓）
EQUIPMENTASSETSSTATUS VARCHAR2(40) -- 設備稼動狀態（PRD=生產中 / SBY=待機 / UDT=非計畫停機 / SDT=計畫停機 / EGT=工程時間 / NST=未排單）
EQUIPMENTASSETSSTATUSREASON VARCHAR2(40) -- 稼動狀態原因代碼
JOBORDER          VARCHAR2(40)  -- 目前掛載的生產工單號（如 GA26031160，非維修工單）
JOBMODEL          VARCHAR2(40)  -- 工單機型
JOBSTAGE          VARCHAR2(40)  -- 目前加工製程階段
JOBID             CHAR(16)      -- 維修工單 ID（關聯 DW_MES_JOB，非生產工單）
JOBSTATUS         VARCHAR2(40)  -- 維修工單狀態
CREATEDATE        DATE          -- 維修工單建立時間
CREATEUSERNAME    VARCHAR2(40)  -- 建立人員姓名
CREATEUSER        VARCHAR2(255) -- 建立人員帳號
TECHNICIANUSERNAME VARCHAR2(40) -- 技術員姓名
TECHNICIANUSER    VARCHAR2(255) -- 技術員帳號
SYMPTOMCODE       VARCHAR2(40)  -- 症狀碼
CAUSECODE         VARCHAR2(40)  -- 原因碼
REPAIRCODE        VARCHAR2(40)  -- 維修碼
RUNCARDLOTID      VARCHAR2(40)  -- 目前加工中的批次 Lot ID
Package           VARCHAR2(40)  -- 封裝型號（如 SOD-323HE）⚠ 混合大小寫，SQL 中必須寫 "Package"
PACKAGE_LF        VARCHAR2(4000)-- 封裝 + LeadFrame 詳細資訊
Function          VARCHAR2(40)  -- 產品 FUNCTION 分類 ⚠ 混合大小寫，SQL 中必須寫 "Function"
TYPE              VARCHAR2(40)  -- 產品 TYPE 分類
BOP               VARCHAR2(40)  -- Bill of Process（製程 BOP 名稱）
WAFERLOTID        VARCHAR2(40)  -- Wafer LOT ID（晶圓批號）
WAFERPN           VARCHAR2(40)  -- Wafer 料號
WAFERLOTID_PREFIX VARCHAR2(160) -- Wafer LOT ID 前綴（比 WAFERLOTID 更完整）
SPEC              VARCHAR2(40)  -- 製程規格名稱
LFOPTIONID        VARCHAR2(4000)-- LeadFrame Option ID 詳細
WIREDESCRIPTION   VARCHAR2(4000)-- 線材描述（金線/銀線/銅線規格）
WAFERMIL          VARCHAR2(3062)-- Die Size 規格（mil），如 "11/*11mil"
LOTTRACKINQTY_PCS NUMBER        -- Track-In 數量（pcs）
LOTTRACKINTIME    DATE          -- Track-In 時間（批次進站時刻）
LOTTRACKINEMPLOYEE VARCHAR2(255)-- Track-In 操作員帳號""",

    # ── 批次歷史 ─────────────────────────────────────────────────────────
    "DWH.DW_MES_CONTAINER": """-- 批次主檔（約 5,300,000 筆，所有歷史批次）
CONTAINERID       CHAR(16)      -- 批次內部 ID（主鍵，JOIN 用）
CONTAINERNAME     VARCHAR2(40)  -- 批次編號（使用者可見的 Lot ID）
MFGORDERNAME      VARCHAR2(40)  -- 生產工單號（GA/GC 開頭）
PRODUCTLINENAME   VARCHAR2(40)  -- 封裝型號（如 SOT-23）
PRODUCTNAME       VARCHAR2(40)  -- 產品料號
PJ_TYPE           VARCHAR2(40)  -- 產品類型
PJ_FUNCTION       VARCHAR2(40)  -- 產品功能
WORKCENTERNAME    VARCHAR2(40)  -- 目前所在工站
SPECNAME          VARCHAR2(40)  -- 製程規格
QTY               NUMBER        -- 批次數量（pcs）
HOLDREASONNAME    VARCHAR2(40)  -- Hold 原因
HOLDREASONID      CHAR(16)      -- Hold 原因 ID
FIRSTNAME         VARCHAR2(40)  -- Wafer LOT ID（晶圓批號）
OBJECTTYPE        VARCHAR2(40)  -- 物件類型
SPLITFROMID       CHAR(16)      -- 拆批來源容器 ID
ORIGINALCONTAINERID CHAR(16)    -- 原始容器 ID
MOVEINQTY         NUMBER        -- 進站數量""",

    "DWH.DW_MES_LOTWIPHISTORY": """-- 批次加工站進出歷史（每次 TrackIn/TrackOut 一筆）
-- 最穩定查詢鍵：CONTAINERID；若使用者提供 LOTID 通常需先 resolve
-- 若題目明確指定生產工單，可直接用 PJ_WORKORDER
CONTAINERID       CHAR(16)      -- 批次容器 ID
WORKCENTERNAME    VARCHAR2(40)  -- 加工站名稱（如 焊接_DB, 成型）
EQUIPMENTID       CHAR(16)      -- 設備 ID
EQUIPMENTNAME     VARCHAR2(40)  -- 設備編號
TRACKINTIMESTAMP  DATE          -- TrackIn 時間（進站）
TRACKOUTTIMESTAMP DATE          -- TrackOut 時間（出站，NULL=尚未出站）
TRACKINQTY        NUMBER        -- TrackIn 數量（pcs）
TRACKOUTQTY       NUMBER        -- TrackOut 數量（pcs）
SPECNAME          VARCHAR2(40)  -- 製程規格
PJ_WORKORDER      VARCHAR2(40)  -- 生產工單號
WORKFLOWNAME      VARCHAR2(40)  -- 製程流程名稱
FINISHEDRUNCARD   VARCHAR2(40)  -- Runcard 編號（流程欄位，非通用主鍵）""",

    # ── 不良/Hold ────────────────────────────────────────────────────────
    "DWH.DW_MES_LOTREJECTHISTORY": """-- 批次不良/Reject 歷史（約 16,100,000 筆）
CONTAINERID       CHAR(16)      -- 批次容器 ID
WORKCENTERNAME    VARCHAR2(50)  -- 發生不良的工站
LOSSREASONNAME    VARCHAR2      -- 不良原因名稱（損耗原因分類）
EQUIPMENTNAME     VARCHAR2      -- 造成不良的設備編號
TXNDATE           DATE          -- 不良發生時間
REJECTQTY         NUMBER        -- 不良數量（pcs）
DEFECTQTY         NUMBER        -- 缺陷數量（pcs）
MOVEINQTY         NUMBER        -- 該站進站數量（用於計算不良率：REJECTQTY/MOVEINQTY）
QTYTOPROCESS      NUMBER        -- 待處理數量
INPROCESSQTY      NUMBER        -- 加工中數量
PROCESSEDQTY      NUMBER        -- 已處理數量
STANDBYQTY        NUMBER        -- Standby 數量
SPECNAME          VARCHAR2      -- 製程規格
PJ_WORKORDER      VARCHAR2      -- 生產工單號
FINISHEDRUNCARD   VARCHAR2      -- Runcard 編號
HISTORYMAINLINEID CHAR(16)      -- 歷史主線 ID""",

    "DWH.DW_MES_HOLDRELEASEHISTORY": """-- Hold/Release 歷史（約 312,000 筆）
CONTAINERID       CHAR(16)      -- 批次容器 ID
HOLDTXNDATE       DATE          -- Hold 時間
RELEASETXNDATE    DATE          -- Release 時間（NULL=尚未解 Hold）
QTY               NUMBER        -- Hold 時的批次數量
HOLDREASONNAME    VARCHAR2      -- Hold 原因名稱（如 品質異常, S2, S1）
HOLDREASONID      CHAR(16)      -- Hold 原因 ID
HOLDCOMMENTS      VARCHAR2      -- Hold 備註說明
HOLDEMP           VARCHAR2      -- Hold 操作人員工號
HOLDEMPDEPTNAME   VARCHAR2      -- Hold 操作人員所屬部門
RELEASEEMP        VARCHAR2      -- Release 操作人員工號
RELEASECOMMENTS   VARCHAR2      -- Release 備註說明
FUTUREHOLDCOMMENTS VARCHAR2     -- 預 Hold 備註（Future Hold）
WORKCENTERNAME    VARCHAR2      -- Hold 時所在工站
NCRID             VARCHAR2      -- NCR 編號（品質異常通知單）
PJ_WORKORDER      VARCHAR2      -- 生產工單號""",

    # ── 設備/機台 ────────────────────────────────────────────────────────
    "DWH.DW_MES_RESOURCE": """-- 設備/資源主檔（約 91,673 筆，含設備+治具+載具等）
RESOURCEID        CHAR(16)      -- 設備內部 ID（主鍵）
RESOURCENAME      VARCHAR2(40)  -- 設備編號（如 GWBK-0247）
OBJECTCATEGORY    VARCHAR2(40)  -- 資源類別（ASSEMBLY / WAFERSORT）
OBJECTTYPE        VARCHAR2(40)  -- 資源類型（進一步分類）
WORKCENTERNAME    VARCHAR2(40)  -- 所屬工站（如 焊接_DB, 成型）
RESOURCEFAMILYNAME VARCHAR2(30) -- 設備型號系列
PJ_DEPARTMENT     VARCHAR2(100) -- 所屬部門
PJ_ISPRODUCTION   NUMBER        -- 是否為生產機台（1=是, 0=否）
PJ_ISKEY          NUMBER        -- 是否為關鍵機台（1=是, 0=否）
PJ_ISMONITOR      NUMBER        -- 是否為監控機台（1=是, 0=否）
PJ_ASSETSSTATUS   VARCHAR2(40)  -- 資產狀態
LOCATIONNAME      VARCHAR2(40)  -- 廠區位置
VENDORNAME        VARCHAR2(40)  -- 設備製造商
VENDORMODEL       VARCHAR2(30)  -- 設備型號""",

    "DWH.DW_MES_RESOURCESTATUS": """-- 設備狀態變更歷史（約 67,700,000 筆，每次狀態切換一筆）
-- HISTORYID = RESOURCEID，用於 JOIN DW_MES_RESOURCE
HISTORYID         CHAR(16)      -- 設備 ID（= RESOURCEID）
TXNDATE           DATE          -- 狀態變更時間
NEWSTATUSNAME     VARCHAR2(40)  -- 新狀態（PRD/SBY/UDT/SDT/EGT/NST）
OLDSTATUSNAME     VARCHAR2(40)  -- 前一狀態
NEWREASONNAME     VARCHAR2(40)  -- 新狀態原因代碼
OLDREASONNAME     VARCHAR2(40)  -- 前一狀態原因代碼
LASTSTATUSCHANGEDATE DATE       -- 此狀態的起始時間
WORKCENTERNAME    VARCHAR2(40)  -- 所屬工站
LOCATIONNAME      VARCHAR2(40)  -- 廠區位置
PJ_DEPARTMENT     VARCHAR2      -- 部門
JOBID             CHAR(16)      -- 關聯維修工單 ID
AVAILABILITY      NUMBER(10)    -- 設備可用率""",

    "DWH.DW_MES_RESOURCESTATUS_SHIFT": """-- 設備班別稼動統計（約 76,900,000 筆，每設備每班每狀態一筆）
-- HISTORYID = RESOURCEID，HOURS = 該狀態在該班持續的小時數
-- 計算 OU%：SUM(PRD hours) / SUM(所有 hours) × 100
HISTORYID         CHAR(16)      -- 設備 ID（= RESOURCEID）
DATADATE          DATE          -- 統計日期（YYYY-MM-DD）
TXNDATE           DATE          -- 班別交易日期
SN                NUMBER        -- 班別序號（日內班次）
OLDSTATUSNAME     VARCHAR2(40)  -- 狀態名稱（PRD/SBY/UDT/SDT/EGT/NST）
NEWSTATUSNAME     VARCHAR2(40)  -- 新狀態
HOURS             NUMBER(12,6)  -- 此狀態持續小時數
WORKCENTERNAME    VARCHAR2(40)  -- 所屬工站
LOCATIONNAME      VARCHAR2(40)  -- 廠區位置
JOBID             CHAR(16)      -- 關聯維修工單 ID""",

    "DWH.DW_MES_SPEC_WORKCENTER_V": """-- 製程規格 × 工站對照 View（230 筆，參考表）
SPEC              VARCHAR2(40)  -- 製程規格代碼
WORK_CENTER       VARCHAR2(40)  -- 工站名稱
WORK_CENTER_GROUP VARCHAR2(40)  -- 工站群組（如 焊接_DB, 焊接_WB）
WORKCENTERSEQUENCE_GROUP VARCHAR2 -- 工站群組工序序號
WORK_CENTER_SHORT VARCHAR2(40)  -- 工站簡稱""",

    # ── 維修工單 ─────────────────────────────────────────────────────────
    "DWH.DW_MES_JOB": """-- 設備維修工單（約 1,273,902 筆，非生產工單）
-- 記錄設備故障報修、維修過程、完成狀態
JOBID             CHAR(16)      -- 維修工單 ID（主鍵）
RESOURCEID        CHAR(16)      -- 維修的設備 ID
RESOURCENAME      VARCHAR2(40)  -- 維修的設備編號
JOBSTATUS         VARCHAR2(40)  -- 工單狀態（New/Assigned/InProgress/Complete/Cancel）
JOBMODELNAME      VARCHAR2(40)  -- 維修類型（維修分類模型）
JOBORDERNAME      VARCHAR2(40)  -- 維修工單編號
CREATEDATE        DATE          -- 報修時間
COMPLETEDATE      DATE          -- 維修完成時間
CANCELDATE        DATE          -- 取消時間
FIRSTCLOCKONDATE  DATE          -- 首次開工時間
LASTCLOCKOFFDATE  DATE          -- 最後收工時間
SYMPTOMCODENAME   VARCHAR2(40)  -- 故障症狀代碼
CAUSECODENAME     VARCHAR2(40)  -- 故障原因代碼
REPAIRCODENAME    VARCHAR2(40)  -- 修復方式代碼
PJ_CAUSECODE2NAME VARCHAR2(40)  -- 次要故障原因
PJ_REPAIRCODE2NAME VARCHAR2(40) -- 次要修復方式
PJ_SYMPTOMCODE2NAME VARCHAR2(40)-- 次要故障症狀
CONTAINERNAMES    VARCHAR2(2000)-- 受影響的批次名稱清單""",

    "DWH.DW_MES_JOBTXNHISTORY": """-- 維修工單狀態變更歷史（約 9,743,810 筆）
JOBID             CHAR(16)      -- 維修工單 ID
TXNDATE           DATE          -- 狀態變更時間
JOBSTATUS         VARCHAR2(40)  -- 變更後狀態
FROMJOBSTATUS     VARCHAR2(40)  -- 變更前狀態
JOBMODELNAME      VARCHAR2(40)  -- 維修類型
JOBORDERNAME      VARCHAR2(40)  -- 維修工單編號
STAGENAME         VARCHAR2(40)  -- 維修流程階段
TOSTAGENAME       VARCHAR2(40)  -- 目標階段
SYMPTOMCODENAME   VARCHAR2(40)  -- 故障症狀
CAUSECODENAME     VARCHAR2(40)  -- 故障原因
REPAIRCODENAME    VARCHAR2(40)  -- 修復方式
USER_NAME         VARCHAR2(255) -- 操作人員姓名
COMMENTS          VARCHAR2(255) -- 維修備註""",

    # ── 材料/物料 ────────────────────────────────────────────────────────
    "DWH.DW_MES_LOTMATERIALSHISTORY": """-- 批次材料耗用歷史（每次耗料一筆）
-- 最穩定查詢鍵：CONTAINERID；若輸入為 LOTID 通常需先反查
CONTAINERID       CHAR(16)      -- 批次容器 ID
TXNDATE           DATE          -- 耗用時間
MATERIALPARTNAME  VARCHAR2      -- 材料料號（如 WAF002861_CP, LEF000074）
MATERIALLOTNAME   VARCHAR2      -- 材料批號（廠商批號或內部編號）
EQUIPMENTNAME     VARCHAR2      -- 耗用設備編號
WORKCENTERNAME    VARCHAR2      -- 耗用工站
QTYCONSUMED       NUMBER        -- 實際耗用數量
QTYREQUIRED       NUMBER        -- 需求數量
PJ_WORKORDER      VARCHAR2      -- 生產工單號
VENDORLOTNUMBER   VARCHAR2      -- 廠商批號
PRIMARY_CATEGORY  VARCHAR2      -- 材料主類別（如 WAFER, LEADFRAME, WIRE, COMPOUND）
SECONDARY_CATEGORY VARCHAR2     -- 材料次類別
SPECNAME          VARCHAR2      -- 製程規格""",

    # ── 批次追溯/族譜 ───────────────────────────────────────────────────
    "DWH.DW_MES_HM_LOTMOVEOUT": """-- 批次出站歷史（約 49,400,000 筆，追溯用）
CONTAINERID       CHAR(16)      -- 批次容器 ID
CONTAINERNAME     VARCHAR2(40)  -- 批次編號
RESOURCEID        CHAR(16)      -- 出站設備 ID
RESOURCENAME      VARCHAR2(40)  -- 出站設備編號
WORKCENTER        VARCHAR2(40)  -- 出站工站
SPECNAME          VARCHAR2(40)  -- 製程規格
QTY               NUMBER        -- 出站數量
QTY2              NUMBER        -- 出站數量（次級單位）
MOVEINTIMESTAMP   DATE          -- 進站時間
LASTMOVEOUTTIMESTAMP DATE       -- 出站時間
TXNDATE           DATE          -- 交易日期
PRODUCTNAME       VARCHAR2(40)  -- 產品料號
HISTORYMAINLINEID CHAR(16)      -- 歷史主線 ID""",

    "DWH.DW_MES_PJ_COMBINEDASSYLOTS": """-- 併批紀錄（約 1,994,711 筆，流水批合併追溯）
-- 一筆記錄 = 一個來源批次併入一個成品批次
CONTAINERID       CHAR(16)      -- 成品批次容器 ID
CONTAINERNAME     VARCHAR2(40)  -- 成品批次編號（流水批號）
LOTID             CHAR(16)      -- 來源批次 ID（被合併的批次）
FINISHEDNAME      VARCHAR2(40)  -- 完成品名稱 / 成品流水號關聯欄位
PJ_WORKORDER      VARCHAR2(40)  -- 生產工單號
PJ_GOODDIEQTY     NUMBER        -- 良品 Die 數量
PJ_ORIGINALGOODDIEQTY NUMBER    -- 合併前的原始良品數量
PJ_COMBINEDRATIO  NUMBER        -- 合併比例
ORIGINALSTARTDATE DATE          -- 原始批次建檔日期""",

    # ── 製程參數/WIP 快照 ────────────────────────────────────────────────
    "DWH.DW_MES_LOTWIPDATAHISTORY": """-- 批次製程參數量測歷史
CONTAINERID       CHAR(16)      -- 批次容器 ID
PJ_WORKORDER      VARCHAR2      -- 生產工單號
WORKCENTERNAME    VARCHAR2      -- 量測工站
SPECNAME          VARCHAR2      -- 製程規格
EQUIPMENTID       CHAR(16)      -- 量測設備 ID
EQUIPMENTNAME     VARCHAR2      -- 量測設備編號
TXNTIMESTAMP      DATE          -- 量測時間
WIPDATANAMENAME   VARCHAR2      -- 製程參數名稱（量測項目）
WIPDATAVALUE      VARCHAR2      -- 製程參數值（量測結果）
PJ_SPCDATARESULT  VARCHAR2      -- SPC 判定結果""",

    "DWH.DW_MES_WIP": """-- WIP 快照表（非即時，定期匯入）
CONTAINERID       CHAR(16)      -- 批次容器 ID
CONTAINERNAME     VARCHAR2      -- 批次編號
MFGORDERNAME      VARCHAR2      -- 生產工單號
PRODUCTLINENAME   VARCHAR2      -- 封裝型號
PJ_TYPE           VARCHAR2      -- 產品類型
WORKFLOWNAME      VARCHAR2      -- 製程流程名稱
SPECNAME          VARCHAR2      -- 製程規格
WORKCENTERNAME    VARCHAR2      -- 所在工站
TXNDATE           DATE          -- 快照時間""",

    # ── 設備保養 ─────────────────────────────────────────────────────────
    "DWH.DW_MES_MAINTENANCE": """-- 設備保養/維護歷史（約 55,100,000 筆）
RESOURCEID        CHAR(16)      -- 設備 ID
RESOURCENAME      VARCHAR2(40)  -- 設備編號
MAINTENANCEREQNAME VARCHAR2(255)-- 保養項目名稱
TXNDATE           DATE          -- 保養執行時間
SHIFTNAME         VARCHAR2(30)  -- 執行班別
LASTDATEDUE       DATE          -- 上次到期日
THRUPUTQTY        NUMBER        -- 產量累計（用於產量觸發保養）
DATANAME          VARCHAR2(255) -- 量測/檢查項目名稱
DATAVALUE         VARCHAR2(255) -- 量測/檢查結果值
LOCATIONNAME      VARCHAR2(40)  -- 設備位置
USERNAME          VARCHAR2(40)  -- 操作人員工號
EMPLOYEENAME      VARCHAR2(40)  -- 操作人員姓名""",

    # ── 零件請購 ─────────────────────────────────────────────────────────
    "DWH.DW_MES_PARTREQUESTORDER": """-- 維修零件請購單
JOBID             CHAR(16)      -- 關聯的維修工單 ID
PARTREQUESTORDERID CHAR(16)     -- 請購單 ID
PARTREQUESTORDERNAME VARCHAR2   -- 請購單名稱
RESOURCEID        CHAR(16)      -- 設備 ID
RESOURCENAME      VARCHAR2      -- 設備編號
REQUESTSTATUS     VARCHAR2      -- 請購狀態
ISDONE            NUMBER        -- 是否完成（1=完成）
CREATIONDATE      DATE          -- 建立時間
LASTCHANGEDATE    DATE          -- 最後變更時間
USER_NAME         VARCHAR2      -- 申請人""",

    # ── ERP 資料 ─────────────────────────────────────────────────────────
    "DWH.ERP_WIP_MOVETXN": """-- ERP 生產入出站交易（報廢/產出統計用）
WIP_ENTITY_NAME   VARCHAR2      -- 生產工單號
TXN_DATE          DATE          -- 交易時間
TRANSACTION_QUANTITY NUMBER     -- 交易數量（移轉數量）
SCRAP_QUANTITY    NUMBER        -- 報廢數量
REASON_NAME       VARCHAR2      -- 報廢原因名稱
REASON_CODE       VARCHAR2      -- 報廢原因代碼
OPERATION_SEQ_NUM NUMBER        -- 作業序號（工站序號）
DEPARTMENT_NAME   VARCHAR2      -- 部門名稱""",

    "DWH.ERP_WIP_MOVETXN_DETAIL": """-- ERP 生產入出站交易明細（含產品分類）
WIP_ENTITY_NAME   VARCHAR2      -- 生產工單號
TXN_DATE          DATE          -- 交易時間
PACKAGE           VARCHAR2      -- 封裝型號
TYPE              VARCHAR2      -- 產品 TYPE
FUNCTION          VARCHAR2      -- 產品 FUNCTION
LINE              VARCHAR2      -- 生產線別
OPERATION_SEQ_NUM NUMBER        -- 作業序號
DEPARTMENT_NAME   VARCHAR2      -- 部門名稱
REASON_NAME       VARCHAR2      -- 報廢原因名稱
REASON_CODE       VARCHAR2      -- 報廢原因代碼
TRANSACTION_QUANTITY NUMBER     -- 交易數量
SCRAP_QUANTITY    NUMBER        -- 報廢數量""",

    "DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE": """-- 報廢原因排除清單（參考表，用於過濾非真實報廢）
REASON_ID         NUMBER        -- 原因 ID
REASON_NAME       VARCHAR2      -- 原因名稱
DESCRIPTION       VARCHAR2      -- 說明
ENABLE_FLAG       VARCHAR2      -- 是否啟用（Y/N）
CREATION_DATE     DATE          -- 建立時間""",
}

# ---------------------------------------------------------------------------
# Few-shot SQL examples per domain
# ---------------------------------------------------------------------------
SQL_EXAMPLES: dict[str, list[dict[str, str]]] = {
    "wip_realtime": [
        {
            "question": "GWBK-0247 現在生產的產品是什麼？",
            "sql": (
                "SELECT e.EQUIPMENTID, e.EQUIPMENTASSETSSTATUS, "
                "e.JOBORDER, e.JOBMODEL, e.JOBSTATUS, "
                'e."Package", e.SPEC, e.RUNCARDLOTID, '
                "e.LOTTRACKINQTY_PCS, e.LOTTRACKINTIME "
                "FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e "
                "WHERE e.EQUIPMENTID = :equipment_id "
                "FETCH FIRST 10 ROWS ONLY"
            ),
        },
        {
            "question": "WB 站目前有多少台機台在跑？",
            "sql": (
                "SELECT e.EQUIPMENTASSETSSTATUS, COUNT(*) AS CNT "
                "FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e "
                "JOIN DWH.DW_MES_RESOURCE r ON r.RESOURCEID = e.RESOURCEID "
                "WHERE r.WORKCENTERNAME LIKE :workcenter_pattern "
                "GROUP BY e.EQUIPMENTASSETSSTATUS "
                "ORDER BY CNT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
        {
            "question": "目前在製中 Hold 批次有哪些？",
            "sql": (
                "SELECT CONTAINERID, LOTID, STATUS, QTY, HOLDREASONNAME, "
                "WORKCENTER_GROUP, SYS_DATE "
                "FROM DWH.DW_MES_LOT_V "
                "WHERE STATUS = 'Hold' "
                "ORDER BY SYS_DATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
        {
            "question": "現在 HOLD 最多的原因是什麼？",
            "sql": (
                "SELECT HOLDREASONNAME, COUNT(*) AS LOT_CNT, SUM(QTY) AS TOTAL_QTY "
                "FROM DWH.DW_MES_LOT_V "
                "WHERE CURRENTHOLDCOUNT > 0 "
                "GROUP BY HOLDREASONNAME "
                "ORDER BY LOT_CNT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
        {
            "question": "目前線上有多少品質異常 HOLD？",
            "sql": (
                "SELECT COUNT(*) AS QUALITY_HOLD_LOTS, SUM(QTY) AS QUALITY_HOLD_QTY "
                "FROM DWH.DW_MES_LOT_V "
                "WHERE CURRENTHOLDCOUNT > 0 "
                "AND (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ("
                "'IQC檢驗(久存品驗證)(QC)', '大中/安波幅50pcs樣品留樣(PD)', '工程驗證(PE)', '工程驗證(RD)', "
                "'指定機台生產', '特殊需求(X-Ray全檢)', '特殊需求管控', '第一次量產QC品質確認(QC)', "
                "'需綁尾數(PD)', '樣品需求留存打樣(樣品)', '盤點(收線)需求'"
                ")) "
                "FETCH FIRST 1 ROWS ONLY"
            ),
        },
        {
            "question": "2N7002K現在在哪些站點生產？",
            "sql": (
                "SELECT DISTINCT WORKCENTER_GROUP "
                "FROM DWH.DW_MES_LOT_V "
                "WHERE PJ_TYPE = :pj_type "
                "AND EQUIPMENTCOUNT > 0 "
                "ORDER BY WORKCENTER_GROUP "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
    ],
    "lot_history": [
        {
            "question": "批次 XYZ-001 的加工歷程？",
            "sql": (
                "SELECT h.CONTAINERID, h.WORKCENTERNAME, h.EQUIPMENTNAME, "
                "h.TRACKINTIMESTAMP, h.TRACKOUTTIMESTAMP, h.TRACKINQTY, h.TRACKOUTQTY "
                "FROM DWH.DW_MES_LOTWIPHISTORY h "
                "WHERE h.CONTAINERID = :container_id "
                "ORDER BY h.TRACKINTIMESTAMP "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天 WB 站各機台加工批次數量？",
            "sql": (
                "SELECT h.WORKCENTERNAME, h.EQUIPMENTNAME, COUNT(*) AS LOT_CNT, "
                "SUM(h.TRACKINQTY) AS TOTAL_QTY "
                "FROM DWH.DW_MES_LOTWIPHISTORY h "
                "WHERE h.WORKCENTERNAME LIKE :workcenter_pattern "
                "AND h.TRACKINTIMESTAMP >= :start_date "
                "AND h.TRACKINTIMESTAMP < :end_date "
                "GROUP BY h.WORKCENTERNAME, h.EQUIPMENTNAME "
                "ORDER BY LOT_CNT DESC "
                "FETCH FIRST 30 ROWS ONLY"
            ),
        },
        {
            "question": "GA26020001在哪些機台生產過？",
            "sql": (
                "SELECT DISTINCT h.EQUIPMENTNAME "
                "FROM DWH.DW_MES_LOTWIPHISTORY h "
                "WHERE h.PJ_WORKORDER = :workorder_name "
                "ORDER BY h.EQUIPMENTNAME "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
        {
            "question": "GA23100020-A00-011 生產過哪些站點？",
            "sql": (
                "SELECT DISTINCT h.WORKCENTERNAME "
                "FROM DWH.DW_MES_CONTAINER c "
                "JOIN DWH.DW_MES_LOTWIPHISTORY h ON h.CONTAINERID = c.CONTAINERID "
                "WHERE c.CONTAINERNAME = :lot_id "
                "ORDER BY h.WORKCENTERNAME "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
    ],
    "reject": [
        {
            "question": "近 7 天 WB 站各不良原因排行？",
            "sql": (
                "SELECT NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)')) AS WORKCENTER_GROUP, "
                "NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') AS LOSSREASONNAME, "
                "SUM(r.REJECTQTY) AS TOTAL_REJECT "
                "FROM DWH.DW_MES_LOTREJECTHISTORY r "
                "LEFT JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = r.CONTAINERID "
                "LEFT JOIN ("
                "SELECT SPEC, MIN(WORK_CENTER_GROUP) KEEP (DENSE_RANK FIRST ORDER BY WORKCENTERSEQUENCE_GROUP) AS WORKCENTER_GROUP "
                "FROM DWH.DW_MES_SPEC_WORKCENTER_V WHERE SPEC IS NOT NULL GROUP BY SPEC"
                ") sm ON sm.SPEC = TRIM(r.SPECNAME) "
                "WHERE NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)')) LIKE :workcenter_pattern "
                "AND r.TXNDATE >= :start_date "
                "AND r.TXNDATE < :end_date "
                "AND UPPER(NVL(TRIM(c.OBJECTTYPE), '-')) <> 'MATERIAL' "
                "AND UPPER(NVL(TRIM(r.LOSSREASONNAME), '-')) NOT IN ("
                "SELECT UPPER(TRIM(REASON_NAME)) FROM DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE WHERE ENABLE_FLAG = 'Y'"
                ") "
                "AND REGEXP_LIKE(UPPER(NVL(TRIM(r.LOSSREASONNAME), '')), '^[0-9]{3}_') "
                "AND NOT REGEXP_LIKE(UPPER(NVL(TRIM(r.LOSSREASONNAME), '')), '^(XXX|ZZZ)_') "
                "GROUP BY NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)')), NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') "
                "ORDER BY TOTAL_REJECT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
        {
            "question": "批次 XYZ-001 的不良紀錄？",
            "sql": (
                "SELECT CONTAINERID, WORKCENTERNAME, LOSSREASONNAME, "
                "EQUIPMENTNAME, TXNDATE, REJECTQTY, DEFECTQTY "
                "FROM DWH.DW_MES_LOTREJECTHISTORY "
                "WHERE CONTAINERID = :container_id "
                "ORDER BY TXNDATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天各工單報廢數量？",
            "sql": (
                "SELECT d.WIP_ENTITY_NAME, d.PACKAGE, d.REASON_NAME, "
                "SUM(d.SCRAP_QUANTITY) AS TOTAL_SCRAP "
                "FROM DWH.ERP_WIP_MOVETXN_DETAIL d "
                "WHERE d.TXN_DATE >= :start_date "
                "AND d.TXN_DATE < :end_date "
                "AND d.SCRAP_QUANTITY > 0 "
                "GROUP BY d.WIP_ENTITY_NAME, d.PACKAGE, d.REASON_NAME "
                "ORDER BY TOTAL_SCRAP DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
    ],
    "hold": [
        {
            "question": "近 7 天 Hold 次數最多的原因？",
            "sql": (
                "SELECT HOLDREASONNAME, COUNT(*) AS HOLD_CNT, SUM(QTY) AS TOTAL_QTY "
                "FROM DWH.DW_MES_HOLDRELEASEHISTORY "
                "WHERE HOLDTXNDATE >= :start_date "
                "AND HOLDTXNDATE < :end_date "
                "GROUP BY HOLDREASONNAME "
                "ORDER BY HOLD_CNT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
        {
            "question": "批次 XYZ-001 的 Hold 歷史？",
            "sql": (
                "SELECT CONTAINERID, HOLDTXNDATE, RELEASETXNDATE, QTY, "
                "HOLDREASONNAME, HOLDEMP, RELEASEEMP, HOLDCOMMENTS "
                "FROM DWH.DW_MES_HOLDRELEASEHISTORY "
                "WHERE CONTAINERID = :container_id "
                "ORDER BY HOLDTXNDATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
    ],
    "equipment": [
        {
            "question": "近 7 天 WB 站各機台 OU% 是多少？",
            "sql": (
                "SELECT rs.HISTORYID, rs.TXNDATE, rs.OLDSTATUSNAME, rs.HOURS, "
                "rs.WORKCENTERNAME "
                "FROM DWH.DW_MES_RESOURCESTATUS_SHIFT rs "
                "WHERE rs.WORKCENTERNAME LIKE :workcenter_pattern "
                "AND rs.TXNDATE >= :start_date "
                "AND rs.TXNDATE < :end_date "
                "ORDER BY rs.TXNDATE DESC "
                "FETCH FIRST 200 ROWS ONLY"
            ),
        },
        {
            "question": "DB 站目前有哪些設備在 UDT 狀態？",
            "sql": (
                "SELECT r.RESOURCENAME, r.WORKCENTERNAME, rs.NEWSTATUSNAME, "
                "rs.TXNDATE, rs.NEWREASONNAME "
                "FROM DWH.DW_MES_RESOURCESTATUS rs "
                "JOIN DWH.DW_MES_RESOURCE r ON r.RESOURCEID = rs.HISTORYID "
                "WHERE r.WORKCENTERNAME LIKE :workcenter_pattern "
                "AND rs.NEWSTATUSNAME = 'UDT' "
                "ORDER BY rs.TXNDATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天故障最多的機台？",
            "sql": (
                "SELECT j.RESOURCEID, r.RESOURCENAME, r.WORKCENTERNAME, "
                "COUNT(*) AS JOB_CNT "
                "FROM DWH.DW_MES_JOB j "
                "JOIN DWH.DW_MES_RESOURCE r ON r.RESOURCEID = j.RESOURCEID "
                "WHERE j.CREATEDATE >= :start_date "
                "AND j.CREATEDATE < :end_date "
                "GROUP BY j.RESOURCEID, r.RESOURCENAME, r.WORKCENTERNAME "
                "ORDER BY JOB_CNT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
    ],
    "material": [
        {
            "question": "批次 XYZ-001 用了哪些材料？",
            "sql": (
                "SELECT CONTAINERID, WORKCENTERNAME, MATERIALPARTNAME, "
                "MATERIALLOTNAME, EQUIPMENTNAME, TXNDATE, QTYCONSUMED "
                "FROM DWH.DW_MES_LOTMATERIALSHISTORY "
                "WHERE CONTAINERID = :container_id "
                "ORDER BY TXNDATE "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天廠商批號 ABC123 被用在哪些批次？",
            "sql": (
                "SELECT CONTAINERID, WORKCENTERNAME, MATERIALPARTNAME, "
                "VENDORLOTNUMBER, TXNDATE, QTYCONSUMED "
                "FROM DWH.DW_MES_LOTMATERIALSHISTORY "
                "WHERE VENDORLOTNUMBER = :vendor_lot "
                "AND TXNDATE >= :start_date "
                "AND TXNDATE < :end_date "
                "ORDER BY TXNDATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
    ],
    "job": [
        {
            "question": "機台 GWBK-0247 近 7 天的維修紀錄？",
            "sql": (
                "SELECT j.JOBID, r.RESOURCENAME, j.CREATEDATE, j.COMPLETEDATE, "
                "j.JOBSTATUS, j.CAUSECODENAME, j.SYMPTOMCODENAME, j.REPAIRCODENAME "
                "FROM DWH.DW_MES_JOB j "
                "JOIN DWH.DW_MES_RESOURCE r ON r.RESOURCEID = j.RESOURCEID "
                "WHERE r.RESOURCENAME = :resource_name "
                "AND j.CREATEDATE >= :start_date "
                "AND j.CREATEDATE < :end_date "
                "ORDER BY j.CREATEDATE DESC "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天 WB 站最常見的故障症狀？",
            "sql": (
                "SELECT j.SYMPTOMCODENAME, COUNT(*) AS CNT "
                "FROM DWH.DW_MES_JOB j "
                "JOIN DWH.DW_MES_RESOURCE r ON r.RESOURCEID = j.RESOURCEID "
                "WHERE r.WORKCENTERNAME LIKE :workcenter_pattern "
                "AND j.CREATEDATE >= :start_date "
                "AND j.CREATEDATE < :end_date "
                "GROUP BY j.SYMPTOMCODENAME "
                "ORDER BY CNT DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
    ],
    "genealogy": [
        {
            "question": "工單 GA26010001 生成的流水批有哪些？",
            "sql": (
                "SELECT c.FINISHEDNAME, c.CONTAINERID, c.LOTID, "
                "c.PJ_WORKORDER, c.PJ_GOODDIEQTY, c.ORIGINALSTARTDATE "
                "FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS c "
                "WHERE c.PJ_WORKORDER = :workorder_name "
                "ORDER BY c.ORIGINALSTARTDATE "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
        {
            "question": "批次 XYZ-001 的 MoveOut 追溯記錄？",
            "sql": (
                "SELECT CONTAINERID, FROMCONTAINERID, CONTAINERNAME, "
                "FROMCONTAINERNAME, QTY, TXNDATE "
                "FROM DWH.DW_MES_HM_LOTMOVEOUT "
                "WHERE CONTAINERID = :container_id "
                "   OR FROMCONTAINERID = :container_id "
                "ORDER BY TXNDATE "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
    ],
    "yield": [
        {
            "question": "近 7 天 WB 站各機台良率？",
            "sql": (
                "SELECT h.WORKCENTERNAME, h.EQUIPMENTNAME, "
                "SUM(h.TRACKINQTY) AS TOTAL_IN, "
                "SUM(h.TRACKOUTQTY) AS TOTAL_OUT, "
                "ROUND(SUM(h.TRACKOUTQTY) / NULLIF(SUM(h.TRACKINQTY), 0) * 100, 2) AS YIELD_PCT "
                "FROM DWH.DW_MES_LOTWIPHISTORY h "
                "WHERE h.WORKCENTERNAME LIKE :workcenter_pattern "
                "AND h.TRACKINTIMESTAMP >= :start_date "
                "AND h.TRACKINTIMESTAMP < :end_date "
                "GROUP BY h.WORKCENTERNAME, h.EQUIPMENTNAME "
                "ORDER BY YIELD_PCT "
                "FETCH FIRST 30 ROWS ONLY"
            ),
        },
        {
            "question": "近 7 天不良率最高的站別？",
            "sql": (
                "SELECT NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)')) AS WORKCENTER_GROUP, "
                "SUM(r.REJECTQTY) AS TOTAL_REJECT, "
                "SUM(r.MOVEINQTY) AS TOTAL_IN, "
                "ROUND(SUM(r.REJECTQTY) / NULLIF(SUM(r.MOVEINQTY), 0) * 100, 4) AS REJECT_RATE "
                "FROM DWH.DW_MES_LOTREJECTHISTORY r "
                "LEFT JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = r.CONTAINERID "
                "LEFT JOIN ("
                "SELECT SPEC, MIN(WORK_CENTER_GROUP) KEEP (DENSE_RANK FIRST ORDER BY WORKCENTERSEQUENCE_GROUP) AS WORKCENTER_GROUP "
                "FROM DWH.DW_MES_SPEC_WORKCENTER_V WHERE SPEC IS NOT NULL GROUP BY SPEC"
                ") sm ON sm.SPEC = TRIM(r.SPECNAME) "
                "WHERE r.TXNDATE >= :start_date "
                "AND r.TXNDATE < :end_date "
                "AND UPPER(NVL(TRIM(c.OBJECTTYPE), '-')) <> 'MATERIAL' "
                "AND UPPER(NVL(TRIM(r.LOSSREASONNAME), '-')) NOT IN ("
                "SELECT UPPER(TRIM(REASON_NAME)) FROM DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE WHERE ENABLE_FLAG = 'Y'"
                ") "
                "AND REGEXP_LIKE(UPPER(NVL(TRIM(r.LOSSREASONNAME), '')), '^[0-9]{3}_') "
                "AND NOT REGEXP_LIKE(UPPER(NVL(TRIM(r.LOSSREASONNAME), '')), '^(XXX|ZZZ)_') "
                "GROUP BY NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)')) "
                "ORDER BY REJECT_RATE DESC "
                "FETCH FIRST 20 ROWS ONLY"
            ),
        },
    ],
    "wip_data": [
        {
            "question": "批次 XYZ-001 在 WB 站的製程參數？",
            "sql": (
                "SELECT CONTAINERID, WORKCENTERNAME, EQUIPMENTNAME, "
                "TXNTIMESTAMP, WIPDATANAMENAME, WIPDATAVALUE, PJ_SPCDATARESULT "
                "FROM DWH.DW_MES_LOTWIPDATAHISTORY "
                "WHERE CONTAINERID = :container_id "
                "ORDER BY TXNTIMESTAMP "
                "FETCH FIRST 100 ROWS ONLY"
            ),
        },
    ],
    "reference": [
        {
            "question": "製程規格 ABC 對應哪些站別？",
            "sql": (
                "SELECT SPEC, WORK_CENTER, WORK_CENTER_GROUP, WORKCENTERSEQUENCE_GROUP "
                "FROM DWH.DW_MES_SPEC_WORKCENTER_V "
                "WHERE SPEC LIKE :spec_pattern "
                "ORDER BY WORKCENTERSEQUENCE_GROUP "
                "FETCH FIRST 50 ROWS ONLY"
            ),
        },
    ],
}


def get_schemas_for_domains(domains: list[str]) -> str:
    """Return concatenated schema strings for the given domain keys."""
    seen_tables: set[str] = set()
    parts: list[str] = []
    for domain in domains:
        domain_def = TABLE_DOMAINS.get(domain, {})
        for tbl in domain_def.get("tables", []):
            if tbl not in seen_tables:
                seen_tables.add(tbl)
                schema = TABLE_SCHEMAS.get(tbl, "")
                if schema:
                    parts.append(f"### {tbl}\n{schema}")
    return "\n\n".join(parts)


def get_examples_for_domains(domains: list[str]) -> str:
    """Return formatted few-shot SQL examples for the given domain keys."""
    parts: list[str] = []
    for domain in domains:
        examples = SQL_EXAMPLES.get(domain, [])
        for ex in examples:
            parts.append(f"Q: {ex['question']}\nSQL:\n{ex['sql']}")
    return "\n\n".join(parts)

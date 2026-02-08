# MES 核心表詳細分析報告

**生成時間**: 2026-01-14（最後更新: 2026-01-29）
**分析範圍**: 19 張 MES 核心表（含 2 張 DWH 即時視圖 + 1 張工站對照視圖）
**資料來源**: MES_Database_Reference.md, DW_MES_LOT_V 實際數據分析, DW_MES_EQUIPMENTSTATUS_WIP_V 實際數據分析, DW_MES_SPEC_WORKCENTER_V 實際數據分析

---

## 目錄

1. [表性質分類總覽](#表性質分類總覽)
2. [即時數據表分析](#即時數據表分析)
3. [現況快照表分析](#現況快照表分析)
4. [歷史累積表分析](#歷史累積表分析)
5. [表間關聯關係圖](#表間關聯關係圖)
6. [關鍵業務場景查詢策略](#關鍵業務場景查詢策略)

---

## 表性質分類總覽

### 即時數據表（Real-time Views）
透過 DB Link 從 DWH 取得的即時 WIP / 設備狀態視圖，依來源更新頻率提供

| 表名 | 數據量 | 主要用途 | 更新方式 |
|------|--------|---------|---------|
| **DW_MES_LOT_V** | ~9,468 | 即時 WIP 分布（70欄位） | DB Link 即時查詢（依 PJ_LOT_MV 更新頻率） |
| **DW_MES_EQUIPMENTSTATUS_WIP_V** | ~2,631 | 設備資產狀態 + WIP 追蹤（32欄位） | DB Link 即時查詢（真正即時表） |

### 現況快照表（Snapshot Tables）
存儲當前狀態的數據，數據會被更新或覆蓋

| 表名 | 數據量 | 主要用途 | 更新方式 |
|------|--------|---------|---------|
| **DW_MES_WIP** | 79,058,085 | 在制品現況（含歷史累積） | 隨生產流程更新 |
| **DW_MES_RESOURCE** | 91,329 | 資源主檔（設備/工位） | 異動時更新 |
| **DW_MES_CONTAINER** | 5,218,406 | 容器當前狀態 | 隨批次流轉更新 |
| **DW_MES_JOB** | 1,248,622 | 設備維修工單當前狀態 | 維修工單狀態變更時更新 |

### 歷史累積表（Historical Tables）
只新增不修改，記錄完整的歷史軌跡

| 表名 | 數據量 | 主要用途 | 累積方式 |
|------|--------|---------|---------|
| **DW_MES_RESOURCESTATUS** | 65,742,614 | 資源狀態變更歷史 | 狀態變更時新增記錄 |
| **DW_MES_RESOURCESTATUS_SHIFT** | 74,820,134 | 資源班次狀態歷史 | 班次資料匯總新增 |
| **DW_MES_LOTWIPHISTORY** | 53,454,213 | 批次流轉歷史 | 每次移出/移入新增 |
| **DW_MES_LOTWIPDATAHISTORY** | 77,960,216 | 批次數據變更歷史 | 數據採集時新增 |
| **DW_MES_HM_LOTMOVEOUT** | 48,645,692 | 批次移出事件 | 移出操作時新增 |
| **DW_MES_JOBTXNHISTORY** | 9,554,723 | 維修工單交易歷史 | 維修工單狀態變更新增 |
| **DW_MES_LOTREJECTHISTORY** | 15,786,025 | 批次拒絕歷史 | 報廢操作時新增 |
| **DW_MES_LOTMATERIALSHISTORY** | 17,829,931 | 物料消耗歷史 | 物料使用時新增 |
| **DW_MES_HOLDRELEASEHISTORY** | 310,737 | 暫停/釋放歷史 | Hold/Release時新增 |
| **DW_MES_MAINTENANCE** | 52,060,026 | 設備維護歷史 | 維護活動時新增 |

### 輔助表（Auxiliary Tables）

| 表名 | 數據量 | 主要用途 |
|------|--------|---------|
| **DW_MES_PARTREQUESTORDER** | 61,396 | 物料請求訂單 |
| **DW_MES_PJ_COMBINEDASSYLOTS** | 1,965,425 | 組合裝配批次 |
| **DW_MES_SPEC_WORKCENTER_V** | 230 | 工站/工序對照視圖 |

---

## 即時數據表分析

### DW_MES_LOT_V（即時 WIP 批次視圖）⭐⭐⭐

**表性質**: 即時數據視圖（Real-time View）

**業務定義**: DWH 提供的即時 WIP 視圖，透過 DB Link 從 `PJ_LOT_MV@DWDB_MESDB` 取得，依 PJ_LOT_MV 更新頻率提供。包含完整的批次狀態、工站位置、設備資訊、Hold 原因等 70 個欄位，是 WIP Dashboard 的主要數據源。

**數據來源**: `PJ_LOT_MV@DWDB_MESDB`（DB Link 連線）

**數據量**: 約 9,468 筆（2026-01-29 查詢）

#### 欄位分類總覽（70 欄位）

| 分類 | 欄位數 | 說明 |
|------|--------|------|
| 批次識別 | 5 | LOTID, CONTAINERID, WORKORDER, FIRSTNAME, NO |
| 數量相關 | 6 | QTY, QTY2, STARTQTY, STARTQTY2, MOVEINQTY, MOVEINQTY2 |
| 狀態相關 | 4 | STATUS, CURRENTHOLDCOUNT, STARTREASON, OWNER |
| 時間相關 | 7 | STARTDATE, UTS, MOVEINTIMESTAMP, SYS_DATE, AGEBYDAYS, REMAINTIME, OCCURRENCEDATE |
| 工站/流程 | 12 | WORKCENTER*, SPEC*, STEP, WORKFLOWNAME, LOCATIONNAME |
| 產品/封裝 | 8 | PRODUCT, PRODUCTLINENAME, PACKAGE_LEF, MATERIALTYPE, PJ_TYPE, PJ_FUNCTION, BOP |
| Hold 相關 | 8 | HOLDREASONNAME, HOLDEMP, HOLDLOCATION, RELEASETIME, RELEASEEMP, RELEASEREASON, COMMENT_HOLD |
| 設備相關 | 4 | EQUIPMENTNAME, EQUIPMENTS, EQUIPMENTCOUNT, DEPTNAME |
| 物料資訊 | 6 | LEADFRAMENAME, LEADFRAMEOPTION, WAFERNAME, WAFERLOT, COMNAME, DATECODE |
| 備註/其他 | 10 | CONTAINERCOMMENTS, COMMENT_*, PRIORITYCODENAME, JOB*, PB_FUNCTION, TMTT_R, WAFER_FACTOR |

#### 關鍵時間欄位

| 欄位名 | 類型 | 用途 | 說明 |
|--------|------|------|------|
| `SYS_DATE` | TIMESTAMP | 數據更新時間 | 視圖同步時間戳，用於確認數據新鮮度 |
| `STARTDATE` | TIMESTAMP | 批次開始時間 | 批次投產的時間點 |
| `MOVEINTIMESTAMP` | TIMESTAMP | 移入當前工站時間 | 進入當前工序的時間 |
| `UTS` | VARCHAR2 | 預計完成日期 | 格式為 'YYYY/MM/DD' |
| `AGEBYDAYS` | NUMBER | 批次天數 | 從 STARTDATE 到現在的天數（含小數） |
| `REMAINTIME` | NUMBER | 剩餘時間 | 預計完成前的剩餘天數（含小數） |

#### 關鍵業務欄位詳解

##### 批次識別欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `LOTID` | VARCHAR2(40) | 批次號（業務識別碼） | `GA26011704-A00-003` |
| `CONTAINERID` | VARCHAR2(40) | 容器 ID（系統識別碼） | `48810480002ab0b4` |
| `WORKORDER` | VARCHAR2(40) | 工單號 | `GA26011704` |
| `FIRSTNAME` | VARCHAR2(100) | 首片批號 | `PSMS-4473#RFTLD3` |
| `NO` | NUMBER | 序號（查詢結果排序用） | 1, 2, 3... |

##### 狀態欄位

| 欄位名 | 類型 | 說明 | 實際值分布 |
|--------|------|------|-----------|
| `STATUS` | VARCHAR2(20) | 批次狀態 | `ACTIVE`（約 98.7%）、`HOLD`（約 1.3%） |
| `OWNER` | VARCHAR2(40) | 所有者/用途 | `量產`、`重工RW`、`代工`、`點測`、`樣品`、`餘晶`、`工程`、`久存`、`PROD`、`降規` |
| `MATERIALTYPE` | VARCHAR2(40) | 物料類型 | `成品`（約 99%）、`Wafer`（約 1%） |
| `STARTREASON` | VARCHAR2(40) | 開始原因 | `NORMAL`、`RW` 等 |

##### 數量欄位

| 欄位名 | 類型 | 說明 | 數值範圍 |
|--------|------|------|---------|
| `QTY` | NUMBER | 當前數量（主單位） | 1 - 3,000,000+ |
| `QTY2` | NUMBER | 當前數量（輔單位） | 通常為 0 |
| `STARTQTY` | NUMBER | 起始數量 | 通常 ≥ QTY |
| `MOVEINQTY` | NUMBER | 移入數量 | 進站時的數量 |

##### 工站/流程欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `WORKCENTERNAME` | VARCHAR2(40) | 工作中心名稱 | `成型`、`TMTT`、`電鍍`、`焊接` |
| `WORKCENTER_GROUP` | VARCHAR2(40) | 工作中心群組 | 與 WORKCENTERNAME 相同或分組 |
| `WORKCENTER_SHORT` | VARCHAR2(20) | 工站簡稱 | `Mold`、`TMTT`、`DB`、`WB` |
| `WORKCENTERSEQUENCE` | VARCHAR2(10) | 工站順序 | `130`、`300` 等（數值越大越後段） |
| `SPECNAME` | VARCHAR2(100) | 工序規格名稱 | `成型烘烤`、`PRE TMTT` |
| `STEP` | VARCHAR2(100) | 當前步驟 | 通常與 SPECNAME 相同 |
| `WORKFLOWNAME` | VARCHAR2(100) | 工藝流程名稱 | `PCC_SOT-223`、`UAC_SOD-523` |

##### 產品/封裝欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `PRODUCT` | VARCHAR2(100) | 產品名稱（完整） | `PJW5P06A_R2_00701` |
| `PRODUCTLINENAME` | VARCHAR2(40) | 產品線/封裝類型 | `SOT-223`、`SOD-523` |
| `PACKAGE_LEF` | VARCHAR2(40) | 封裝型號 | `SOT-223`、`SOD-523` |
| `PJ_TYPE` | VARCHAR2(40) | 產品型號 | `PJW5P06A`、`RB521S30-NC` |
| `PJ_FUNCTION` | VARCHAR2(40) | 產品功能分類 | `MOSFET`、`SKY` |
| `BOP` | VARCHAR2(40) | BOP 代碼 | `PCC15`、`UAC10` |

##### Hold 相關欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `HOLDREASONNAME` | VARCHAR2(100) | Hold 原因 | `S2品質異常單(PE)`、`特殊需求管控` |
| `CURRENTHOLDCOUNT` | NUMBER | 當前 Hold 次數 | 0 = 非 Hold，≥1 = Hold 中 |
| `HOLDEMP` | VARCHAR2(40) | Hold 操作人員 | 員工姓名 |
| `HOLDLOCATION` | VARCHAR2(40) | Hold 位置 | 通常為 NULL |
| `RELEASETIME` | TIMESTAMP | 預計解除時間 | NULL 表示未設定 |
| `RELEASEEMP` | VARCHAR2(40) | 解除人員 | NULL 表示尚未解除 |
| `RELEASEREASON` | VARCHAR2(200) | 解除原因 | NULL 表示尚未解除 |
| `COMMENT_HOLD` | VARCHAR2(4000) | Hold 備註 | 詳細說明 Hold 原因 |

##### 設備欄位（重要說明）

| 欄位名 | 類型 | 說明 | 使用工站 |
|--------|------|------|---------|
| `EQUIPMENTNAME` | VARCHAR2(40) | 設備名稱（單一設備） | TMTT（82%）、切彎腳（69%）、PKG_SAW |
| `EQUIPMENTS` | VARCHAR2(4000) | 設備清單（逗號分隔） | 成型、焊接、電鍍、打印等其他工站 |
| `EQUIPMENTCOUNT` | NUMBER | 設備數量 | 0 表示尚無設備綁定 |

**⚠️ 重要**: `EQUIPMENTNAME` 與 `EQUIPMENTS` 為**互斥使用**：
- **TMTT、切彎腳、PKG_SAW** 工站使用 `EQUIPMENTNAME`（單一設備）
- **其他工站**（成型、焊接、電鍍、打印等）使用 `EQUIPMENTS`（設備清單）
- 僅約 100 筆同時有兩欄位數據（均為 TMTT 工站）
- **建議查詢**: 使用 `COALESCE(EQUIPMENTNAME, EQUIPMENTS)` 取得統一設備資訊

##### 優先度欄位

| 欄位名 | 值 | 說明 |
|--------|-----|------|
| `PRIORITYCODENAME` | `1.超特急` | 最高優先度 |
| | `2.特急` | 高優先度 |
| | `3.急件` | 中高優先度（約 3%） |
| | `4.一般` | 一般優先度（約 96%） |

##### Hold 原因分布（參考數據）

| HOLDREASONNAME | 說明 | 典型佔比 |
|----------------|------|---------|
| `特殊需求管控` | 特殊製程或客戶要求 | 最常見 |
| `S2品質異常單(PE)` | PE 開立的品質異常 | 常見 |
| `現場品質異常單(PQC)` | PQC 開立的品質異常 | 常見 |
| `自行暫停` | 自主暫停 | 偶爾 |
| `治具不足HOLD` | 治具問題 | 偶爾 |
| 其他 | 換線暫停、生管暫停等 | 少見 |

#### 查詢策略

**1. WIP 即時分布統計（按工站）**
```sql
SELECT
    WORKCENTER_GROUP,
    WORKCENTER_SHORT,
    COUNT(*) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY,
    SUM(CASE WHEN STATUS = 'HOLD' THEN 1 ELSE 0 END) as HOLD_LOTS,
    SUM(CASE WHEN STATUS = 'HOLD' THEN QTY ELSE 0 END) as HOLD_QTY
FROM DW_MES_LOT_V
WHERE OWNER NOT IN ('DUMMY')  -- 排除 DUMMY 批次
GROUP BY WORKCENTER_GROUP, WORKCENTER_SHORT, WORKCENTERSEQUENCE_GROUP
ORDER BY TO_NUMBER(WORKCENTERSEQUENCE_GROUP);
```

**2. WIP 交叉分析（工站 x 封裝）**
```sql
SELECT
    WORKCENTER_GROUP,
    PRODUCTLINENAME,
    COUNT(*) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY
FROM DW_MES_LOT_V
WHERE OWNER NOT IN ('DUMMY')
GROUP BY WORKCENTER_GROUP, PRODUCTLINENAME
ORDER BY WORKCENTER_GROUP, LOT_COUNT DESC;
```

**3. Hold 批次清單**
```sql
SELECT
    LOTID,
    PRODUCT,
    WORKCENTERNAME,
    SPECNAME,
    QTY,
    HOLDREASONNAME,
    HOLDEMP,
    COMMENT_HOLD,
    AGEBYDAYS
FROM DW_MES_LOT_V
WHERE STATUS = 'HOLD'
ORDER BY AGEBYDAYS DESC;
```

**4. 設備使用查詢（統一處理 EQUIPMENTNAME/EQUIPMENTS）**
```sql
SELECT
    LOTID,
    WORKCENTERNAME,
    COALESCE(EQUIPMENTNAME, EQUIPMENTS) as EQUIPMENT_INFO,
    EQUIPMENTCOUNT,
    QTY
FROM DW_MES_LOT_V
WHERE COALESCE(EQUIPMENTNAME, EQUIPMENTS) IS NOT NULL
ORDER BY WORKCENTERNAME;
```

**5. 批次詳細查詢**
```sql
SELECT
    LOTID,
    CONTAINERID,
    WORKORDER,
    PRODUCT,
    PJ_TYPE,
    PJ_FUNCTION,
    PRODUCTLINENAME,
    WORKCENTERNAME,
    SPECNAME,
    STATUS,
    QTY,
    STARTQTY,
    AGEBYDAYS,
    REMAINTIME,
    UTS,
    PRIORITYCODENAME,
    OWNER,
    COALESCE(EQUIPMENTNAME, EQUIPMENTS) as EQUIPMENT,
    SYS_DATE
FROM DW_MES_LOT_V
WHERE LOTID LIKE 'GA26011%'  -- 工單篩選
ORDER BY WORKCENTERSEQUENCE;
```

#### 與其他表的關聯

| 關聯表 | 關聯欄位 | 用途 |
|--------|---------|------|
| DW_MES_CONTAINER | CONTAINERID | 取得更詳細的容器資訊 |
| DW_MES_LOTWIPHISTORY | CONTAINERID | 查詢批次流轉歷史 |
| DW_MES_HOLDRELEASEHISTORY | CONTAINERID | 查詢 Hold/Release 歷史 |

#### 重要注意事項

⚠️ **資料更新頻率**: 每 5 分鐘從 DWH 同步，查詢時注意 `SYS_DATE` 確認數據新鮮度

⚠️ **DUMMY 批次過濾**: 生產報表應排除 `OWNER IN ('DUMMY')` 的測試批次

⚠️ **設備欄位選擇**: 使用 `COALESCE(EQUIPMENTNAME, EQUIPMENTS)` 處理不同工站的設備資訊

⚠️ **時間欄位**: `UTS` 為 VARCHAR2 格式 'YYYY/MM/DD'，需轉換後才能計算

⚠️ **無資料庫備註**: 此視圖無 Oracle 欄位備註（ALL_COL_COMMENTS 為空），欄位說明請參考本文件

---

### DW_MES_EQUIPMENTSTATUS_WIP_V（設備狀態 + WIP 追蹤視圖）⭐⭐

**表性質**: 即時數據視圖（Real-time View）

**業務定義**: DWH 提供設備資產狀態與 WIP 追蹤資料的即時視圖，透過 DB Link 直接查詢 `PJ_EquipmentStatus_WIP_V@DWDB_MESDB`，屬於真正即時表（非同步快照）。整合設備狀態、維修工單與批次 Track-In 及 Wafer/封裝資訊，適合做設備狀態與當前 WIP 關聯分析。

**數據來源**: `PJ_EquipmentStatus_WIP_V@DWDB_MESDB`（DB Link 連線）

**數據量**: 約 2,631 筆（2026-01-29 查詢）

#### 欄位分類總覽（32 欄位）

| 分類 | 欄位數 | 說明 |
|------|--------|------|
| 設備/資源識別 | 3 | RESOURCEID, EQUIPMENTID, OBJECTCATEGORY |
| 設備狀態 | 2 | EQUIPMENTASSETSSTATUS, EQUIPMENTASSETSSTATUSREASON |
| 維修工單 | 11 | JOBORDER, JOBMODEL, JOBSTAGE, JOBID, JOBSTATUS, CREATEDATE, CREATEUSERNAME, CREATEUSER, SYMPTOMCODE, CAUSECODE, REPAIRCODE |
| WIP/產品 | 7 | RUNCARDLOTID, "Package", PACKAGE_LF, "Function", TYPE, BOP, SPEC |
| Wafer/材料 | 6 | WAFERLOTID, WAFERPN, WAFERLOTID_PREFIX, LFOPTIONID, WIREDESCRIPTION, WAFERMIL |
| Track-In | 3 | LOTTRACKINQTY_PCS, LOTTRACKINTIME, LOTTRACKINEMPLOYEE |

#### 關鍵欄位說明

#### 欄位清單與說明（32 欄位）

| 欄位名 | 類型 | 欄位功能說明 |
|--------|------|--------------|
| `RESOURCEID` | CHAR(16) | 資源/設備資源 ID（資源主檔識別碼） |
| `EQUIPMENTID` | VARCHAR2(40) | 設備編號（機台代號） |
| `OBJECTCATEGORY` | VARCHAR2(40) | 類別/製程分類（如 ASSEMBLY） |
| `EQUIPMENTASSETSSTATUS` | VARCHAR2(40) | 設備資產狀態（如 PRD、IDLE） |
| `EQUIPMENTASSETSSTATUSREASON` | VARCHAR2(40) | 設備狀態原因/說明（如 Production RUN） |
| `JOBORDER` | VARCHAR2(40) | 維修工單號 |
| `JOBMODEL` | VARCHAR2(40) | 維修工單機型/型號 |
| `JOBSTAGE` | VARCHAR2(40) | 維修工單階段 |
| `JOBID` | CHAR(16) | 維修工單內部 ID |
| `JOBSTATUS` | VARCHAR2(40) | 維修工單狀態 |
| `CREATEDATE` | DATE | 工單建立時間 |
| `CREATEUSERNAME` | VARCHAR2(40) | 建立者帳號 |
| `CREATEUSER` | VARCHAR2(255) | 建立者姓名/顯示名稱 |
| `SYMPTOMCODE` | VARCHAR2(40) | 維修症狀代碼 |
| `CAUSECODE` | VARCHAR2(40) | 故障原因代碼 |
| `REPAIRCODE` | VARCHAR2(40) | 維修處置代碼 |
| `RUNCARDLOTID` | VARCHAR2(40) | 批次號（Run card lot id） |
| `"Package"` | VARCHAR2(40) | 封裝型號（需雙引號保留大小寫） |
| `PACKAGE_LF` | VARCHAR2(4000) | 封裝/Leadframe 類型或描述 |
| `"Function"` | VARCHAR2(40) | 產品功能分類（需雙引號保留大小寫） |
| `TYPE` | VARCHAR2(40) | 產品型號 |
| `BOP` | VARCHAR2(40) | BOP 代碼 |
| `WAFERLOTID` | VARCHAR2(40) | Wafer Lot 編號 |
| `WAFERPN` | VARCHAR2(40) | Wafer 料號 |
| `WAFERLOTID_PREFIX` | VARCHAR2(160) | Wafer Lot 前綴 |
| `SPEC` | VARCHAR2(40) | 製程/工序規格 |
| `LFOPTIONID` | VARCHAR2(4000) | Leadframe Option |
| `WIREDESCRIPTION` | VARCHAR2(4000) | Wire 描述 |
| `WAFERMIL` | VARCHAR2(3062) | Wafer 規格/厚度 |
| `LOTTRACKINQTY_PCS` | NUMBER | Track-In 數量（PCS） |
| `LOTTRACKINTIME` | DATE | Track-In 時間 |
| `LOTTRACKINEMPLOYEE` | VARCHAR2(255) | Track-In 人員 |

##### 設備狀態欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `EQUIPMENTASSETSSTATUS` | VARCHAR2(40) | 設備資產狀態 | `PRD` |
| `EQUIPMENTASSETSSTATUSREASON` | VARCHAR2(40) | 狀態原因 | `Production RUN` |
| `OBJECTCATEGORY` | VARCHAR2(40) | 類別/製程分類 | `ASSEMBLY` |

##### 批次與產品欄位

| 欄位名 | 類型 | 說明 | 範例值 |
|--------|------|------|--------|
| `RUNCARDLOTID` | VARCHAR2(40) | 批次號（Run card lot id） | `GA26011480-A00-006` |
| `"Package"` | VARCHAR2(40) | 封裝型號 | `DFN2510-10L` |
| `"Function"` | VARCHAR2(40) | 產品功能分類 | `TVS/ESD` |
| `TYPE` | VARCHAR2(40) | 產品型號 | `PE1605M4AQ` |
| `BOP` | VARCHAR2(40) | BOP 代碼 | `ECA08` |
| `SPEC` | VARCHAR2(40) | 工序規格 | `元件切割` |

##### Track-In 與 Wafer 欄位

| 欄位名 | 類型 | 說明 |
|--------|------|------|
| `LOTTRACKINQTY_PCS` | NUMBER | Track-In 數量（PCS） |
| `LOTTRACKINTIME` | DATE | Track-In 時間 |
| `LOTTRACKINEMPLOYEE` | VARCHAR2(255) | Track-In 人員 |
| `WAFERLOTID` | VARCHAR2(40) | Wafer Lot |
| `WAFERPN` | VARCHAR2(40) | Wafer 料號 |
| `WAFERLOTID_PREFIX` | VARCHAR2(160) | Wafer Lot 前綴 |
| `LFOPTIONID` | VARCHAR2(4000) | Leadframe Option |
| `WIREDESCRIPTION` | VARCHAR2(4000) | Wire 描述 |
| `WAFERMIL` | VARCHAR2(3062) | Wafer 厚度/規格 |

#### 查詢策略

**1. 設備狀態分布**
```sql
SELECT
    OBJECTCATEGORY,
    EQUIPMENTASSETSSTATUS,
    EQUIPMENTASSETSSTATUSREASON,
    COUNT(*) as EQUIPMENT_COUNT
FROM DW_MES_EQUIPMENTSTATUS_WIP_V
GROUP BY OBJECTCATEGORY, EQUIPMENTASSETSSTATUS, EQUIPMENTASSETSSTATUSREASON
ORDER BY OBJECTCATEGORY, EQUIPMENT_COUNT DESC;
```

**2. 設備對應 WIP 批次（含 Track-In）**
```sql
SELECT
    EQUIPMENTID,
    RUNCARDLOTID,
    "Package" as PACKAGE,
    "Function" as FUNCTION,
    TYPE,
    BOP,
    SPEC,
    LOTTRACKINQTY_PCS,
    LOTTRACKINTIME
FROM DW_MES_EQUIPMENTSTATUS_WIP_V
WHERE RUNCARDLOTID IS NOT NULL
ORDER BY LOTTRACKINTIME DESC;
```

**3. 維修工單清單**
```sql
SELECT
    EQUIPMENTID,
    JOBORDER,
    JOBMODEL,
    JOBSTAGE,
    JOBSTATUS,
    CREATEDATE,
    SYMPTOMCODE,
    CAUSECODE,
    REPAIRCODE
FROM DW_MES_EQUIPMENTSTATUS_WIP_V
WHERE JOBORDER IS NOT NULL
ORDER BY CREATEDATE DESC;
```

**4. Wafer/材料分布**
```sql
SELECT
    WAFERPN,
    WAFERLOTID_PREFIX,
    COUNT(*) as LOT_COUNT
FROM DW_MES_EQUIPMENTSTATUS_WIP_V
WHERE WAFERPN IS NOT NULL
GROUP BY WAFERPN, WAFERLOTID_PREFIX
ORDER BY LOT_COUNT DESC;
```

#### 與其他表的關聯

| 關聯表 | 關聯欄位 | 用途 |
|--------|---------|------|
| DW_MES_LOT_V | RUNCARDLOTID ↔ LOTID | 對照批次狀態/工站資訊 |
| DW_MES_WIP | RUNCARDLOTID ↔ CONTAINERNAME | 取得批次現況與工單資訊 |
| DW_MES_RESOURCE | EQUIPMENTID / RESOURCEID | 取得設備主檔/資源資訊 |

#### 重要注意事項

⚠️ **資料更新頻率**: DB Link 即時查詢，查詢時可搭配 `LOTTRACKINTIME` 判斷新鮮度

⚠️ **欄位大小寫**: `"Package"`、`"Function"` 為**引用欄位**，查詢需使用雙引號保留大小寫

⚠️ **欄位空值**: 維修工單與 Wafer/材料欄位常為 NULL，需依使用情境加條件

⚠️ **無資料庫備註**: 此視圖無 Oracle 欄位備註（ALL_COL_COMMENTS 為空），欄位說明請參考本文件

---

### DW_MES_SPEC_WORKCENTER_V（工站/工序對照視圖）⭐

**表性質**: 對照視圖（Mapping View）

**業務定義**: 由 `MES_SPEC`、`MES_OPERATION`、`MES_WORKCENTER` 組合，提供 SPEC 與工站名稱、分組與排序欄位的對照表。可用於統一工站命名與排序規則，補足報表分群需求。

**數據來源**: `MES_SPEC`, `MES_OPERATION`, `MES_WORKCENTER`（DWH 本地表）

**數據量**: 230 筆（2026-01-29 查詢）

#### 欄位說明（9 欄位）

| 欄位名 | 類型 | 說明 |
|--------|------|------|
| `SPEC` | VARCHAR2(40) | SPEC 名稱 |
| `SPECSEQUENCE` | NUMBER | SPEC 順序（PJ_SEQUENCE） |
| `SPEC_ORDER` | VARCHAR2(200) | 排序欄位（SPECSEQUENCE + '_' + SPEC） |
| `WORK_CENTER` | VARCHAR2(100) | 工站名稱 |
| `WORK_CENTER_SEQUENCE` | VARCHAR2(40) | 工站順序碼（取自 WORKCENTER.Description） |
| `WORK_CENTER_GROUP` | VARCHAR2(100) | 工站分組名稱（依規則合併，如焊接/成型/電鍍） |
| `WORKCENTERSEQUENCE_GROUP` | VARCHAR2(40) | 工站群組順序碼（依規則統一） |
| `WORKCENTERGROUP_ORDER` | VARCHAR2(200) | 群組排序欄位（序號 + '_' + 群組名） |
| `WORK_CENTER_SHORT` | VARCHAR2(40) | 工站簡稱（如 DB/WB/Mold） |

#### 查詢策略

**1. SPEC 對應工站分組**
```sql
SELECT
    SPEC,
    WORK_CENTER,
    WORK_CENTER_GROUP,
    WORK_CENTER_SHORT,
    WORKCENTERSEQUENCE_GROUP
FROM DWH.DW_MES_SPEC_WORKCENTER_V
ORDER BY WORKCENTERSEQUENCE_GROUP, SPEC;
```

**2. 與 WIP 視圖對照（補足工站分組）**
```sql
SELECT
    l.LOTID,
    l.SPECNAME,
    l.WORKCENTERNAME,
    s.WORK_CENTER_GROUP,
    s.WORK_CENTER_SHORT
FROM DWH.DW_MES_LOT_V l
LEFT JOIN DWH.DW_MES_SPEC_WORKCENTER_V s
  ON l.SPECNAME = s.SPEC
ORDER BY l.WORKCENTERSEQUENCE_GROUP, l.LOTID;
```

#### 重要注意事項

⚠️ **分組規則**: `WORK_CENTER_GROUP` 與 `WORKCENTERSEQUENCE_GROUP` 由 CASE 規則產生，若工站命名異動需同步檢查

---

## 現況快照表分析

### 1. DW_MES_WIP（在制品表）⭐⭐⭐

**表性質**: 現況快照表（含歷史累積）

**業務定義**: 存儲在制品（WIP）的現況資料，但實際包含歷史累積，需搭配時間條件（如 `TXNDATE`）限制查詢範圍

#### 關鍵時間欄位

| 欄位名 | 用途 | 查詢建議 |
|--------|------|---------|
| `MOVEINTIMESTAMP` | 批次移入當前工序的時間 | 計算在站時間 (SYSDATE - MOVEINTIMESTAMP) |
| `ORIGINALSTARTDATE` | 批次原始開始生產日期 | 計算生產週期 (SYSDATE - ORIGINALSTARTDATE) |
| `EXPECTEDENDDATE` | 預計完成日期 | 監控交期風險 |
| `TXNDATE` | 資料最後更新時間 | 數據同步監控用 |
| `HOLDTIME` | 暫停時間 | Hold批次的暫停時間點 |
| `COMMENT_DATE` | 備註更新時間 | 追蹤最後異動時間 |

#### 關鍵業務欄位

**數量相關**
- `QTY` / `QTY2`: 當前數量（主/輔單位）
- `MOVEINQTY` / `MOVEINQTY2`: 移入數量
- `ORIGINALQTY` / `ORIGINALQTY2`: 原始開始數量
- `WOQTY`: 工單總數量

**狀態與位置**
- `STATUS`: 批次狀態碼（數值）
- `LOCATIONNAME`: 當前所在位置
- `WORKFLOWSTEPNAME`: 當前工序步驟名稱
- `WORKCENTERNAME`: 當前工作中心

**Hold相關**
- `CURRENTHOLDCOUNT`: 當前Hold數量
- `HOLDREASONID` / `HOLDREASONNAME`: Hold原因
- `HOLDLOCATIONNAME`: Hold所在位置
- `HOLDEMP`: Hold操作人員
- `HOLDCOMMENT_FUTURE`: Hold備註（FutureHold）

**產品與工單**
- `CONTAINERNAME`: 批次號（LOT號）
- `MFGORDERNAME`: 工單號
- `PRODUCTNAME`: 產品名稱
- `PRODUCTLINENAME`: 產品線
- `SPECNAME`: 當前站點規格

**生產信息**
- `DATECODE`: 生產週期代碼
- `FIRSTNAME`: 首片批號
- `WAFERLOT` / `WAFERNAME`: Wafer資訊（3個欄位合併）
- `LEADFRAMENAME` / `LEADFRAMEOPTION`: 框架資訊
- `CONSUMEFACTOR`: 消耗因子（CF值）

#### 查詢策略

**1. 查詢在站時間過長的批次（停滯分析）**
```sql
SELECT
    CONTAINERNAME,
    PRODUCTNAME,
    WORKFLOWSTEPNAME,
    MOVEINTIMESTAMP,
    ROUND((SYSDATE - MOVEINTIMESTAMP) * 24, 2) as HOURS_IN_STATION
FROM DW_MES_WIP
WHERE STATUS NOT IN (8, 128)  -- 排除已完成或取消
  AND (SYSDATE - MOVEINTIMESTAMP) > 2  -- 在站超過2天
ORDER BY HOURS_IN_STATION DESC;
```

**2. 查詢Hold批次清單**
```sql
SELECT
    CONTAINERNAME,
    PRODUCTNAME,
    HOLDREASONNAME,
    HOLDEMP,
    HOLDTIME,
    HOLDLOCATIONNAME,
    CURRENTHOLDCOUNT
FROM DW_MES_WIP
WHERE CURRENTHOLDCOUNT > 0
  AND STATUS NOT IN (8, 128)
ORDER BY HOLDTIME;
```

**3. 查詢在制品數量統計（按產品線）**
```sql
SELECT
    PRODUCTLINENAME,
    COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY,
    SUM(CASE WHEN CURRENTHOLDCOUNT > 0 THEN 1 ELSE 0 END) as HOLD_LOT_COUNT
FROM DW_MES_WIP
WHERE STATUS NOT IN (8, 128)
GROUP BY PRODUCTLINENAME
ORDER BY LOT_COUNT DESC;
```

**4. 工單進度查詢**
```sql
SELECT
    MFGORDERNAME,
    PRODUCTNAME,
    WOQTY as WO_TOTAL_QTY,
    COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
    SUM(QTY) as CURRENT_QTY,
    MIN(MOVEINTIMESTAMP) as EARLIEST_MOVEIN,
    MAX(MOVEINTIMESTAMP) as LATEST_MOVEIN
FROM DW_MES_WIP
WHERE MFGORDERNAME = 'WO12345'  -- 替換為實際工單號
  AND STATUS NOT IN (8, 128)
GROUP BY MFGORDERNAME, PRODUCTNAME, WOQTY;
```

---

### 2. DW_MES_RESOURCE（資源主表）

**表性質**: 現況快照表（主檔表）

**業務定義**: 存儲所有生產資源（設備、工位）的基本信息和配置

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `CREATIONDATE` | 資源創建日期 |
| `LASTCHANGEDATE` | 最後修改日期 |

#### 關鍵業務欄位

**基本信息**
- `RESOURCEID` / `RESOURCENAME`: 資源唯一標識與名稱
- `OBJECTCATEGORY` / `OBJECTTYPE`: 資源分類（設備/工位等）
- `DESCRIPTION`: 資源描述
- `EQUIPMENTTYPE`: 設備類型

**位置與歸屬**
- `LOCATIONID` / `LOCATIONNAME`: 所在位置
- `WORKCENTERNAME`: 所屬工作中心
- `RESOURCEFAMILYNAME`: 資源家族
- `PJ_DEPARTMENT`: 所屬部門

**設備狀態與能力**
- `PJ_ASSETSSTATUS`: 資產狀態
- `MAXLOTS`: 最大批次容量
- `MAXUNITS`: 最大單元容量
- `MULTILOTSFLAG`: 是否支持多批次

**設備屬性標記（2025-12-17新增）**
- `PJ_ISPRODUCTION`: 是否為生產設備
- `PJ_ISKEY`: 是否為關鍵設備
- `PJ_ISMONITOR`: 是否為監控設備

**供應商信息**
- `VENDORID` / `VENDORNAME`: 供應商
- `PJ_ERPVENDORID`: ERP供應商代碼
- `VENDORMODEL`: 設備型號
- `VENDORSERIALNUMBER`: 序列號

#### 查詢策略

**1. 查詢關鍵生產設備清單**
```sql
SELECT
    RESOURCENAME,
    WORKCENTERNAME,
    LOCATIONNAME,
    EQUIPMENTTYPE,
    VENDORNAME,
    VENDORMODEL,
    PJ_ASSETSSTATUS
FROM DW_MES_RESOURCE
WHERE PJ_ISPRODUCTION = 1
  AND PJ_ISKEY = 1
  AND OBJECTTYPE = 'Equipment'
ORDER BY WORKCENTERNAME, RESOURCENAME;
```

**2. 查詢設備容量信息**
```sql
SELECT
    RESOURCENAME,
    WORKCENTERNAME,
    MAXLOTS,
    MAXUNITS,
    MULTILOTSFLAG,
    LOTCOUNT as CURRENT_LOT_COUNT
FROM DW_MES_RESOURCE
WHERE OBJECTTYPE = 'Equipment'
  AND MAXLOTS > 0
ORDER BY WORKCENTERNAME;
```

---

### 3. DW_MES_CONTAINER（容器信息表）

**表性質**: 現況快照表

**業務定義**: 存儲生產容器（批次載體）的當前信息和狀態

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `LASTMOVEOUTTIMESTAMP` | 最後移出時間 |
| `MOVEINTIMESTAMP` | 最後移入時間 |
| `FACTORYSTARTDATE` | 工廠開始日期 |
| `ORIGINALSTARTDATE` | 原始開始日期 |
| `PLANNEDSTARTDATE` | 計劃開始日期 |
| `LASTACTIVITYDATE` | 最後活動日期 |
| `LASTCOMPLETIONDATE` | 最後完成日期 |
| `ONHOLDDATE` | Hold日期 |
| `EXPIRATIONDATE` | 過期日期 |
| `UTS` | 更新時間戳 |
| `LAST_SYNC_DATE` | 最後同步日期 |

#### 關鍵業務欄位

**容器標識**
- `CONTAINERID` / `CONTAINERNAME`: 容器唯一標識
- `FIRSTNAME`: 首片資訊

**當前狀態**
- `STATUS`: 狀態碼
- `CURRENTSTATUSID`: 當前狀態ID
- `LOCATIONNAME`: 當前位置
- `WORKFLOWSTEPNAME`: 當前工序
- `SPECNAME`: 當前規格
- `WORKCENTERNAME`: 當前工作中心

**數量信息**
- `QTY` / `QTY2`: 當前數量
- `MOVEINQTY` / `MOVEINQTY2`: 移入數量
- `ORIGINALQTY` / `ORIGINALQTY2`: 原始數量
- `FACTORYSTARTQTY`: 工廠開始數量

**Hold狀態**
- `CURRENTHOLDCOUNT`: 當前Hold計數
- `FUTUREHOLDCOUNT`: FutureHold計數
- `HOLDREASONID` / `HOLDREASONNAME`: Hold原因
- `HOLDLOCATIONNAME`: Hold位置
- `HOLDLOCATIONSTARTTIMESTAMP`: Hold開始時間
- `HOLDLOCATIONDURATION`: Hold持續時間

**工單與產品**
- `MFGORDERID` / `MFGORDERNAME`: 工單
- `PRODUCTID` / `PRODUCTNAME`: 產品
- `PRODUCTLINENAME`: 產品線
- `PROCESSSPECID`: 工藝規格
- `PJ_BOP`: BOP信息
- `PJ_PRODUCEREGION`: 生產區域

**Lead Frame信息**
- `LEADFRAMENAME`: 框架名稱
- `LEADFRAMEDESC`: 框架描述
- `LEADFRAMEOPTION`: 框架選項

#### 查詢策略

**1. 查詢容器完整生命週期**
```sql
SELECT
    CONTAINERNAME,
    FACTORYSTARTDATE,
    FACTORYSTARTQTY,
    CURRENTSTATUSID,
    QTY,
    LASTMOVEOUTTIMESTAMP,
    LASTMOVEOUTUSERNAME,
    ROUND((SYSDATE - FACTORYSTARTDATE), 2) as DAYS_IN_PRODUCTION
FROM DW_MES_CONTAINER
WHERE CONTAINERNAME = 'LOT123456'  -- 替換為實際批號
ORDER BY LASTMOVEOUTTIMESTAMP DESC;
```

**2. 查詢長時間Hold的容器**
```sql
SELECT
    CONTAINERNAME,
    PRODUCTNAME,
    HOLDREASONNAME,
    HOLDLOCATIONSTARTTIMESTAMP,
    HOLDLOCATIONDURATION,
    CURRENTHOLDCOUNT
FROM DW_MES_CONTAINER
WHERE CURRENTHOLDCOUNT > 0
  AND HOLDLOCATIONDURATION > 48  -- Hold超過48小時
ORDER BY HOLDLOCATIONDURATION DESC;
```

---

### 4. DW_MES_JOB（工單表）

**表性質**: 現況快照表

**業務定義**: 存儲維修/維護工單的當前狀態信息

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `CREATEDATE` | 工單創建日期 |
| `EXPECTEDSTARTDATE` | 預計開始日期 |
| `FIRSTCLOCKONDATE` | 首次簽到日期 |
| `LASTCLOCKOFFDATE` | 最後簽退日期 |
| `COMPLETEDATE` | 完成日期 |
| `CANCELDATE` | 取消日期 |

#### 關鍵業務欄位

**工單基本信息**
- `JOBID`: 工單唯一標識
- `JOBORDERNAME`: 工單名稱
- `JOBSTATUS`: 工單狀態
- `JOBMODELNAME`: 工單模型
- `STAGENAME`: 階段名稱
- `STAGESEQUENCE`: 階段順序

**資源與容器**
- `RESOURCEID` / `RESOURCENAME`: 關聯資源（設備）
- `CONTAINERIDS` / `CONTAINERNAMES`: 關聯容器（批次）
- `PARTREQUESTORDERNAME`: 物料請求訂單

**維修信息**
- `SYMPTOMCODENAME`: 症狀代碼
- `CAUSECODENAME`: 原因代碼
- `REPAIRCODENAME`: 維修代碼
- `PJ_SYMPTOMCODE2NAME`: 症狀代碼2
- `PJ_CAUSECODE2NAME`: 原因代碼2
- `PJ_REPAIRCODE2NAME`: 維修代碼2

**工單統計**
- `ACKNOWLEDGECOUNT`: 確認計數
- `ASSIGNCOUNT`: 分配計數
- `CLOCKONCOUNT`: 簽到計數
- `ACTIVECLOCKONCOUNT`: 活動簽到計數
- `ESTIMATEDDURATION`: 預估工時

**操作人員**
- `CREATEUSERID` / `CREATE_EMPNAME` / `CREATE_FULLNAME`: 創建人
- `COMPLETEUSERID` / `COMPLETE_EMPNAME` / `COMPLETE_FULLNAME`: 完成人
- `CANCELUSERID` / `CANCEL_EMPNAME` / `CANCEL_FULLNAME`: 取消人

#### 查詢策略

**1. 查詢設備維修工單統計**
```sql
SELECT
    RESOURCENAME,
    JOBSTATUS,
    COUNT(*) as JOB_COUNT,
    AVG(COMPLETEDATE - CREATEDATE) as AVG_COMPLETION_DAYS
FROM DW_MES_JOB
WHERE CREATEDATE >= TRUNC(SYSDATE) - 30
GROUP BY RESOURCENAME, JOBSTATUS
ORDER BY JOB_COUNT DESC;
```

**2. 查詢未完成工單清單**
```sql
SELECT
    JOBORDERNAME,
    RESOURCENAME,
    JOBSTATUS,
    CREATEDATE,
    EXPECTEDSTARTDATE,
    SYMPTOMCODENAME,
    CREATE_FULLNAME
FROM DW_MES_JOB
WHERE JOBSTATUS NOT IN ('Completed', 'Cancelled')
ORDER BY CREATEDATE;
```

**3. 查詢維修原因分析**
```sql
SELECT
    SYMPTOMCODENAME,
    CAUSECODENAME,
    REPAIRCODENAME,
    COUNT(*) as OCCURRENCE_COUNT
FROM DW_MES_JOB
WHERE COMPLETEDATE >= TRUNC(SYSDATE) - 90
  AND JOBSTATUS = 'Completed'
GROUP BY SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME
ORDER BY OCCURRENCE_COUNT DESC;
```

---

## 歷史累積表分析

### 5. DW_MES_RESOURCESTATUS（資源狀態表）⭐⭐⭐

**表性質**: 歷史累積表（關鍵核心表）

**業務定義**: 記錄設備狀態的每一次變更，用於計算設備稼動率、停機時間等關鍵指標

#### 關鍵時間欄位

| 欄位名 | 用途 | 查詢建議 |
|--------|------|---------|
| `OLDLASTSTATUSCHANGEDATE` | 上一個狀態開始時間 | **狀態持續時間計算起點** |
| `LASTSTATUSCHANGEDATE` | 新狀態開始時間 | **狀態持續時間計算終點** |
| `OLDLASTACTIVITYDATE` | 上次活動日期 | 設備最後活動時間 |
| `TXNDATE` | 交易時間 | 資料同步時間（用於ETL） |

**時間計算公式**:
```sql
狀態持續時間(小時) = (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24
```

#### 關鍵業務欄位

**狀態變更信息**
- `OLDSTATUSNAME` → `NEWSTATUSNAME`: 狀態變更（從→到）
- `OLDREASONNAME` → `NEWREASONNAME`: 原因變更
- `OLDAVAILABILITY` → `AVAILABILITY`: 可用性變更

**可用性標記（AVAILABILITY）**
- `1`: Productive（生產中）
- `2`: Standby（待機）
- `3`: Non-Scheduled（非排程）
- `4`: Unscheduled Down（非計劃停機）
- `5`: Scheduled Down（計劃停機）

**資源信息（來自RESOURCE表）**
- `HISTORYID`: 資源ID（關聯RESOURCEID）
- `DESCRIPTION`: 設備描述
- `RESOURCEFAMILYNAME`: 設備家族
- `WORKCENTERNAME`: 工作中心
- `LOCATIONNAME`: 位置
- `VENDORNAME` / `VENDORMODEL`: 供應商與型號
- `PJ_ASSETSSTATUS`: 資產狀態
- `PJ_DEPARTMENT`: 部門

**工單關聯**
- `JOBID`: 關聯的維修工單ID

**特殊標記**
- `SS_ISDOWNVIAPARENT`: 是否因父設備Down而Down
- `UPDATELASTSTATUSCHANGEDATE` / `OLDUPDATELASTSTATUSCHANGEDATE`: 更新標記

#### 查詢策略

**1. 計算設備稼動率（OEE基礎數據）**
```sql
SELECT
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    TRUNC(OLDLASTSTATUSCHANGEDATE) as DATE_KEY,
    SUM(CASE
        WHEN AVAILABILITY = 1 THEN
            (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24
        ELSE 0
    END) as PRODUCTIVE_HOURS,
    SUM(CASE
        WHEN AVAILABILITY = 2 THEN
            (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24
        ELSE 0
    END) as STANDBY_HOURS,
    SUM(CASE
        WHEN AVAILABILITY = 4 THEN
            (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24
        ELSE 0
    END) as UNSCHEDULED_DOWN_HOURS,
    SUM((LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24) as TOTAL_HOURS
FROM DW_MES_RESOURCESTATUS
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 7
  AND LASTSTATUSCHANGEDATE <= SYSDATE
GROUP BY HISTORYID, WORKCENTERNAME, TRUNC(OLDLASTSTATUSCHANGEDATE)
ORDER BY DATE_KEY DESC, RESOURCE_ID;
```

**2. 查詢設備停機記錄（Down Time分析）**
```sql
SELECT
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    OLDLASTSTATUSCHANGEDATE as DOWN_START,
    LASTSTATUSCHANGEDATE as DOWN_END,
    ROUND((LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24, 2) as DOWN_HOURS,
    NEWSTATUSNAME,
    NEWREASONNAME,
    AVAILABILITY
FROM DW_MES_RESOURCESTATUS
WHERE AVAILABILITY IN (4, 5)  -- Unscheduled Down / Scheduled Down
  AND OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 7
ORDER BY DOWN_HOURS DESC;
```

**3. 查詢設備狀態變更頻率**
```sql
SELECT
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    COUNT(*) as STATUS_CHANGE_COUNT,
    MIN(OLDLASTSTATUSCHANGEDATE) as FIRST_CHANGE,
    MAX(LASTSTATUSCHANGEDATE) as LAST_CHANGE
FROM DW_MES_RESOURCESTATUS
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 1
GROUP BY HISTORYID, WORKCENTERNAME
ORDER BY STATUS_CHANGE_COUNT DESC;
```

**4. 查詢特定時間段設備時間軸**
```sql
SELECT
    OLDLASTSTATUSCHANGEDATE as START_TIME,
    LASTSTATUSCHANGEDATE as END_TIME,
    OLDSTATUSNAME as FROM_STATUS,
    NEWSTATUSNAME as TO_STATUS,
    NEWREASONNAME as REASON,
    ROUND((LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24 * 60, 2) as DURATION_MINUTES
FROM DW_MES_RESOURCESTATUS
WHERE HISTORYID = 'RESOURCE_ID_HERE'  -- 替換為實際設備ID
  AND OLDLASTSTATUSCHANGEDATE >= TO_DATE('2026-01-14 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
  AND LASTSTATUSCHANGEDATE <= TO_DATE('2026-01-14 20:00:00', 'YYYY-MM-DD HH24:MI:SS')
ORDER BY OLDLASTSTATUSCHANGEDATE;
```

#### 重要注意事項

⚠️ **時間範圍必須限制**: 此表有 6500 萬筆資料，查詢時務必加上時間條件

⚠️ **狀態持續時間計算**: 使用 `LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE`

⚠️ **索引使用**: 優先使用 `OLDLASTSTATUSCHANGEDATE` 和 `HISTORYID` 索引

---

### 6. DW_MES_RESOURCESTATUS_SHIFT（資源狀態班次表）⭐⭐⭐

**表性質**: 歷史累積表（彙總表）

**業務定義**: 按班次彙總資源狀態資料，已計算好時長，是生產報表的首選數據源

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `DATADATE` | 資料日期（班次日期） |
| `OLDLASTSTATUSCHANGEDATE` | 狀態開始時間 |
| `LASTSTATUSCHANGEDATE` | 狀態結束時間 |
| `TXNDATE` | 交易時間 |

#### 關鍵業務欄位

**時長計算（已彙總）**
- `HOURS`: **狀態持續時長（小時）** ⭐ 已計算好，直接使用

**班次信息**
- `SN`: 班次序號

**狀態信息（同RESOURCESTATUS）**
- `OLDSTATUSNAME` / `NEWSTATUSNAME`: 狀態變更
- `OLDREASONNAME` / `NEWREASONNAME`: 原因
- `OLDAVAILABILITY` / `AVAILABILITY`: 可用性

**資源信息**
- `HISTORYID`: 資源ID
- `WORKCENTERNAME`: 工作中心
- `RESOURCEFAMILYNAME`: 設備家族
- `LOCATIONNAME`: 位置

**工單關聯**
- `JOBID`: 維修工單ID

#### 查詢策略

**1. 日報表：設備稼動率統計（最佳實踐）**
```sql
SELECT
    DATADATE,
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) as PRODUCTIVE_HOURS,
    SUM(CASE WHEN AVAILABILITY = 2 THEN HOURS ELSE 0 END) as STANDBY_HOURS,
    SUM(CASE WHEN AVAILABILITY = 4 THEN HOURS ELSE 0 END) as DOWN_HOURS,
    SUM(HOURS) as TOTAL_HOURS,
    ROUND(SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) / NULLIF(SUM(HOURS), 0) * 100, 2) as UTILIZATION_PCT
FROM DW_MES_RESOURCESTATUS_SHIFT
WHERE DATADATE >= TRUNC(SYSDATE) - 7
GROUP BY DATADATE, HISTORYID, WORKCENTERNAME
ORDER BY DATADATE DESC, UTILIZATION_PCT DESC;
```

**2. 月報表：設備停機時長排名**
```sql
SELECT
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    NEWREASONNAME as DOWN_REASON,
    SUM(HOURS) as TOTAL_DOWN_HOURS,
    COUNT(*) as DOWN_COUNT
FROM DW_MES_RESOURCESTATUS_SHIFT
WHERE DATADATE >= TRUNC(ADD_MONTHS(SYSDATE, -1), 'MM')
  AND AVAILABILITY IN (4, 5)  -- Down狀態
GROUP BY HISTORYID, WORKCENTERNAME, NEWREASONNAME
ORDER BY TOTAL_DOWN_HOURS DESC;
```

**3. 趨勢分析：設備稼動率趨勢（按日）**
```sql
SELECT
    DATADATE,
    COUNT(DISTINCT HISTORYID) as EQUIPMENT_COUNT,
    SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) as TOTAL_PRODUCTIVE_HOURS,
    SUM(HOURS) as TOTAL_HOURS,
    ROUND(SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) / NULLIF(SUM(HOURS), 0) * 100, 2) as AVG_UTILIZATION_PCT
FROM DW_MES_RESOURCESTATUS_SHIFT
WHERE DATADATE >= TRUNC(SYSDATE) - 30
  AND WORKCENTERNAME = 'WC001'  -- 可選：指定工作中心
GROUP BY DATADATE
ORDER BY DATADATE;
```

#### 優勢與使用建議

✅ **優勢**:
- 已彙總計算好時長（HOURS欄位），無需自行計算
- 數據按DATADATE分區，查詢效率高
- 適合做日報表、月報表

✅ **使用建議**:
- 優先使用此表做報表統計，而非RESOURCESTATUS
- 使用DATADATE作為主要時間篩選條件
- 適合做時間序列分析和趨勢圖表

---

### 7. DW_MES_LOTWIPHISTORY（批次在制品歷史表）⭐⭐⭐

**表性質**: 歷史累積表（核心流程表）

**業務定義**: 記錄批次在每個工序的完整流轉歷史，包含MoveIn/MoveOut和TrackIn/TrackOut信息

#### 關鍵時間欄位

| 欄位名 | 用途 | 業務含義 |
|--------|------|---------|
| `MOVEINTIMESTAMP` | 批次移入工序時間 | 批次到達工序的時間 |
| `MOVEOUTTIMESTAMP` | 批次移出工序時間 | 批次離開工序的時間 |
| `TRACKINTIMESTAMP` | 批次上機時間 | 批次開始在設備上加工 |
| `TRACKOUTTIMESTAMP` | 批次下機時間 | 批次完成加工離開設備 |
| `ORIGINALSTARTDATE` | 原始開始日期 | 批次首次開始生產日期 |
| `LAST_UPDATED_DATE` | 最後更新日期 | 記錄更新時間 |
| `LAST_SYNC_DATE` | 最後同步日期 | 資料同步時間 |

**時間關係**:
```
MoveIn → TrackIn → TrackOut → MoveOut
  ↓        ↓         ↓          ↓
到達工序  上機加工   完成加工    離開工序
```

#### 關鍵業務欄位

**批次標識**
- `WIPLOTHISTORYID`: 歷史記錄唯一ID
- `WIPEQUIPMENTHISTORYID`: 設備歷史關聯ID
- `CONTAINERID` / `FINISHEDRUNCARD`: 批次容器ID與完成品號
- `PJ_WORKORDER`: 工單號

**數量追蹤（4組數量）**
- `MOVEINQTY` / `MOVEINQTY2`: 移入數量（主/輔單位）
- `MOVEOUTQTY` / `MOVEOUTQTY2`: 移出數量
- `TRACKINQTY` / `TRACKINQTY2`: 上機數量
- `TRACKOUTQTY` / `TRACKOUTQTY2`: 下機數量

**工序與設備**
- `WORKCENTERID` / `WORKCENTERNAME`: 工作中心
- `SPECID` / `SPECNAME`: 工序規格
- `EQUIPMENTID` / `EQUIPMENTNAME`: 加工設備
- `WORKFLOWNAME`: 工藝流程名稱
- `PROCESSSPECNAME`: 工藝規格
- `PROCESSTYPENAME`: 工序類型

**產品信息**
- `PRODUCTNAME`: 產品名稱
- `DESCRIPTION`: 產品描述
- `DATECODE`: 生產週期代碼
- `PACKAGE_LF`: 封裝Lead Frame信息

**Wafer信息**
- `PJ_WAFERID1` / `PJ_WAFERID2` / `PJ_WAFERID3`: Wafer ID

**人員信息**
- `TRACKINEMPLOYEENAME` / `TRACKINEMPZONE`: 上機人員與區域
- `TRACKOUTEMPLOYEENAME` / `TRACKOUTEMPZONE`: 下機人員與區域

**其他**
- `FLAGNAME`: 標記名稱
- `CARRIERNAME`: 載具名稱
- `WIPTRACKINGGROUPKEYID`: WIP追蹤群組Key

#### 查詢策略

**1. 批次完整流轉軌跡查詢**
```sql
SELECT
    WIPLOTHISTORYID,
    WORKCENTERNAME,
    SPECNAME,
    EQUIPMENTNAME,
    MOVEINTIMESTAMP,
    TRACKINTIMESTAMP,
    TRACKOUTTIMESTAMP,
    MOVEOUTTIMESTAMP,
    MOVEINQTY,
    MOVEOUTQTY,
    ROUND((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24, 2) as PROCESS_HOURS,
    ROUND((MOVEOUTTIMESTAMP - MOVEINTIMESTAMP) * 24, 2) as STATION_HOURS,
    TRACKINEMPLOYEENAME,
    TRACKOUTEMPLOYEENAME
FROM DW_MES_LOTWIPHISTORY
WHERE CONTAINERID = 'CONTAINER_ID_HERE'  -- 或使用 PJ_WORKORDER = 'WO123'
ORDER BY MOVEINTIMESTAMP;
```

**2. 工序加工時長分析（Cycle Time）**
```sql
SELECT
    WORKCENTERNAME,
    SPECNAME,
    COUNT(*) as LOT_COUNT,
    AVG((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24) as AVG_PROCESS_HOURS,
    MIN((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24) as MIN_PROCESS_HOURS,
    MAX((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24) as MAX_PROCESS_HOURS,
    STDDEV((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24) as STDDEV_HOURS
FROM DW_MES_LOTWIPHISTORY
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 30
  AND TRACKOUTTIMESTAMP IS NOT NULL
GROUP BY WORKCENTERNAME, SPECNAME
ORDER BY AVG_PROCESS_HOURS DESC;
```

**3. 設備產出統計（Throughput）**
```sql
SELECT
    EQUIPMENTNAME,
    WORKCENTERNAME,
    TRUNC(TRACKINTIMESTAMP) as WORK_DATE,
    COUNT(DISTINCT CONTAINERID) as LOT_COUNT,
    SUM(TRACKINQTY) as TOTAL_QTY_IN,
    SUM(TRACKOUTQTY) as TOTAL_QTY_OUT,
    SUM(TRACKOUTQTY - TRACKINQTY) as QTY_LOSS
FROM DW_MES_LOTWIPHISTORY
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 7
  AND EQUIPMENTNAME IS NOT NULL
GROUP BY EQUIPMENTNAME, WORKCENTERNAME, TRUNC(TRACKINTIMESTAMP)
ORDER BY WORK_DATE DESC, TOTAL_QTY_OUT DESC;
```

**4. 工序等待時間分析（Queue Time）**
```sql
SELECT
    WORKCENTERNAME,
    SPECNAME,
    COUNT(*) as LOT_COUNT,
    AVG((TRACKINTIMESTAMP - MOVEINTIMESTAMP) * 24) as AVG_QUEUE_HOURS,
    MAX((TRACKINTIMESTAMP - MOVEINTIMESTAMP) * 24) as MAX_QUEUE_HOURS
FROM DW_MES_LOTWIPHISTORY
WHERE MOVEINTIMESTAMP >= TRUNC(SYSDATE) - 7
  AND TRACKINTIMESTAMP IS NOT NULL
GROUP BY WORKCENTERNAME, SPECNAME
ORDER BY AVG_QUEUE_HOURS DESC;
```

**5. 批次數量損耗追蹤**
```sql
SELECT
    CONTAINERID,
    PJ_WORKORDER,
    WORKCENTERNAME,
    SPECNAME,
    MOVEINQTY,
    MOVEOUTQTY,
    (MOVEINQTY - MOVEOUTQTY) as QTY_LOSS,
    ROUND((MOVEINQTY - MOVEOUTQTY) / NULLIF(MOVEINQTY, 0) * 100, 2) as LOSS_PCT,
    MOVEINTIMESTAMP,
    MOVEOUTTIMESTAMP
FROM DW_MES_LOTWIPHISTORY
WHERE MOVEINTIMESTAMP >= TRUNC(SYSDATE) - 7
  AND (MOVEINQTY - MOVEOUTQTY) > 0  -- 有損耗
ORDER BY QTY_LOSS DESC;
```

#### 重要注意事項

⚠️ **時間範圍必須限制**: 此表有 5300 萬筆資料

⚠️ **時間計算**:
- 加工時間 = `TRACKOUTTIMESTAMP - TRACKINTIMESTAMP`
- 在站時間 = `MOVEOUTTIMESTAMP - MOVEINTIMESTAMP`
- 等待時間 = `TRACKINTIMESTAMP - MOVEINTIMESTAMP`

⚠️ **索引優先使用**: `TRACKINTIMESTAMP`, `MOVEINTIMESTAMP`, `CONTAINERID`, `PJ_WORKORDER`

---

### 8. DW_MES_LOTWIPDATAHISTORY（批次在制品數據歷史表）

**表性質**: 歷史累積表（數據採集表）

**業務定義**: 記錄批次在生產過程中採集的所有參數數據（如測試結果、SPC數據等）

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `TXNTIMESTAMP` | 數據採集時間 |
| `LAST_UPDATED_DATE` | 最後更新日期 |

#### 關鍵業務欄位

**批次與工序**
- `CONTAINERID` / `FINISHEDRUNCARD`: 批次標識
- `PJ_WORKORDER`: 工單號
- `WORKCENTERID` / `WORKCENTERNAME`: 工作中心
- `SPECID` / `SPECNAME`: 工序規格
- `EQUIPMENTID` / `EQUIPMENTNAME`: 設備

**數據內容**
- `WIPDATANAMEID` / `WIPDATANAMENAME`: 數據項名稱
- `WIPDATAVALUE`: 數據值（最長4000字元）
- `PJ_SPCDATARESULT`: SPC數據結果

**關聯信息**
- `WIPLOTHISTORYID`: 關聯LOTWIPHISTORY的ID
- `SERVICENAME`: 服務名稱
- `PROCESSTYPENAME`: 工序類型
- `EMPLOYEENAME`: 採集人員
- `WAFERSCRIBENUMBER`: Wafer刻號

#### 查詢策略

**1. 查詢批次採集的所有數據**
```sql
SELECT
    WIPDATANAMENAME as DATA_NAME,
    WIPDATAVALUE as DATA_VALUE,
    TXNTIMESTAMP,
    WORKCENTERNAME,
    SPECNAME,
    EQUIPMENTNAME,
    EMPLOYEENAME
FROM DW_MES_LOTWIPDATAHISTORY
WHERE CONTAINERID = 'CONTAINER_ID_HERE'
ORDER BY TXNTIMESTAMP, WIPDATANAMENAME;
```

**2. 查詢特定參數的歷史趨勢**
```sql
SELECT
    CONTAINERID,
    TXNTIMESTAMP,
    WIPDATAVALUE,
    EQUIPMENTNAME,
    PJ_SPCDATARESULT
FROM DW_MES_LOTWIPDATAHISTORY
WHERE WIPDATANAMENAME = 'PARAMETER_NAME'  -- 如: 'Temperature'
  AND TXNTIMESTAMP >= TRUNC(SYSDATE) - 7
ORDER BY TXNTIMESTAMP;
```

**3. SPC異常數據查詢**
```sql
SELECT
    CONTAINERID,
    PJ_WORKORDER,
    WORKCENTERNAME,
    SPECNAME,
    WIPDATANAMENAME,
    WIPDATAVALUE,
    PJ_SPCDATARESULT,
    TXNTIMESTAMP
FROM DW_MES_LOTWIPDATAHISTORY
WHERE PJ_SPCDATARESULT IN ('Out of Control', 'Warning')  -- 根據實際值調整
  AND TXNTIMESTAMP >= TRUNC(SYSDATE) - 7
ORDER BY TXNTIMESTAMP DESC;
```

#### 重要注意事項

⚠️ **大數據量表**: 約 7,796 萬筆資料，務必加時間條件

⚠️ **與LOTWIPHISTORY關聯**: 通過`WIPLOTHISTORYID`關聯

⚠️ **數據值為文字**: `WIPDATAVALUE`是VARCHAR2，數值運算需轉換

---

### 9. DW_MES_HM_LOTMOVEOUT（批次移出表）⭐⭐

**表性質**: 歷史累積表（事件表）

**業務定義**: 記錄每次批次從工序移出（MoveOut）的事件，是生產流程追蹤的重要數據源

#### 關鍵時間欄位

| 欄位名 | 用途 |
|--------|------|
| `TXNDATE` | 交易時間（MoveOut時間） |
| `MOVEINTIMESTAMP` | 移入時間 |
| `LASTMOVEOUTTIMESTAMP` | 最後移出時間 |
| `SYSTEMDATE` | 系統時間 |
| `MFGDATE` | 製造日期 |

#### 關鍵業務欄位

**交易信息**
- `HISTORYID` / `HISTORYMAINLINEID`: 歷史記錄ID
- `HISTORYSUMMARYID`: 歷史匯總ID
- `TXNID`: 交易ID
- `TXNTYPE`: 交易類型

**批次與容器**
- `CONTAINERID` / `CONTAINERNAME`: 批次容器
- `CARRIERID` / `CARRIERNAME`: 載具

**狀態變更（From → To）**
- `FROMSPECID` / `FROMSPECNAME`: 來源工序
- `SPECID` / `SPECNAME`: 目標工序
- `FROMWORKCENTER` / `WORKCENTER`: 工作中心變更
- `FROMSTATUS` / `STATUS`: 狀態變更
- `FROMQTY` / `QTY`: 數量變更
- `FROMQTY2` / `QTY2`: 數量2變更

**數量信息**
- `MOVEINQTY` / `MOVEINQTY2`: 移入數量
- `FROMUOMNAME` / `UOMNAME`: 單位

**設備與資源**
- `RESOURCEID` / `RESOURCENAME`: 資源（設備）
- `RESOURCEOBJECTCATEGORY` / `RESOURCEOBJECTTYPE`: 資源類型
- `RESOURCESTATUSCODEID` / `RESOURCESTATUSREASONID`: 資源狀態

**產品與工單**
- `PRODUCTID` / `PRODUCTNAME`: 產品
- `OWNERID` / `OWNERNAME`: 所有者
- `WORKFLOWNAME`: 工藝流程

**人員信息**
- `EMPLOYEEID` / `EMPLOYEENAME`: 操作人員
- `USERID` / `USERNAME`: 用戶
- `USERFULLNAME`: 用戶全名
- `EMPZONE`: 人員區域

**班次與時間**
- `SHIFTNAME`: 班次
- `COMPUTERNAME`: 電腦名稱
- `SERVERNAME`: 伺服器名稱

**MES CDC信息**
- `CDONAME`: CDO名稱
- `CDOTXNSEQUENCE`: CDO交易序號
- `CALLBYCDONAME`: 調用CDO名稱

**其他**
- `COMMENTS`: 備註
- `CONSUMEFACTOR`: 消耗因子
- `WAFERPRODUCT`: Wafer產品

#### 查詢策略

**1. 批次流轉記錄查詢**
```sql
SELECT
    TXNDATE,
    CONTAINERNAME,
    FROMSPECNAME as FROM_STEP,
    SPECNAME as TO_STEP,
    FROMQTY,
    QTY,
    (FROMQTY - QTY) as QTY_LOSS,
    RESOURCENAME,
    EMPLOYEENAME,
    SHIFTNAME
FROM DW_MES_HM_LOTMOVEOUT
WHERE CONTAINERID = 'CONTAINER_ID_HERE'
ORDER BY TXNDATE;
```

**2. 每日產出統計**
```sql
SELECT
    TRUNC(TXNDATE) as WORK_DATE,
    SPECNAME,
    WORKCENTER,
    COUNT(DISTINCT CONTAINERID) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY,
    COUNT(DISTINCT RESOURCENAME) as EQUIPMENT_COUNT
FROM DW_MES_HM_LOTMOVEOUT
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
GROUP BY TRUNC(TXNDATE), SPECNAME, WORKCENTER
ORDER BY WORK_DATE DESC, TOTAL_QTY DESC;
```

**3. 人員產出績效**
```sql
SELECT
    EMPLOYEENAME,
    EMPZONE,
    COUNT(DISTINCT CONTAINERID) as LOT_COUNT,
    SUM(QTY) as TOTAL_OUTPUT,
    COUNT(*) as OPERATION_COUNT
FROM DW_MES_HM_LOTMOVEOUT
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
GROUP BY EMPLOYEENAME, EMPZONE
ORDER BY TOTAL_OUTPUT DESC;
```

#### 重要注意事項

⚠️ **大數據量**: 約 4,865 萬筆，必須加時間條件

⚠️ **與LOTWIPHISTORY差異**:
- HM_LOTMOVEOUT: 只記錄MoveOut事件
- LOTWIPHISTORY: 記錄完整的MoveIn/TrackIn/TrackOut/MoveOut

---

### 10. 其他歷史表簡要說明

#### DW_MES_LOTREJECTHISTORY（批次拒絕歷史表）
- **用途**: 記錄批次報廢、損耗的歷史
- **關鍵欄位**:
  - `REJECTQTY`: 拒絕數量
  - `LOSSREASONNAME`: 損耗原因
  - `REJECTCATEGORYNAME`: 拒絕類別
- **查詢場景**: 良率分析、損耗原因分析

#### DW_MES_LOTMATERIALSHISTORY（批次物料歷史表）
- **用途**: 記錄批次使用物料的歷史
- **關鍵欄位**:
  - `MATERIALPARTNAME`: 物料名稱
  - `MATERIALLOTNAME`: 物料批號
  - `QTYCONSUMED`: 消耗數量
  - `CONSUMEFACTOR`: 消耗因子
- **查詢場景**: 物料追溯、消耗分析

#### DW_MES_HOLDRELEASEHISTORY（暫停/釋放歷史表）
- **用途**: 記錄批次Hold和Release的完整歷史
- **關鍵欄位**:
  - `HOLDTXNDATE` / `RELEASETXNDATE`: Hold/Release時間
  - `HOLDREASONNAME` / `RELEASEREASONNAME`: Hold/Release原因
  - `HOLDEMP` / `RELEASEEMP`: 操作人員
- **查詢場景**: Hold原因分析、Hold時長統計

#### DW_MES_JOBTXNHISTORY（維修工單交易歷史表）
- **用途**: 記錄維修工單的狀態變更歷史
- **關鍵欄位**:
  - `FROMJOBSTATUS` / `JOBSTATUS`: 狀態變更
  - `TXNDATE`: 交易時間
- **查詢場景**: 維修工單流程追蹤

#### DW_MES_MAINTENANCE（維護記錄表）
- **用途**: 記錄設備維護保養的詳細記錄
- **關鍵欄位**:
  - `MAINTENANCEREQNAME`: 維護需求名稱
  - `THRUPUTQTY`: 產出數量
  - `DATAVALUE`: 維護數據值
- **查詢場景**: 設備保養追蹤、維護計劃執行狀況

---

## 表間關聯關係圖

### 核心實體關係

```
┌─────────────────────────────────────────────────────────────────┐
│                        核心實體關係圖                              │
└─────────────────────────────────────────────────────────────────┘

1. 在制品流轉主線（核心業務流程）

   DW_MES_WIP (現況快照，含歷史累積)
        ↓ CONTAINERID
   DW_MES_CONTAINER (容器主檔)
        ↓ CONTAINERID
   DW_MES_LOTWIPHISTORY (流轉歷史)
        ↓ WIPLOTHISTORYID
   DW_MES_LOTWIPDATAHISTORY (數據採集歷史)

   DW_MES_LOTWIPHISTORY
        ↓ CONTAINERID
   DW_MES_HM_LOTMOVEOUT (移出事件)


2. 資源狀態主線（設備管理）

   DW_MES_RESOURCE (資源主檔)
        ↓ RESOURCEID
   DW_MES_RESOURCESTATUS (狀態變更歷史)
        ↓ HISTORYID (= RESOURCEID)
   DW_MES_RESOURCESTATUS_SHIFT (班次彙總)


3. 工單維修主線（維修管理）

   DW_MES_JOB (工單現況)
        ↓ JOBID
   DW_MES_JOBTXNHISTORY (維修工單交易歷史)

   DW_MES_JOB
        ↓ RESOURCEID
   DW_MES_RESOURCE (關聯設備)

   DW_MES_JOB
        ↓ JOBID
   DW_MES_PARTREQUESTORDER (物料請求)


4. 批次異常處理主線

   DW_MES_WIP / DW_MES_CONTAINER
        ↓ CONTAINERID
   DW_MES_HOLDRELEASEHISTORY (Hold/Release歷史)

   DW_MES_LOTWIPHISTORY
        ↓ HISTORYMAINLINEID
   DW_MES_LOTREJECTHISTORY (拒絕歷史)


5. 物料消耗主線

   DW_MES_LOTWIPHISTORY
        ↓ CONTAINERID
   DW_MES_LOTMATERIALSHISTORY (物料消耗歷史)


6. 設備維護主線

   DW_MES_RESOURCE
        ↓ RESOURCEID
   DW_MES_MAINTENANCE (維護記錄)
```

### 詳細關聯鍵對照表

| 主表 | 關聯表 | 關聯欄位 | 關聯類型 | 說明 |
|------|--------|---------|---------|------|
| **DW_MES_WIP** | DW_MES_CONTAINER | CONTAINERID | 1:1 | 在制品關聯容器 |
| **DW_MES_CONTAINER** | DW_MES_LOTWIPHISTORY | CONTAINERID | 1:N | 容器的流轉歷史 |
| **DW_MES_LOTWIPHISTORY** | DW_MES_LOTWIPDATAHISTORY | WIPLOTHISTORYID | 1:N | 流轉記錄的數據採集 |
| **DW_MES_LOTWIPHISTORY** | DW_MES_HM_LOTMOVEOUT | CONTAINERID + HISTORYMAINLINEID | 1:N | 流轉的移出事件 |
| **DW_MES_LOTWIPHISTORY** | DW_MES_LOTREJECTHISTORY | HISTORYMAINLINEID | 1:N | 流轉的拒絕記錄 |
| **DW_MES_LOTWIPHISTORY** | DW_MES_LOTMATERIALSHISTORY | CONTAINERID | 1:N | 流轉的物料消耗 |
| **DW_MES_WIP** | DW_MES_HOLDRELEASEHISTORY | CONTAINERID | 1:N | 在制品的Hold歷史 |
| **DW_MES_RESOURCE** | DW_MES_RESOURCESTATUS | RESOURCEID = HISTORYID | 1:N | 資源的狀態歷史 |
| **DW_MES_RESOURCE** | DW_MES_RESOURCESTATUS_SHIFT | RESOURCEID = HISTORYID | 1:N | 資源的班次彙總 |
| **DW_MES_RESOURCE** | DW_MES_MAINTENANCE | RESOURCEID | 1:N | 資源的維護記錄 |
| **DW_MES_RESOURCE** | DW_MES_PARTREQUESTORDER | RESOURCEID | 1:N | 資源的維修用料請求 |
| **DW_MES_RESOURCE** | DW_MES_HM_LOTMOVEOUT | RESOURCEID | 1:N | 資源對應的移出事件 |
| **DW_MES_JOB** | DW_MES_JOBTXNHISTORY | JOBID | 1:N | 工單的交易歷史 |
| **DW_MES_JOB** | DW_MES_RESOURCE | RESOURCEID | N:1 | 工單關聯資源 |
| **DW_MES_JOB** | DW_MES_PARTREQUESTORDER | JOBID | 1:N | 工單的物料請求 |
| **DW_MES_CONTAINER** | DW_MES_PJ_COMBINEDASSYLOTS | CONTAINERID | 1:N | 容器的組合裝配 |

### Reference 備註確認的關聯

以下關聯來自 `MES_Database_Reference.md` 的欄位備註（維護人註記）：

| 表 | 欄位 | 備註 | 可推得關聯/用途 |
|------|------|------|----------------|
| **DW_MES_RESOURCESTATUS** | HISTORYID | RESOURCEID | 關聯 `DW_MES_RESOURCE.RESOURCEID` |
| **DW_MES_RESOURCESTATUS_SHIFT** | HISTORYID | RESOURCEID | 關聯 `DW_MES_RESOURCE.RESOURCEID` |
| **DW_MES_JOB** | PARTREQUESTORDERNAME | DW_MES_PARTREQUESTORDER | 可由 `DW_MES_PARTREQUESTORDER` 取得工單請領資訊 |
| **DW_MES_WIP** | RELEASETIME / RELEASEEMP / RELEASEREASON | DW_MES_HOLDRELEASEHISTORY | WIP 的解除資訊來源於 Hold/Release 歷史 |

### 欄位來源備註（同表內派生）

以下備註顯示欄位來源於同表關鍵欄位（非跨表），建議查詢時以 ID 欄位為主：

| 表 | 欄位 | 備註 |
|------|------|------|
| **DW_MES_CONTAINER** | MFGORDERNAME / PJ_BOP / PJ_PRODUCEREGION / PRODUCTBOMBASEID | MFGORDERID |
| **DW_MES_WIP** | STARTREASONNAME / MFGORDERNAME / FIRSTNAME / OWNERNAME / PRIORITYCODENAME / PRODUCTBOMBASEID / PRODUCTNAME / PRODUCTLINENAME / PJ_BOP / PJ_PRODUCEREGION / PJ_TYPE / PJ_FUNCTION | CONTAINERID |
| **DW_MES_WIP** | WOQTY / WOPLANNEDCOMPLETIONDATE | CONTAINERID -> MFGORDERID |

### 關鍵關聯欄位說明

#### CONTAINERID
- 批次/容器的唯一標識（16位元CHAR）
- 貫穿所有與批次相關的表
- 最重要的關聯欄位

#### RESOURCEID / HISTORYID
- RESOURCE表使用 `RESOURCEID`
- RESOURCESTATUS表使用 `HISTORYID`（實際上等於RESOURCEID）
- 關聯時注意欄位名稱差異

#### HISTORYMAINLINEID
- 歷史記錄的主線ID
- 用於關聯同一批次在不同歷史表的記錄

#### WIPLOTHISTORYID
- LOTWIPHISTORY的主鍵
- LOTWIPDATAHISTORY用此欄位關聯

#### PJ_WORKORDER
- 工單號（業務鍵）
- 部分表使用此欄位追蹤批次

---

## 關鍵業務場景查詢策略

### 場景1: 在制品（WIP）看板

**需求**: 顯示當前所有在制品的狀態、位置、停滯時間

**推薦表**: `DW_MES_WIP`

**查詢邏輯**:
```sql
SELECT
    CONTAINERNAME,
    PRODUCTNAME,
    PRODUCTLINENAME,
    WORKCENTERNAME,
    WORKFLOWSTEPNAME,
    QTY,
    MOVEINTIMESTAMP,
    ROUND((SYSDATE - MOVEINTIMESTAMP) * 24, 2) as HOURS_IN_STATION,
    CURRENTHOLDCOUNT,
    HOLDREASONNAME,
    LOCATIONNAME
FROM DW_MES_WIP
WHERE STATUS NOT IN (8, 128)  -- 排除已完成或取消
ORDER BY HOURS_IN_STATION DESC;
```

**效能優化**:
- 使用索引: `TXNDATE`, `CONTAINERNAME`
- 建議增加工作中心或產品線篩選

---

### 場景2: 設備稼動率（OEE）報表

**需求**: 計算每日設備的稼動率、停機時長

**推薦表**: `DW_MES_RESOURCESTATUS_SHIFT`（首選，已彙總）

**查詢邏輯**:
```sql
SELECT
    DATADATE,
    HISTORYID as RESOURCE_ID,
    WORKCENTERNAME,
    -- 生產時間
    SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) as PRODUCTIVE_HOURS,
    -- 待機時間
    SUM(CASE WHEN AVAILABILITY = 2 THEN HOURS ELSE 0 END) as STANDBY_HOURS,
    -- 非計劃停機
    SUM(CASE WHEN AVAILABILITY = 4 THEN HOURS ELSE 0 END) as UNSCHEDULED_DOWN_HOURS,
    -- 計劃停機
    SUM(CASE WHEN AVAILABILITY = 5 THEN HOURS ELSE 0 END) as SCHEDULED_DOWN_HOURS,
    -- 總時間
    SUM(HOURS) as TOTAL_HOURS,
    -- 稼動率
    ROUND(SUM(CASE WHEN AVAILABILITY = 1 THEN HOURS ELSE 0 END) / NULLIF(SUM(HOURS), 0) * 100, 2) as UTILIZATION_PCT
FROM DW_MES_RESOURCESTATUS_SHIFT
WHERE DATADATE >= TRUNC(SYSDATE) - 7
GROUP BY DATADATE, HISTORYID, WORKCENTERNAME
ORDER BY DATADATE DESC, UTILIZATION_PCT DESC;
```

**替代方案**: 若需要更細緻的時間分析，使用 `DW_MES_RESOURCESTATUS`

**效能優化**:
- 優先使用 `DATADATE` 索引
- 班次表比狀態表效率高約10倍

---

### 場景3: 批次生產履歷追溯

**需求**: 追溯某批次的完整生產過程（每個工序的時間、設備、人員）

**推薦表**: `DW_MES_LOTWIPHISTORY`

**查詢邏輯**:
```sql
SELECT
    WIPLOTHISTORYID,
    WORKCENTERNAME,
    SPECNAME,
    EQUIPMENTNAME,
    MOVEINTIMESTAMP,
    TRACKINTIMESTAMP,
    TRACKOUTTIMESTAMP,
    MOVEOUTTIMESTAMP,
    MOVEINQTY,
    MOVEOUTQTY,
    (MOVEINQTY - MOVEOUTQTY) as QTY_LOSS,
    ROUND((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24, 2) as PROCESS_HOURS,
    ROUND((MOVEOUTTIMESTAMP - MOVEINTIMESTAMP) * 24, 2) as STATION_HOURS,
    ROUND((TRACKINTIMESTAMP - MOVEINTIMESTAMP) * 24, 2) as QUEUE_HOURS,
    TRACKINEMPLOYEENAME,
    TRACKOUTEMPLOYEENAME,
    FLAGNAME
FROM DW_MES_LOTWIPHISTORY
WHERE CONTAINERID = 'CONTAINER_ID_HERE'  -- 或使用 PJ_WORKORDER
ORDER BY MOVEINTIMESTAMP;
```

**擴展查詢**: 加入採集數據
```sql
SELECT
    lwh.SPECNAME,
    lwh.EQUIPMENTNAME,
    lwh.TRACKINTIMESTAMP,
    lwd.WIPDATANAMENAME,
    lwd.WIPDATAVALUE,
    lwd.PJ_SPCDATARESULT
FROM DW_MES_LOTWIPHISTORY lwh
LEFT JOIN DW_MES_LOTWIPDATAHISTORY lwd
    ON lwh.WIPLOTHISTORYID = lwd.WIPLOTHISTORYID
WHERE lwh.CONTAINERID = 'CONTAINER_ID_HERE'
ORDER BY lwh.MOVEINTIMESTAMP, lwd.WIPDATANAMENAME;
```

---

### 場景4: 工序Cycle Time分析

**需求**: 分析各工序的平均加工時間、最大/最小時間

**推薦表**: `DW_MES_LOTWIPHISTORY`

**查詢邏輯**:
```sql
SELECT
    WORKCENTERNAME,
    SPECNAME,
    PROCESSTYPENAME,
    COUNT(*) as LOT_COUNT,
    -- 加工時間統計
    ROUND(AVG((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24), 2) as AVG_PROCESS_HOURS,
    ROUND(MIN((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24), 2) as MIN_PROCESS_HOURS,
    ROUND(MAX((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24), 2) as MAX_PROCESS_HOURS,
    ROUND(STDDEV((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24), 2) as STDDEV_HOURS,
    -- 在站時間統計
    ROUND(AVG((MOVEOUTTIMESTAMP - MOVEINTIMESTAMP) * 24), 2) as AVG_STATION_HOURS,
    -- 等待時間統計
    ROUND(AVG((TRACKINTIMESTAMP - MOVEINTIMESTAMP) * 24), 2) as AVG_QUEUE_HOURS
FROM DW_MES_LOTWIPHISTORY
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 30
  AND TRACKOUTTIMESTAMP IS NOT NULL
  AND (TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) > 0  -- 排除異常數據
GROUP BY WORKCENTERNAME, SPECNAME, PROCESSTYPENAME
ORDER BY AVG_PROCESS_HOURS DESC;
```

**瓶頸工序識別**:
```sql
SELECT
    WORKCENTERNAME,
    SPECNAME,
    AVG((MOVEOUTTIMESTAMP - MOVEINTIMESTAMP) * 24) as AVG_STATION_HOURS,
    COUNT(*) as LOT_COUNT
FROM DW_MES_LOTWIPHISTORY
WHERE MOVEINTIMESTAMP >= TRUNC(SYSDATE) - 7
GROUP BY WORKCENTERNAME, SPECNAME
HAVING AVG((MOVEOUTTIMESTAMP - MOVEINTIMESTAMP) * 24) > 24  -- 在站超過24小時
ORDER BY AVG_STATION_HOURS DESC;
```

---

### 場景5: 設備產出與效率分析

**需求**: 統計各設備的產出數量、良率、稼動時間

**推薦表**:
- 產出數量: `DW_MES_LOTWIPHISTORY`
- 良率: `DW_MES_LOTREJECTHISTORY`
- 稼動: `DW_MES_RESOURCESTATUS_SHIFT`

**查詢邏輯（產出）**:
```sql
SELECT
    EQUIPMENTNAME,
    WORKCENTERNAME,
    TRUNC(TRACKINTIMESTAMP) as WORK_DATE,
    COUNT(DISTINCT CONTAINERID) as LOT_COUNT,
    SUM(TRACKINQTY) as TOTAL_INPUT_QTY,
    SUM(TRACKOUTQTY) as TOTAL_OUTPUT_QTY,
    SUM(TRACKINQTY - TRACKOUTQTY) as TOTAL_LOSS_QTY,
    ROUND((1 - SUM(TRACKINQTY - TRACKOUTQTY) / NULLIF(SUM(TRACKINQTY), 0)) * 100, 2) as YIELD_PCT
FROM DW_MES_LOTWIPHISTORY
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 7
  AND EQUIPMENTNAME IS NOT NULL
GROUP BY EQUIPMENTNAME, WORKCENTERNAME, TRUNC(TRACKINTIMESTAMP)
ORDER BY WORK_DATE DESC, TOTAL_OUTPUT_QTY DESC;
```

**整合稼動率查詢**:
```sql
SELECT
    r.HISTORYID as RESOURCE_ID,
    r.WORKCENTERNAME,
    r.DATADATE,
    -- 稼動數據
    SUM(CASE WHEN r.AVAILABILITY = 1 THEN r.HOURS ELSE 0 END) as PRODUCTIVE_HOURS,
    ROUND(SUM(CASE WHEN r.AVAILABILITY = 1 THEN r.HOURS ELSE 0 END) / NULLIF(SUM(r.HOURS), 0) * 100, 2) as UTILIZATION_PCT,
    -- 產出數據
    COUNT(DISTINCT w.CONTAINERID) as LOT_COUNT,
    SUM(w.TRACKOUTQTY) as TOTAL_OUTPUT_QTY
FROM DW_MES_RESOURCESTATUS_SHIFT r
LEFT JOIN DW_MES_LOTWIPHISTORY w
    ON r.HISTORYID = w.EQUIPMENTID
    AND TRUNC(w.TRACKINTIMESTAMP) = r.DATADATE
WHERE r.DATADATE >= TRUNC(SYSDATE) - 7
GROUP BY r.HISTORYID, r.WORKCENTERNAME, r.DATADATE
ORDER BY r.DATADATE DESC, UTILIZATION_PCT DESC;
```

---

### 場景6: Hold批次分析

**需求**: 統計當前Hold批次、Hold原因、Hold時長

**推薦表**:
- 當前狀態: `DW_MES_WIP`
- 歷史記錄: `DW_MES_HOLDRELEASEHISTORY`

**查詢邏輯（當前Hold）**:
```sql
SELECT
    CONTAINERNAME,
    PRODUCTNAME,
    PRODUCTLINENAME,
    WORKCENTERNAME,
    WORKFLOWSTEPNAME,
    HOLDREASONNAME,
    HOLDTIME,
    ROUND((SYSDATE - HOLDTIME) * 24, 2) as HOLD_HOURS,
    HOLDEMP,
    HOLDLOCATIONNAME,
    CURRENTHOLDCOUNT,
    HOLDCOMMENT_FUTURE
FROM DW_MES_WIP
WHERE CURRENTHOLDCOUNT > 0
  AND STATUS NOT IN (8, 128)
ORDER BY HOLD_HOURS DESC;
```

**查詢邏輯（Hold歷史分析）**:
```sql
SELECT
    HOLDREASONNAME,
    COUNT(*) as HOLD_COUNT,
    AVG((RELEASETXNDATE - HOLDTXNDATE) * 24) as AVG_HOLD_HOURS,
    MAX((RELEASETXNDATE - HOLDTXNDATE) * 24) as MAX_HOLD_HOURS,
    SUM(QTY) as TOTAL_HOLD_QTY
FROM DW_MES_HOLDRELEASEHISTORY
WHERE HOLDTXNDATE >= TRUNC(SYSDATE) - 30
  AND RELEASETXNDATE IS NOT NULL
GROUP BY HOLDREASONNAME
ORDER BY HOLD_COUNT DESC;
```

---

### 場景7: 設備維修工單進度追蹤

**需求**: 查詢工單的投入數量、完成數量、在制數量、預計完成時間

**推薦表**: `DW_MES_WIP` + `DW_MES_CONTAINER`

**查詢邏輯**:
```sql
WITH WO_SUMMARY AS (
    SELECT
        MFGORDERNAME,
        PRODUCTNAME,
        MAX(WOQTY) as WO_TOTAL_QTY,
        MAX(WOPLANNEDCOMPLETIONDATE) as PLANNED_COMPLETION_DATE,
        COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
        SUM(QTY) as CURRENT_WIP_QTY,
        SUM(CASE WHEN CURRENTHOLDCOUNT > 0 THEN QTY ELSE 0 END) as HOLD_QTY,
        MIN(MOVEINTIMESTAMP) as FIRST_MOVEIN,
        MAX(MOVEINTIMESTAMP) as LAST_MOVEIN
    FROM DW_MES_WIP
    WHERE STATUS NOT IN (8, 128)
    GROUP BY MFGORDERNAME, PRODUCTNAME
)
SELECT
    MFGORDERNAME,
    PRODUCTNAME,
    WO_TOTAL_QTY,
    CURRENT_WIP_QTY,
    HOLD_QTY,
    (WO_TOTAL_QTY - CURRENT_WIP_QTY) as COMPLETED_QTY,
    ROUND((CURRENT_WIP_QTY / NULLIF(WO_TOTAL_QTY, 0)) * 100, 2) as WIP_PCT,
    ROUND((HOLD_QTY / NULLIF(CURRENT_WIP_QTY, 0)) * 100, 2) as HOLD_PCT,
    PLANNED_COMPLETION_DATE,
    CASE
        WHEN PLANNED_COMPLETION_DATE < SYSDATE THEN 'Overdue'
        WHEN PLANNED_COMPLETION_DATE < SYSDATE + 3 THEN 'Critical'
        ELSE 'On Track'
    END as STATUS,
    LOT_COUNT,
    FIRST_MOVEIN,
    LAST_MOVEIN
FROM WO_SUMMARY
ORDER BY PLANNED_COMPLETION_DATE;
```

---

### 場景8: 良率分析

**需求**: 分析各工序、產品的良率

**推薦表**:
- `DW_MES_LOTWIPHISTORY`（產出）
- `DW_MES_LOTREJECTHISTORY`（報廢）

**查詢邏輯**:
```sql
SELECT
    w.WORKCENTERNAME,
    w.SPECNAME,
    w.PRODUCTNAME,
    TRUNC(w.MOVEINTIMESTAMP) as WORK_DATE,
    -- 產出統計
    COUNT(DISTINCT w.CONTAINERID) as LOT_COUNT,
    SUM(w.MOVEINQTY) as TOTAL_INPUT_QTY,
    SUM(w.MOVEOUTQTY) as TOTAL_OUTPUT_QTY,
    -- 報廢統計
    SUM(NVL(r.REJECTQTY, 0)) as TOTAL_REJECT_QTY,
    -- 良率計算
    ROUND((1 - SUM(NVL(r.REJECTQTY, 0)) / NULLIF(SUM(w.MOVEINQTY), 0)) * 100, 2) as YIELD_PCT
FROM DW_MES_LOTWIPHISTORY w
LEFT JOIN DW_MES_LOTREJECTHISTORY r
    ON w.CONTAINERID = r.CONTAINERID
    AND w.SPECID = r.SPECID
    AND TRUNC(w.MOVEINTIMESTAMP) = TRUNC(r.TXNDATE)
WHERE w.MOVEINTIMESTAMP >= TRUNC(SYSDATE) - 30
GROUP BY w.WORKCENTERNAME, w.SPECNAME, w.PRODUCTNAME, TRUNC(w.MOVEINTIMESTAMP)
ORDER BY WORK_DATE DESC, YIELD_PCT ASC;
```

**報廢原因分析**:
```sql
SELECT
    WORKCENTERNAME,
    SPECNAME,
    LOSSREASONNAME,
    REJECTCATEGORYNAME,
    COUNT(*) as OCCURRENCE_COUNT,
    SUM(REJECTQTY) as TOTAL_REJECT_QTY,
    AVG(REJECTQTY) as AVG_REJECT_QTY_PER_LOT
FROM DW_MES_LOTREJECTHISTORY
WHERE TXNDATE >= TRUNC(SYSDATE) - 30
GROUP BY WORKCENTERNAME, SPECNAME, LOSSREASONNAME, REJECTCATEGORYNAME
ORDER BY TOTAL_REJECT_QTY DESC;
```

---

## 查詢效能最佳實踐

### 1. 大表查詢原則

#### 必須加時間範圍的表（>1000萬筆）
- `DW_MES_WIP`: 使用 `TXNDATE`
- `DW_MES_LOTWIPDATAHISTORY`: 使用 `TXNTIMESTAMP`
- `DW_MES_RESOURCESTATUS_SHIFT`: 使用 `DATADATE`（推薦）
- `DW_MES_RESOURCESTATUS`: 使用 `OLDLASTSTATUSCHANGEDATE`
- `DW_MES_LOTWIPHISTORY`: 使用 `TRACKINTIMESTAMP` 或 `MOVEINTIMESTAMP`
- `DW_MES_MAINTENANCE`: 使用 `TXNDATE`
- `DW_MES_HM_LOTMOVEOUT`: 使用 `TXNDATE`
- `DW_MES_LOTMATERIALSHISTORY`: 使用 `TXNDATE`
- `DW_MES_LOTREJECTHISTORY`: 使用 `TXNDATE`

#### 推薦時間範圍
```sql
-- 日報表
WHERE DATADATE >= TRUNC(SYSDATE) - 7

-- 週報表
WHERE DATADATE >= TRUNC(SYSDATE, 'IW') - 7

-- 月報表
WHERE DATADATE >= TRUNC(SYSDATE, 'MM')
```

### 2. 索引使用策略

#### 優先使用索引欄位
```sql
-- 好的寫法（使用索引）
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
  AND CONTAINERNAME = 'LOT123'

-- 不好的寫法（破壞索引）
WHERE TO_CHAR(TXNDATE, 'YYYY-MM-DD') = '2026-01-14'
  OR UPPER(CONTAINERNAME) = 'LOT123'
```

#### 各表主要索引

| 表名 | 推薦查詢索引 |
|------|------------|
| DW_MES_WIP | `CONTAINERNAME`, `TXNDATE` |
| DW_MES_RESOURCESTATUS_SHIFT | `DATADATE`, `HISTORYID` |
| DW_MES_LOTWIPHISTORY | `TRACKINTIMESTAMP`, `CONTAINERID`, `PJ_WORKORDER` |
| DW_MES_HM_LOTMOVEOUT | `TXNDATE`, `HISTORYID` |

### 3. JOIN優化

#### 推薦JOIN順序
```sql
-- 小表 JOIN 大表
SELECT ...
FROM DW_MES_RESOURCE r  -- 90K rows
INNER JOIN DW_MES_RESOURCESTATUS_SHIFT rs  -- 74M rows
    ON r.RESOURCEID = rs.HISTORYID
WHERE rs.DATADATE >= TRUNC(SYSDATE) - 7  -- 先過濾大表
```

#### 避免笛卡爾積
```sql
-- 使用 DISTINCT 或 GROUP BY 去重
SELECT DISTINCT
    w.CONTAINERNAME,
    r.RESOURCENAME
FROM DW_MES_WIP w
INNER JOIN DW_MES_LOTWIPHISTORY h
    ON w.CONTAINERID = h.CONTAINERID
```

### 4. 聚合查詢優化

#### 使用SHIFT表而非原始表
```sql
-- 推薦：使用班次彙總表
SELECT DATADATE, SUM(HOURS)
FROM DW_MES_RESOURCESTATUS_SHIFT
WHERE DATADATE >= TRUNC(SYSDATE) - 30
GROUP BY DATADATE;

-- 不推薦：使用原始狀態表
SELECT TRUNC(OLDLASTSTATUSCHANGEDATE),
       SUM((LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24)
FROM DW_MES_RESOURCESTATUS
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 30
GROUP BY TRUNC(OLDLASTSTATUSCHANGEDATE);
```

### 5. 分頁查詢

```sql
-- Oracle 12c+ 使用 OFFSET FETCH
SELECT *
FROM (
    SELECT CONTAINERNAME, PRODUCTNAME, MOVEINTIMESTAMP
    FROM DW_MES_WIP
    WHERE STATUS NOT IN (8, 128)
    ORDER BY MOVEINTIMESTAMP DESC
)
OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY;

-- Oracle 11g 使用 ROWNUM
SELECT *
FROM (
    SELECT ROWNUM as RN, t.*
    FROM (
        SELECT CONTAINERNAME, PRODUCTNAME, MOVEINTIMESTAMP
        FROM DW_MES_WIP
        WHERE STATUS NOT IN (8, 128)
        ORDER BY MOVEINTIMESTAMP DESC
    ) t
    WHERE ROWNUM <= 100
)
WHERE RN > 0;
```

---

## 附錄：常用代碼對照表

### STATUS 狀態碼

| STATUS值 | 含義 |
|---------|------|
| 1 | In Progress（進行中） |
| 2 | On Hold（暫停） |
| 4 | Released（已釋放） |
| 8 | Completed（已完成） |
| 16 | In Queue（排隊中） |
| 32 | Reserved（保留） |
| 64 | In Transit（運輸中） |
| 128 | Cancelled（已取消） |

### AVAILABILITY 可用性代碼

| AVAILABILITY | 含義 | 用途 |
|-------------|------|------|
| 1 | Productive | 生產中（計入稼動時間） |
| 2 | Standby | 待機（不計入稼動） |
| 3 | Non-Scheduled | 非排程時間 |
| 4 | Unscheduled Down | 非計劃停機（故障） |
| 5 | Scheduled Down | 計劃停機（保養） |

### TXNTYPE 交易類型

需根據實際系統定義

### OBJECTTYPE 資源類型

| OBJECTTYPE | 說明 |
|-----------|------|
| Equipment | 設備 |
| WorkStation | 工作站 |
| Location | 位置 |

---

## 總結與建議

### 表選擇決策樹

```
查詢需求分類：

1. 要查詢"當前狀態" → 使用快照表
   - 在制品現況 → DW_MES_WIP
   - 設備基本信息 → DW_MES_RESOURCE
   - 容器當前狀態 → DW_MES_CONTAINER
   - 設備維修工單當前狀態 → DW_MES_JOB

2. 要查詢"歷史記錄" → 使用歷史表
   - 批次流轉歷史 → DW_MES_LOTWIPHISTORY
   - 設備狀態歷史 → DW_MES_RESOURCESTATUS_SHIFT（推薦）或 RESOURCESTATUS
   - 批次移出事件 → DW_MES_HM_LOTMOVEOUT
   - 數據採集歷史 → DW_MES_LOTWIPDATAHISTORY

3. 要做"統計分析" → 優先使用彙總表
   - 設備稼動率 → DW_MES_RESOURCESTATUS_SHIFT（已計算HOURS）
   - 產出統計 → DW_MES_LOTWIPHISTORY
   - 良率分析 → DW_MES_LOTWIPHISTORY + DW_MES_LOTREJECTHISTORY
```

### 開發優先級建議

#### 第一階段：基礎報表（必須）
1. 在制品看板（WIP Dashboard）
2. 設備稼動率報表（OEE Report）
3. 設備維修工單進度追蹤（WO Progress）

#### 第二階段：分析報表（重要）
4. Cycle Time分析
5. 設備產出分析
6. Hold批次分析

#### 第三階段：深度分析（進階）
7. 良率分析
8. 瓶頸工序分析
9. 批次履歷追溯

### 效能關鍵注意事項

⚠️ **關鍵警告**：
1. 所有大表（>1000萬筆）查詢必須加時間範圍
2. 優先使用班次彙總表（SHIFT）而非原始表
3. 避免在索引欄位使用函數
4. JOIN時先過濾再關聯
5. 使用EXPLAIN PLAN檢查執行計劃

---

**文檔版本**: v1.2
**最後更新**: 2026-01-29
**更新內容**: DWH 全表掃描更新數據量、補充 DW_MES_SPEC_WORKCENTER_V 工站對照視圖與查詢策略
**建議更新週期**: 每季度或表結構變更時





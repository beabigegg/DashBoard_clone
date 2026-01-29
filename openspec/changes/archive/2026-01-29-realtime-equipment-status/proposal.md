## Why

現有機台狀況表使用 `DW_MES_RESOURCE` + `DW_MES_RESOURCESTATUS` 組合查詢，需要複雜的 ROW_NUMBER + 時間視窗計算來推導「最新狀態」。這種方式有幾個問題：
1. **查詢複雜度高**：每次都要 JOIN 兩表並用視窗函數取最新記錄
2. **非真正即時**：依賴 RESOURCESTATUS 的最後 N 天歷史，實際可能延遲數小時
3. **效能負擔大**：Oracle 查詢量大（掃描 6,500 萬筆歷史記錄）

`DW_MES_EQUIPMENTSTATUS_WIP_V` 是 DWH 提供的**真正即時視圖**，透過 DB Link 直接查詢源頭，包含設備狀態、維修工單、當前 WIP 等 32 欄位，且資料量僅約 2,600 筆。

## What Changes

### 新增快取層

1. **即時設備狀態快取**（5 分鐘同步）
   - 來源：`DW_MES_EQUIPMENTSTATUS_WIP_V`
   - 資料：即時設備狀態、維修工單、WIP Track-In 資訊
   - 篩選：使用 `resource-cache` 中的有效設備清單過濾

2. **工站對照快取**（每天同步）
   - 來源：`DW_MES_SPEC_WORKCENTER_V`（230 筆）
   - 資料：WORK_CENTER → WORK_CENTER_GROUP 對照、排序規則

### 資料組合邏輯

```
[resource-cache]              [realtime-equipment-cache]     [workcenter-mapping-cache]
DW_MES_RESOURCE               DW_MES_EQUIPMENTSTATUS_WIP_V   DW_MES_SPEC_WORKCENTER_V
(篩選後設備主檔)               (即時狀態)                     (工站分組對照)
     |                              |                              |
     +--- RESOURCEID ----+--- RESOURCEID                           |
                         |                                         |
                         v                                         |
              [合併後即時機況]                                      |
              (主檔欄位 + 即時狀態)                                 |
                         |                                         |
                         +--- WORKCENTERNAME ---+--- WORK_CENTER ---+
                                                |
                                                v
                                    [完整機台狀況表]
                                    (含 WORKCENTER_GROUP)
```

### 欄位來源對照

| 欄位 | 來源 | 備註 |
|------|------|------|
| RESOURCEID | resource-cache | 主鍵 |
| RESOURCENAME | resource-cache | 設備編號 |
| WORKCENTERNAME | resource-cache | 工站名稱 |
| RESOURCEFAMILYNAME | resource-cache | 設備族群 |
| PJ_DEPARTMENT | resource-cache | 部門 |
| PJ_ISPRODUCTION | resource-cache | 生產機 Flag |
| PJ_ISKEY | resource-cache | 關鍵機 Flag |
| PJ_ISMONITOR | resource-cache | 監控機 Flag |
| EQUIPMENTASSETSSTATUS | realtime-cache | 即時狀態 |
| EQUIPMENTASSETSSTATUSREASON | realtime-cache | 狀態原因 |
| JOBORDER | realtime-cache | 維修工單號 |
| JOBSTATUS | realtime-cache | 工單狀態 |
| SYMPTOMCODE | realtime-cache | 症狀代碼 |
| RUNCARDLOTID | realtime-cache | 當前 WIP 批次 |
| LOTTRACKINTIME | realtime-cache | Track-In 時間 |
| LOTTRACKINQTY_PCS | realtime-cache | Track-In 數量 |
| WORK_CENTER_GROUP | workcenter-mapping | 工站分組 |
| WORKCENTERSEQUENCE_GROUP | workcenter-mapping | 分組排序 |

## Capabilities

### New Capabilities
- `realtime-equipment-cache`: 即時設備狀態快取層，每 5 分鐘從 `DW_MES_EQUIPMENTSTATUS_WIP_V` 同步至 Redis，提供即時狀態、維修工單、WIP Track-In 資訊
- `workcenter-mapping-cache`: 工站對照快取層，每天從 `DW_MES_SPEC_WORKCENTER_V` 同步至 Redis，提供 WORK_CENTER → WORK_CENTER_GROUP 對照

### Modified Capabilities
- `resource-cache`: 擴充 API 支援與即時狀態快取合併查詢

## Impact

### 資料來源比較

| 面向 | 現有方式 | 新方式 |
|------|---------|--------|
| **即時狀態來源** | RESOURCE + RESOURCESTATUS JOIN | EQUIPMENTSTATUS_WIP_V (即時) |
| **掃描資料量** | ~9萬 + ~6500萬 | ~2,600 筆 |
| **查詢複雜度** | 視窗函數 + 時間條件 | 簡單全表 |
| **更新頻率** | 查詢時計算 | 5 分鐘快取 |
| **篩選欄位** | 直接可用 | 從 resource-cache 補充 |

### 關鍵對應關係

| 關聯 | 來源表 | 目標表 | 關聯欄位 |
|------|--------|--------|---------|
| 設備主檔 ↔ 即時狀態 | resource-cache | EQUIPMENTSTATUS_WIP_V | RESOURCEID |
| 設備 ↔ 工站分組 | resource-cache | SPEC_WORKCENTER_V | WORKCENTERNAME ↔ WORK_CENTER |

### 待確認事項

1. **狀態值對應**：`EQUIPMENTASSETSSTATUS` (PRD, IDLE...) vs `NEWSTATUSNAME` (PRD, SBY, UDT...)
   - 需確認值域是否相同或需要 mapping

2. **資料覆蓋範圍**：
   - EQUIPMENTSTATUS_WIP_V 約 2,631 筆
   - resource-cache 篩選後約 3,000+ 台
   - 差異可能是「無狀態」的設備，需確認處理方式

3. **WORK_CENTER 對應**：
   - resource-cache 的 WORKCENTERNAME 與 SPEC_WORKCENTER_V 的 WORK_CENTER 是否完全對應
   - 是否有 WORKCENTERNAME 找不到對應 WORK_CENTER_GROUP 的情況

### 受影響程式碼

- 新增：`src/mes_dashboard/services/realtime_equipment_cache.py`
- 新增：`src/mes_dashboard/services/workcenter_mapping_cache.py`
- 修改：`src/mes_dashboard/services/resource_service.py` - 改用快取組合查詢
- 修改：`src/mes_dashboard/routes/resource_routes.py` - API 回應結構可能調整
- 修改：`src/mes_dashboard/templates/resource_status.html` - 新增欄位顯示

### 依賴項

- Redis (已部署)
- 現有 `resource-cache` 機制
- 現有 `filter_cache` 機制（可考慮整合 workcenter-mapping）

## Context

### 現況

現有機台狀況表透過 `DW_MES_RESOURCE` + `DW_MES_RESOURCESTATUS` 組合查詢取得設備最新狀態：
- 需要 ROW_NUMBER 視窗函數 + 時間條件篩選最新記錄
- 每次查詢掃描約 6,500 萬筆歷史記錄
- 狀態可能延遲數小時（依賴歷史表同步頻率）

### 資料調查結論

| 項目 | 結果 |
|------|------|
| resource-cache 設備數 | 1,804 |
| 能對應即時狀態的設備 | 1,803 (99.94%) |
| 工站對應 WORK_CENTER_GROUP | 18/18 (100%) |
| EQUIPMENTSTATUS_WIP_V 重複記錄 | 有（同設備多 LOT） |
| 狀態值相容性 | E10 標準 + 少量非標準 |

### 約束條件

- Redis 已部署，可用於快取
- 現有 `resource-cache` 機制已實作，4 小時同步一次
- 現有 `filter_cache` 從 WIP 視圖取得 workcenter_group 對照
- 前端機台狀況表已有完整 UI，僅需調整資料來源

---

## Goals / Non-Goals

### Goals

1. **提供即時設備狀態**：從 `DW_MES_EQUIPMENTSTATUS_WIP_V` 取得真正即時的設備狀態，5 分鐘同步一次
2. **擴充設備資訊**：新增維修工單、當前 WIP、Track-In 等欄位
3. **統一工站分組**：使用 `DW_MES_SPEC_WORKCENTER_V` 提供一致的 WORK_CENTER_GROUP 對照
4. **保持向後相容**：現有 API 回應結構維持相容，新欄位為追加

### Non-Goals

1. **不取代 resource-cache**：resource-cache 仍作為設備主檔來源，提供篩選欄位
2. **不改變篩選邏輯**：維持現有的設備篩選條件（OBJECTCATEGORY、LOCATIONNAME、PJ_ASSETSSTATUS）
3. **不實作 WIP 詳細列表**：多 LOT 情況僅提供聚合數據，不展開明細
4. **不修改設備歷史績效功能**：該功能使用 RESOURCESTATUS_SHIFT，不受影響

---

## Decisions

### Decision 1: 快取架構 - 三層快取組合

**選擇**：新增兩個獨立快取，與現有 resource-cache 組合查詢

```
┌─────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│   resource-cache    │  │ realtime-equipment-cache│  │ workcenter-mapping-cache│
│  DW_MES_RESOURCE    │  │ EQUIPMENTSTATUS_WIP_V   │  │ SPEC_WORKCENTER_V       │
│  (4 小時同步)        │  │ (5 分鐘同步)            │  │ (每天同步)              │
│  ~1,804 筆          │  │ ~2,607 筆               │  │ ~230 筆                 │
└─────────┬───────────┘  └───────────┬─────────────┘  └───────────┬─────────────┘
          │                          │                            │
          │   RESOURCEID             │   RESOURCEID               │   WORK_CENTER
          └──────────┬───────────────┘                            │
                     │                                            │
                     v                                            │
          ┌─────────────────────┐                                 │
          │   Python 端合併     │◄────── WORKCENTERNAME ──────────┘
          │   (查詢時 JOIN)     │
          └─────────────────────┘
```

**替代方案考量**：
- ❌ 單一大快取：同步頻率不同，且 resource-cache 已存在
- ❌ 直接查 Oracle：無法達到即時性要求，查詢成本高

**理由**：
- 各快取獨立同步，頻率可分別調整
- 複用現有 resource-cache，降低改動範圍
- workcenter-mapping 變動極少，每天同步即可

---

### Decision 2: 即時狀態快取結構 - 預聚合 by RESOURCEID

**選擇**：同步時預先 GROUP BY RESOURCEID，儲存聚合後資料

**Redis 結構**：
```
{prefix}:equipment_status:data     → JSON Array (每設備一筆，已聚合)
{prefix}:equipment_status:index    → Hash {RESOURCEID → array index} (快速查找)
{prefix}:equipment_status:meta:updated → ISO 8601 timestamp
{prefix}:equipment_status:meta:count   → 記錄數
```

**單筆資料結構**：
```json
{
  "RESOURCEID": "488016800000036a",
  "EQUIPMENTID": "DB-001",
  "EQUIPMENTASSETSSTATUS": "PRD",
  "EQUIPMENTASSETSSTATUSREASON": "Production RUN",
  "JOBORDER": "J2026010001",
  "JOBSTATUS": "Open",
  "SYMPTOMCODE": null,
  "CAUSECODE": null,
  "REPAIRCODE": null,
  "LOT_COUNT": 3,
  "TOTAL_TRACKIN_QTY": 15000,
  "LATEST_TRACKIN_TIME": "2026-01-29T10:30:00"
}
```

**替代方案考量**：
- ❌ 儲存原始資料（未聚合）：浪費空間，查詢時需再聚合
- ❌ 每設備一個 key：key 數量過多（~2,600），不利批次操作

**理由**：
- 預聚合減少查詢時運算
- 單一 JSON Array 便於全量載入與篩選
- Index Hash 支援單筆快速查找

---

### Decision 3: 工站對照快取 - 整合進 filter_cache

**選擇**：擴充現有 `filter_cache.py`，新增 workcenter → group 對照

**理由**：
- filter_cache 已有 workcenter_groups 邏輯，但來源是 WIP 視圖
- 改用 SPEC_WORKCENTER_V 作為權威來源，資料更完整（230 筆 vs WIP 中出現的子集）
- 避免新增獨立快取模組，降低複雜度

**變更**：
```python
# filter_cache.py 新增
def _load_workcenter_mapping_from_spec():
    """從 DW_MES_SPEC_WORKCENTER_V 載入工站對照"""
    sql = """
        SELECT DISTINCT
            WORK_CENTER,
            WORK_CENTER_GROUP,
            WORKCENTERSEQUENCE_GROUP,
            WORK_CENTER_SHORT
        FROM DWH.DW_MES_SPEC_WORKCENTER_V
    """
    ...
```

---

### Decision 4: 同步策略 - 全量覆蓋

**選擇**：每次同步全量載入並覆蓋

**理由**：
- EQUIPMENTSTATUS_WIP_V 僅 ~2,600 筆，全量載入成本低
- 無版本欄位可做差異同步
- 避免增量同步的複雜度（刪除偵測、狀態一致性）

**同步流程**：
```
1. 查詢 Oracle：SELECT * FROM EQUIPMENTSTATUS_WIP_V
2. Python 端 GROUP BY RESOURCEID 聚合
3. 建立 index mapping
4. Redis MULTI/EXEC 原子寫入
```

---

### Decision 5: 狀態值處理 - 保持原值 + 分類標籤

**選擇**：保留原始狀態值，額外提供 `STATUS_CATEGORY` 分類

**狀態分類規則**：
```python
STATUS_CATEGORY_MAP = {
    'PRD': 'PRODUCTIVE',
    'SBY': 'STANDBY',
    'UDT': 'DOWN',
    'SDT': 'DOWN',
    'EGT': 'ENGINEERING',
    'NST': 'NOT_SCHEDULED',
    'SCRAP': 'INACTIVE',
    '設備-LOST': 'INACTIVE',
    '設備-RUN': 'PRODUCTIVE',  # 需確認
}
# 未列出的歸類為 'OTHER'
```

**理由**：
- 保留原值供詳細顯示
- 分類標籤便於前端 UI 著色與統計

---

### Decision 6: API 設計 - 擴充現有 endpoint

**選擇**：擴充 `/api/resource/status` 回應，新增欄位

**新增欄位**：
```json
{
  "RESOURCENAME": "DB-001",
  "WORKCENTERNAME": "焊接_DB",
  "WORKCENTER_GROUP": "焊接",           // 新增
  "NEWSTATUSNAME": "PRD",               // 來自即時快取
  "NEWREASONNAME": "Production RUN",    // 來自即時快取
  "STATUS_CATEGORY": "PRODUCTIVE",      // 新增
  "JOBORDER": "J2026010001",            // 新增
  "JOBSTATUS": "Open",                  // 新增
  "LOT_COUNT": 3,                       // 新增
  "TOTAL_TRACKIN_QTY": 15000,           // 新增
  "LATEST_TRACKIN_TIME": "2026-01-29T10:30:00",  // 新增
  // ... 現有欄位保留
}
```

**Fallback 策略**：
- 若 RESOURCEID 在即時快取找不到（1/1804），使用現有 RESOURCESTATUS 查詢
- 記錄 warning log

---

## Risks / Trade-offs

### Risk 1: 即時快取同步延遲
**風險**：5 分鐘同步間隔內，狀態變更不會反映
**緩解**：
- 前端顯示「最後更新時間」
- 提供手動刷新按鈕（觸發 force refresh）
- 可調整 `EQUIPMENT_STATUS_SYNC_INTERVAL` 環境變數

### Risk 2: 聚合邏輯假設錯誤
**風險**：假設同 RESOURCEID 的 EQUIPMENTASSETSSTATUS 相同，若實際不同會取錯值
**緩解**：
- 同步時檢查並記錄 warning
- 取 MAX 或最常出現的值

### Risk 3: SPEC_WORKCENTER_V 與 RESOURCE 的 WORKCENTERNAME 不完全匹配
**風險**：調查顯示 100% 匹配，但未來可能有新工站
**緩解**：
- 無法匹配時 WORKCENTER_GROUP 回傳 null
- 每日同步 log 記錄未匹配的 WORKCENTERNAME

### Risk 4: 非標準狀態值增加
**風險**：未來可能出現更多非標準狀態（如 設備-LOST）
**緩解**：
- STATUS_CATEGORY_MAP 設定檔化，便於更新
- 未知狀態歸類為 'OTHER'，不影響系統運作

---

## Migration Plan

### Phase 1: 新增快取層（不影響現有功能）

1. 實作 `realtime_equipment_cache.py`
2. 擴充 `filter_cache.py` 新增 workcenter mapping
3. 新增環境變數與設定
4. 部署並驗證快取同步正常

### Phase 2: 整合至 API

1. 修改 `resource_service.py` 使用新快取
2. 擴充 API 回應欄位
3. 實作 fallback 邏輯
4. 更新 API 文件

### Phase 3: 前端整合

1. 更新機台狀況表顯示新欄位
2. 新增 WORKCENTER_GROUP 篩選器
3. 顯示 WIP 相關資訊（LOT_COUNT 等）

### Rollback Strategy

- 環境變數 `REALTIME_EQUIPMENT_CACHE_ENABLED=false` 可完全停用新快取
- API 自動 fallback 到現有 RESOURCESTATUS 查詢邏輯
- 前端新欄位設計為 optional，缺失時不顯示

---

## Open Questions

1. **`設備-RUN` 狀態含義**：需與業務確認，暫歸類為 PRODUCTIVE
2. **WIP 詳細資訊需求**：是否需要展開顯示每個 LOT，還是僅顯示聚合數據？
3. **同步頻率調整**：5 分鐘是否滿足業務需求？是否需要更頻繁？
4. **維修工單展開**：一台設備可能有多個工單，是否需要全部顯示？

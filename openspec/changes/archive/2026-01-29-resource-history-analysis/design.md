## Context

目前系統的 /resource 頁面混合即時與歷史資料展示，歷史分析功能受限於現有架構。資料來源為：

- **DW_MES_RESOURCESTATUS_SHIFT**：班次級狀態彙總表（約 74M 筆），包含 HOURS 欄位可直接計算各狀態工時
- **DW_MES_RESOURCE**：機台維度資料（約 90K 筆），包含 WORKCENTERNAME、RESOURCEFAMILYNAME、RESOURCENAME 等維度

現有 `dashboard_service.py` 已有 `query_ou_trend()` 和 `query_utilization_heatmap()` 函數可參考，使用相同的 OU% 計算公式：`PRD / (PRD + SBY + EGT + SDT + UDT) * 100`

## Goals / Non-Goals

**Goals:**

- 建立獨立的歷史分析頁面，支援多維度、多時間粒度的機台效能分析
- 實現三層階層式下鑽：站點 → 型號 → 個別機台
- 提供完整的 SEMI E10 設備狀態分析（時數 + 佔比）
- 支援日/週/月/年的時間粒度切換
- 採用查詢觸發模式，避免頁面載入時的效能衝擊

**Non-Goals:**

- 不修改現有 /resource 頁面的即時機況功能（僅移除歷史圖表）
- 不實作即時資料推送或自動刷新
- 不整合其他資料來源（如 SECS/GEM 設備訊號）
- 不實作機台詳細事件時間軸（甘特圖）—— 可作為後續擴充

## Decisions

### 1. 頁面架構：完全獨立頁面

**決定**：建立 `/resource-history` 作為完全獨立的頁面

**替代方案**：
- (A) 在 /resource 頁面新增 Tab 切換 → 會增加頁面複雜度，且兩者篩選條件不同
- (B) 子路由 `/resource/history` → 與現有 /resource 頁面產生關聯，不符合獨立需求

**理由**：完全獨立的頁面便於維護，不影響現有 /resource 即時機況功能。

### 2. 資料服務：獨立 Service 模組

**決定**：建立 `resource_history_service.py` 獨立模組

**替代方案**：
- (A) 擴展現有 `resource_service.py` → 會使檔案過大且職責混淆
- (B) 擴展 `dashboard_service.py` → 該模組已有多個功能，不適合再擴展

**理由**：單一職責原則，便於維護與測試。可重用 `dashboard_service.py` 中的 OU 計算邏輯。

### 3. 時間粒度處理：SQL 層聚合

**決定**：在 SQL 查詢中使用 `TRUNC()` 進行時間聚合

```sql
-- 日：TRUNC(TXNDATE)
-- 週：TRUNC(TXNDATE, 'IW')  -- ISO week
-- 月：TRUNC(TXNDATE, 'MM')
-- 年：TRUNC(TXNDATE, 'YYYY')
```

**替代方案**：
- (A) Python 層聚合 → 需拉取更多資料，效能差
- (B) 預計算彙總表 → 需額外 ETL 流程，增加維護成本

**理由**：利用 Oracle 原生函數在資料庫層高效聚合，減少網路傳輸。

### 4. 階層式資料結構：單次查詢 + 前端組裝

**決定**：後端回傳扁平化資料，包含 WORKCENTERNAME、RESOURCEFAMILYNAME、RESOURCENAME 三個維度欄位，前端根據需要進行階層組裝

**替代方案**：
- (A) 後端回傳巢狀 JSON → 結構複雜，不利於匯出
- (B) 三次獨立查詢（各層級） → 網路請求多，延遲增加

**理由**：單次查詢減少延遲，扁平結構便於表格渲染與匯出，前端可靈活控制展開/收合邏輯。

### 5. 圖表實作：ECharts

**決定**：沿用現有 ECharts 套件

**理由**：與現有頁面一致，減少學習成本和套件依賴。已有 OU 趨勢圖和熱力圖的實作可參考。

### 6. 匯出功能：CSV 格式

**決定**：提供 CSV 匯出，由後端生成

**替代方案**：
- (A) Excel 格式 → 需額外套件（openpyxl），增加依賴
- (B) 前端匯出 → 資料量大時效能問題

**理由**：CSV 輕量且通用，後端處理可支援大量資料。

## Risks / Trade-offs

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| 大量資料查詢效能 | 74M 筆資料表的聚合查詢可能緩慢 | 強制要求日期範圍限制（最多 1 年）；使用 TXNDATE 索引；考慮查詢超時設定 |
| 前端渲染效能 | 大量機台明細可能導致表格卡頓 | 實作分頁或虛擬捲動；限制單次回傳筆數（如 1000 筆） |
| 記憶體使用 | pandas DataFrame 處理大量資料 | 使用 chunked 讀取或直接串流輸出 |
| 使用者誤操作 | 選擇過長時間範圍導致查詢卡住 | 前端驗證時間範圍；顯示預估資料量警告 |

## API 設計

### 主要 API 端點

```
GET /api/resource/history/summary
    ?start_date=2024-01-01
    &end_date=2024-01-31
    &granularity=day|week|month|year
    &workcenter=WC01  (optional)
    &family=FAM01     (optional)
    &is_production=1  (optional)
    &is_key=1         (optional)

Response: {
    kpi: { ou_pct, prd_hours, sby_hours, udt_hours, sdt_hours, egt_hours, nst_hours, machine_count },
    trend: [{ date, ou_pct, prd_hours, ... }],
    heatmap: [{ workcenter, date, ou_pct }],
    workcenter_comparison: [{ workcenter, ou_pct, prd_hours, ... }]
}

GET /api/resource/history/detail
    ?start_date=2024-01-01
    &end_date=2024-01-31
    &granularity=day|week|month|year
    &workcenter=WC01  (optional)
    &family=FAM01     (optional)
    &page=1
    &page_size=100

Response: {
    data: [{ workcenter, family, resource, ou_pct, prd_hours, prd_pct, sby_hours, sby_pct, ... }],
    total: 1234,
    page: 1,
    page_size: 100
}

GET /api/resource/history/export
    ?start_date=2024-01-01
    &end_date=2024-01-31
    &granularity=day
    &format=csv

Response: CSV file download
```

## 前端元件結構

```
resource_history.html
├── Filter Bar
│   ├── Date Range Picker (start_date, end_date)
│   ├── Granularity Buttons (日/週/月/年)
│   ├── Workcenter Select (多選)
│   ├── Family Select (多選)
│   ├── Checkbox Filters (生產機/關鍵機/監控機)
│   └── Query Button
├── KPI Cards Row
│   ├── OU% Card
│   ├── PRD Hours Card
│   ├── UDT Hours Card
│   ├── SDT Hours Card
│   ├── EGT Hours Card
│   └── Machine Count Card
├── Charts Row 1
│   ├── OU% Trend Line Chart
│   └── E10 Stacked Bar Chart
├── Charts Row 2
│   ├── Workcenter Comparison Bar Chart
│   └── Utilization Heatmap
└── Detail Table
    ├── Toolbar (Export, Expand All)
    └── Hierarchical Table
        ├── Workcenter Level (expandable)
        │   ├── Family Level (expandable)
        │   │   └── Resource Level
```

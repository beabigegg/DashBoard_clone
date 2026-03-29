## Why

Resource History 頁面目前只顯示設備時間利用率指標（OU%、AVAIL%、各 E10 狀態時數），缺少產量與良率維度的 OEE（Overall Equipment Effectiveness）指標。現場已有 PJMES051 報表提供 OEE，但需要手動開報表對照，無法與設備稼動率整合分析。將 OEE 整合進 resource-history 頁面，讓使用者在同一介面看到稼動率 × 良率 = OEE 的完整圖像。

## What Changes

- 新增 **OEE%** KPI 卡片（1 張）到 resource-history 頁面的 Summary 區（9 → 10 張）
- 新增 Oracle SQL 查詢 `DWH.DW_MES_LOTWIPHISTORY`（產出 TRACKOUTQTY）和 `DWH.DW_MES_LOTREJECTHISTORY`（不良 NG_QTY），按設備 + 班別日期彙總，納入現有 Parquet spool 快取
- 後端 service 層整合產量/不良數據與現有時間數據，計算 OEE = Availability × Yield（Performance 固定 1.0）
- **Trend 圖表**：在現有 AVAIL%/OU% 趨勢圖上疊加 OEE% 折線
- **Detail 表格**：新增 OEE% 欄位（欄位順序：OU%、OEE%、AVAIL%）
- **Heatmap**：新增指標切換（現有 OU% + 新增 OEE% 選項）
- CSV 匯出新增 OEE% 欄位

## Capabilities

### New Capabilities
- `resource-history-oee-metrics`: 定義 OEE 計算公式（Availability × Yield, Performance=1.0）、數據來源（LOTWIPHISTORY + LOTREJECTHISTORY）、SQL 查詢規格、NG 計算公式（5 欄位加總, DEFECTQTY 排除）、07:30 班別日期切分規則

### Modified Capabilities
- `resource-history-page`: KPI 卡片 9→10 張（新增 OEE%），Trend 疊加 OEE% 折線，Detail 表格新增 OEE% 欄位，Heatmap 支援指標切換，匯出新增欄位
- `resource-dataset-cache`: 主查詢需平行取得產量/不良數據並納入 Parquet spool 快取；DuckDB runtime 需新增 OEE 的衍生計算

## Impact

- **後端 SQL**：新增 `sql/resource_history/oee_production.sql` 查詢 LOTWIPHISTORY + LOTREJECTHISTORY（資料量 ~45 萬筆/月，遠小於現有 RESOURCESTATUS_SHIFT 的 130 萬筆/月）
- **後端 Service**：修改 `resource_dataset_cache.py`（主查詢平行取產量數據，跟進 canonical base dataset pattern）和 `resource_history_sql_runtime.py`（DuckDB 衍生 OEE，唯一 compute path）
- **前端**：修改 `KpiCards.vue`（新增 OEE 卡片）、`compute.js`（新增 calcOeePct）、TrendChart（疊加折線）、HeatmapChart（指標切換）、Detail 表格（新增欄位）
- **API**：現有 `/api/resource/history/query` 和 `/view` 的回應結構擴充（新增 oee_pct 欄位，向下相容）
- **數據來源**：新依賴 `DWH.DW_MES_LOTWIPHISTORY` 和 `DWH.DW_MES_LOTREJECTHISTORY`，查詢需使用 workcenter_group 展開（透過 `DW_MES_SPEC_WORKCENTER_V`）和 07:30 班別日期切分
- **已知限制**：DWH 的 LOTREJECTHISTORY 缺少 LotTerminate/WIP reject 來源，Yield 偏高約 0.07%（與 PJMES051 報表對比驗證，97.2% 產出吻合、81.5% NG 吻合）

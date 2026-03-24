## Why

2026-03-24 的實際故障顯示：Query Tool 在高記憶體壓力下被 RSS guard 直接拒絕，導致查詢失敗（`RSS guard rejected ... rss_mb=1262.5 limit_mb=1100`）。  
同時間系統也出現 `System memory pressure CRITICAL`，代表這不是單一路由偶發，而是重查詢路徑在高壓場景下的共同風險。

目前程式中，除了 Query Tool 之外，仍有多個重查詢頁面使用相同或近似的「過載即拒絕」策略：

- `trace/events`：sync 路徑有 RSS guard，命中後直接 503
- `reject-history/query`：主查詢前有 RSS front-door reject
- `material-trace/query|export`：記憶體 guard 觸發後回傳 400（語意不一致）
- `yield-alert`：已具 DuckDB/spool 與 guard，但仍需與其他頁面的降級策略對齊

此外，AI 問答場景已暴露業務一致性缺口：低良率查詢未穩定套用 `WORKCENTER_GROUP` 彙整與 reject 業務過濾規則。若不與記憶體降級策略一起修，容易在高壓時同時出現「查不到」與「查到但邏輯不一致」。

## What Changes

建立跨頁「重查詢過載處理一致化」變更，分四個面向一次修復：

1. Query Tool DuckDB/spool 化（優先）
- LOT history / associations 批次路徑導入 parquet spool + DuckDB runtime（參照 reject/hold/resource 既有模式）
- RSS guard 命中時，優先走 spool/DuckDB 降級，不再直接失敗
- 對低良率相關結果，固定套用 `WORKCENTER_GROUP` 彙整與 reject 業務過濾策略

2. Trace / Reject / Material Trace 過載語意對齊
- 統一 MemoryError/overload 的 API 契約：`503 SERVICE_UNAVAILABLE` + `Retry-After` + machine-readable code
- Trace sync guard 命中時，優先改走 async job（可用時），降低直接失敗率
- Material Trace 由 `validation_error(400)` 改為 `service_unavailable(503)`

3. 共用重查詢降級策略
- 新增共用 helper，統一「cache/spool 可用時先回可用結果，再考慮拒絕」流程
- 避免各頁重複實作不同版本 guard 行為

4. 觀測與配置治理
- 統一 guard/reject/fallback 日誌欄位與 metrics（guard_hit、fallback_used、503_rate）
- 補齊 `.env.example` 相關參數（例如 `QUERY_TOOL_RSS_REJECT_MB`）與預設值說明

## Capabilities

### New Capabilities
- `parquet-spool-view-engine`: Query Tool 新增 DuckDB-on-spool 計算能力，用於高量 LOT 歷程/關聯查詢降級。

### Modified Capabilities
- `query-tool-lot-trace`: 高量 detail 查詢在記憶體高壓下 SHALL 優先走 spool/DuckDB 降級，並維持 `WORKCENTER_GROUP`/reject 業務規則一致。
- `trace-staged-api`: sync guard 命中時 SHALL 優先 async 化（可用時），降低直接 503。
- `reject-history-api`: RSS front-door reject SHALL 對齊統一過載回應與可重試訊號。
- `material-trace-api`: 記憶體過載錯誤 SHALL 回傳 503（非 400），與重查詢契約一致。
- `yield-alert-center-api`: 與跨頁過載契約對齊（回應碼、meta、retry 語意）。
- `system-memory-monitoring`: guard/fallback 指標與日誌欄位擴充，支援跨頁比較。

## Impact

- 後端修改重點：
  - `query_tool_service.py` + 新增 `query_tool_sql_runtime.py`
  - `query_tool_routes.py`, `trace_routes.py`, `material_trace_routes.py`, `reject_history_routes.py`
  - 共用記憶體降級 helper（core/service）
- 既有 API 路徑不變；主要是高壓時的行為從「直接失敗」改為「可降級優先、再失敗」
- 前端不需改動主要互動流程，但可選擇顯示更完整的 overload meta

## Scope

- 本變更聚焦「重查詢過載治理與業務一致性」；不重寫整體查詢架構
- 不修改既有主查詢 SQL 的業務欄位定義（除必要的業務過濾對齊）
- 不新增新頁面，只修既有重查詢路由與服務層

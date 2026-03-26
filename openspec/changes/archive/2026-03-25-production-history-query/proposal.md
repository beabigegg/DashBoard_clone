## Why

現場工程師需要快速查詢「某種產品在過去一段時間內，經過了哪些站點的哪些機台」。現有的批次追蹤工具以 LOT 血緣展開為核心，操作步驟多（resolve → 選節點 → 查 history），且不支援以 PJ_TYPE + 日期區間為主軸的聚合查詢。需要一個獨立頁面，一次查詢即可看到完整的生產足跡摘要與明細。

## What Changes

- 新增獨立頁面「生產歷程查詢」，以 PJ_TYPE + TrackIn 日期區間為核心查詢維度。
- 上方聚合 Matrix（WorkCenter → Spec → Equipment，按月份計數），下方明細 TABLE（25 rows/page）。
- 後端採用 Oracle 分段查詢 + Parquet spool + DuckDB 衍生視圖的兩層架構，支援 Matrix 聯動篩選、分頁、全量 CSV 匯出。
- 支援多 PJ_TYPE / 多工單 / 多 LOT ID 組合查詢。
- LOT ID 查詢時，沿 split chain 追溯 parent LOT 以取得完整前段歷程。
- 明確定義 API 契約：成功回應採 `{ success: true, data: ... }`；驗證錯誤、dataset 過期、重查詢壅塞等失敗情境有一致語義（400 / 410 / 503 + Retry-After）。
- 明確定義 dataset 生命週期（TTL、過期後重查流程）與 `/matrix`、`/export` 的 filter 契約，避免前後端實作歧義。

## Capabilities

### New Capabilities
- `production-history-query`: 以 PJ_TYPE + 日期區間為主軸的生產歷程聚合查詢與明細瀏覽，含 Matrix 摘要、明細分頁、全量匯出。

### Modified Capabilities
- None.

## Impact

- Affected code: 新增後端 route + service + SQL，新增前端獨立頁面（page entry + components + composables + style），portal-shell 路由註冊。
- Runtime/deploy: 無架構變動，複用現有 Oracle → Parquet spool → DuckDB 基礎設施。
- APIs/pages: 新增 `/api/production-history/*` 端點群組，新增 `/production-history` 前端頁面。
- Ops: 查詢量級較大（PJ_TYPE + 30 天可能數萬筆），需關注 spool 使用量、DuckDB 記憶體與 guard reject 比率。
- Test/Governance: 新增 dataset TTL/過期、overload retryable contract、filter encode/decode 與回應契約一致性測試。

## Phase 2 (Future)

- 搭配 REJECT 表與 ERP MOVE 表，在相同頁面擴充「機台 × TYPE 最終測試良率」與「報廢原因」分析視圖。

# Change Request

## Original Request

將 production-history 的 filter 從「Type 唯一一階 + 6 個二階 supplementary」改為「7 個一階 cross-filter（其中 4 個低基數走快取、3 個高基數走多行輸入）+ 2 個二階保留」。

**升階對照表：**

| 欄位 | 來源 | 新一階模式 | 備註 |
|---|---|---|---|
| Type (PJ_TYPE) | DW_MES_CONTAINER | MultiSelect (cache full list) | 既有，保留必選 |
| Package (PRODUCTLINENAME) | DW_MES_CONTAINER | MultiSelect (cache full list) | 從二階升 |
| BOP (PJ_BOP) | DW_MES_CONTAINER | MultiSelect (cache full list) | 從二階升 |
| Function (PJ_FUNCTION) | DW_MES_CONTAINER | MultiSelect (cache full list) | 全新 |
| 工單號 (MFGORDERNAME) | DW_MES_CONTAINER | 多行 textarea + `*` 萬用字元 | 從二階升 + 改 UX |
| LOT ID (CONTAINERNAME) | DW_MES_CONTAINER | 多行 textarea + `*` 萬用字元 | 從二階升 + 改 UX |
| Wafer LOT (FIRSTNAME) | DW_MES_CONTAINER | 多行 textarea + `*` 萬用字元 | 全新 |
| WorkCenter 群組 | spool (LOTWIPHISTORY) | **不動** — 維持二階 | DuckDB cross-filter |
| Equipment | spool (LOTWIPHISTORY) | **不動** — 維持二階 | DuckDB cross-filter |

**Cache 設計：**
- 擴充 `container_filter_cache` 收 4 個低基數欄位的 distinct list（同一個 UNION ALL SQL，類似現有 PJ_TYPE/PRODUCTLINENAME 的模式）
- L1 memory + L2 Redis，TTL 24h
- Cross-filter（低基數欄位互鎖）：因 4 個欄位都在同一張表 DW_MES_CONTAINER，cache layout 需從「flat distinct list」升級為「DISTINCT 4-tuple list」或在 server 端用 SQL 即時計算 cross-filter

**高基數欄位 UX（多行輸入 + 萬用字元）：**
- 仿 `material-trace` 的 `parseMultiLineInput` 模式 — 多行 textarea，每行/逗號分隔一筆
- 支援 `*` 萬用字元 → server 端轉成 `LIKE 'XXX%'`（Oracle）/ `ILIKE '%XXX%'` 視 pattern 而定
- 解析在 server 端（提交時驗證），不做逐字 typeahead

**API 設計：**
- 新增/擴充 `GET /api/production-history/filter-options?selected=<json>` — 給定當前低基數選擇，回傳 4 個欄位的可選值
- 主查詢 endpoint 接受新欄位（pj_functions, mfgorders 含萬用字元、lot_ids 含萬用字元、wafer_lots 含萬用字元）並寫入 `main_query.sql` 的 `EXTRA_FILTERS`

## Business / User Goal

- 讓使用者在「查詢前」就能用 Package/BOP/Function 縮小 Oracle 掃描範圍 → 降低 Oracle 負擔、縮短 query latency
- 讓 LOT/工單/Wafer LOT 在「查詢前」就能精準鎖定，不需先全表查再二階過濾
- 多行輸入支援使用者貼 Excel 一欄資料；萬用字元支援 prefix 群組（例：`MA2025*`）

## Non-goals

- 不改 WorkCenter 群組與 Equipment filter（維持二階 spool 計算）
- 不改 matrix 視覺結構
- 不改明細呈現（這是 Change 2 的範圍）
- 不引進 typeahead 即時下拉（已明確選擇 A+ 模式：多行 + 萬用字元）

## Constraints

- 依賴 Change 2 (`prod-history-detail-raw-rows`) 已 merge — spool schema 需先含 `PJ_FUNCTION`
- Cache 啟動 lock 沿用 `resource_history_duckdb_cache._try_lock` 模式（多 worker 安全）
- Wildcard 萬用字元的 server-side validation 必須防 SQL injection
- Oracle 高基數欄位 `LIKE` 查詢需評估是否要加 `ROWNUM` 限制以避免使用者輸入過寬 pattern

## Known Context

- `container_filter_cache` 已存在並運作良好（Redis L2 + memory L1，TTL 24h）
- `material-trace` 的 `parseMultiLineInput` 與 `forwardInputType` 為 UX 參考
- `main_query.sql` 的 `EXTRA_FILTERS` placeholder 已支援動態擴充
- `production_history_service._build_extra_filters` 是新加 filter 的單一切入點

## Open Questions

1. Cross-filter 是「即時 API 計算」還是「前端 cache full 4-tuple list 後 in-memory filter」？傾向前者（cache payload 小、邏輯集中）
2. Function (PJ_FUNCTION) 是否設為必選或保持選填？傾向選填（與 Package/BOP 一致）
3. 萬用字元規則：只支援 `*` 作為前綴/後綴 `LIKE 'X%'` / `LIKE '%X'` / `LIKE '%X%'`？還是支援多段 `*`？傾向支援單個 `*` 在任意位置（最常見用例）
4. 二階 filter 在升階後仍保留還是移除？傾向移除（避免雙重 UI 混淆），但 WorkCenter 群組 / Equipment 留二階

## Requested Delivery Date / Priority

優先：中（待 Change 2 完成後啟動）

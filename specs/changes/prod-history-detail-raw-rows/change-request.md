# Change Request

## Original Request

將 production-history 明細資料的呈現從「GROUP BY 後 MIN/MAX/SUM 聚合」改為「原始 LOTWIPHISTORY 列」，以維持資料正確不誤判。

**現況** (`src/mes_dashboard/sql/production_history/main_query.sql`):
```sql
SELECT c.CONTAINERNAME, c.PJ_TYPE, ...,
       MIN(h.TRACKINTIMESTAMP)  AS TRACKIN_TS,
       MAX(h.TRACKOUTTIMESTAMP) AS TRACKOUT_TS,
       MAX(h.TRACKINQTY)        AS TRACKIN_QTY,
       SUM(h.TRACKOUTQTY)       AS TRACKOUT_QTY
FROM ... GROUP BY CONTAINERNAME, PJ_TYPE, PJ_BOP, MFGORDERNAME, FIRSTNAME,
                   PRODUCTLINENAME, WORKCENTERNAME, SPECNAME, EQUIPMENTID, EQUIPMENTNAME
```

**目標**: 移除 GROUP BY，每筆 partial track-out 都是獨立一列：
```sql
SELECT c.CONTAINERNAME, c.PJ_TYPE, c.PJ_BOP, c.PJ_FUNCTION,
       c.MFGORDERNAME, c.FIRSTNAME, c.PRODUCTLINENAME,
       h.WORKCENTERNAME, h.SPECNAME, h.EQUIPMENTID, h.EQUIPMENTNAME,
       h.TRACKINTIMESTAMP, h.TRACKOUTTIMESTAMP,
       h.TRACKINQTY, h.TRACKOUTQTY
FROM ... -- 無 GROUP BY
```

連帶影響：
- Matrix 聚合改在 DuckDB 端做 `COUNT(DISTINCT CONTAINERNAME)`（事實上現況就已經在 DuckDB 端做，邏輯不變）
- Spool schema 略變（同樣欄位，但會多含 `PJ_FUNCTION` 給 Change 3 用）
- Parquet 檔變大（按 partial track-out 比例 N 倍）
- CSV export 也使用原始列
- 所有 parity/safety/contract 測試需 rebase

## Business / User Goal

避免使用者因明細聚合產生誤判：
- 原本 `TRACKIN_QTY = MAX(TRACKINQTY)` 假設「首筆 partial = 原始批量」；若 DWH 紀錄非單調遞減（中途併批等情境），會給出錯誤的「進站量」
- 原本 `TRACKIN_TS = MIN, TRACKOUT_TS = MAX` 把多次 partial 折成一段區間，使用者看不到細部時間軸
- 改成原始列後，使用者可直接從明細看見每次 partial 的 in/out 時間與數量，無歧義

## Non-goals

- 不改 matrix 視覺結構（仍是 WC → Spec → Equipment × Month tree）
- 不改 filter 架構（保持現有一階 Type + 日期，二階 6 個 supplementary — 這是 Change 3 的範圍）
- 不引進新欄位給使用者 filter（除了 `PJ_FUNCTION` 預先納入 spool schema 為 Change 3 鋪路）
- 不調整前端任何 component 結構（只調整 detail table 顯示欄位順序/格式如果需要）

## Constraints

- 依賴 Change 1 (`migrate-production-history-ts`) 已 merge — 後端 SQL 變更前 frontend 必須先 TS
- Heavy query slot、memory guard 等既有限制全部保留
- spool row 數可能放大 N 倍，需評估對 Parquet 大小與 DuckDB query latency 的影響並寫進 test plan

## Known Context

- Oracle → spool → DuckDB 三段架構不變
- `production_history_sql_runtime.py` 的 `compute_detail_page`、`compute_matrix_view`、`stream_export`、`_build_filter_where` 都會受影響
- 既有的 Python parity test、safety test 需 rebase
- 既有的 contract tests（response shape）需確認 detail row schema 是否變更（預期不變，只是 row 數量行為不同）

## Resolved Decisions (2026-05-14, user-confirmed)

1. matrix 的 `count` 欄位 **維持 `COUNT(DISTINCT CONTAINERNAME)`** — lot 數對使用者較直覺；DuckDB 端不變。
2. detail-table **不新增 "partial #" 欄位** — 純依 `TRACKIN_TS` 排序，使用者自行判讀順序。

## Requested Delivery Date / Priority

優先：中（待 Change 1 完成後啟動）

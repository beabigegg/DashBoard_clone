# Change Request

## Original Request

前幾個提案我們把 production-history 的明細列表中的聚合取消了, 但是我現在想到一個比較好的聚合方式:

**聚合條件**: 同 LOT ID / 同 SPEC / 同機台 / 同 TRACK IN 時間 / 同 TRACK IN QTY 那就可聚合
**聚合方式**: 取這些的最後一筆 TRACK OUT 時間 + 每筆的 TRACK OUT 數量加總
**目的**: 處理一次上機多次下機 (partial trackout) 的問題

**反例 (不可聚合)**: 同 LOT ID / 同 SPEC / 同機台但是不同 TRACK IN 時間/TRACK IN 數量就不可聚合。因為有可能是 A LOT 做一半先下機, 機台改作 B LOT, 然後 B LOT 做完後又將 A LOT 上機繼續作業。這種情況下為了避免 B LOT 資訊的缺失及判讀問題, 就不做聚合。

**額外決定（討論後加入）**:

- **嚴格守門**：群組內非鍵欄位 (`work_order`, `wafer_lot`, `pj_type`, `pj_bop`, `pj_function`, `package_name`, `workcenter`, `equipment_name`) 必須全部一致才聚合；若任一欄位在群組內出現差異，該群組退回 raw rows 不合併（避免遮蔽 MES 資料異常）。
- **新增 `partial_count` 欄位**：群組內筆數。前端 DataTable 在 `partial_count > 1` 時顯示徽章，告訴工程師這列是合併過的（避免工程師看到 trackout_qty=trackin_qty 就誤判只下機一次）。

## Business / User Goal

讓 production-history 明細表回到「一次上機 = 一列」的可讀性，同時不犧牲 A/B lot 交錯上機場景的判讀正確性。

## Non-goals

- 不修改 Oracle/spool 的 parquet schema（純 view 層聚合，不需要 parquet 清檔）。
- 不修改 matrix view / AI query / filter options 等其他端點的計算邏輯。
- 不修改 spec.md 或 contracts 中明細表的欄位語意（仍是「一次生產 session」一列，只是把 partial trackout 合併視為同一個 session）。

## Constraints

- 三條路徑必須同步：DuckDB SQL 主路徑 (`compute_detail_page`)、pandas fallback (`_pandas_detail_page`)、CSV 匯出（位置待 Step 2 classifier 標明）。
- `pagination.total_rows` 必須改為聚合後筆數，不是 raw rows 計數。
- 嚴格守門失敗（非鍵欄位有差異）時必須能在 log 中留下足跡（至少 INFO 等級），方便事後追查 MES 資料異常。

## Known Context

- 上一個相關 change：`specs/archive/2025/prod-history-detail-raw-rows/` — 移除舊的 4 鍵聚合（lot+spec+equipment+date）改為 raw rows，並重命名了 7 個 Oracle 欄位 → API JSON 鍵的對映層。本案的聚合鍵是新的 5 鍵（多了 trackin_time + trackin_qty），語意上更精準。
- 後端 SQL → API 重命名層位於 [production_history_sql_runtime.py:184-205, 242-251](src/mes_dashboard/services/production_history_sql_runtime.py#L184-L205) — 本案不變動該對映，只在 SELECT 外加 GROUP BY 子查詢。
- 前端 DataTable 共用元件位置待 classifier 確認。

## Open Questions

1. CSV 匯出走的是哪條路徑？（後端 service？前端 client-side？）需 classifier 在 context-manifest 中標明。
2. 嚴格守門失敗的群組要不要顯示一個「資料異常」flag 給前端？還是只記 log？（傾向只記 log，避免污染 UI）
3. `partial_count` 是否要進 API contract？（傾向 yes，因為前端要靠它決定徽章顯示）

## Requested Delivery Date / Priority

- 優先級：中（影響日常工程師查報表時的閱讀體驗，但無資料正確性風險，因為 raw rows 仍是正確的，只是視覺上重複）。
- 無硬性 delivery date。

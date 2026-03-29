## Context

Phase 3 已移除 `apply_view()` 的 pandas fallback，DuckDB SQL runtime 為唯一 view engine。但 `execute_primary_query()` 的 Oracle cold-start 路徑仍保留完整 pandas 衍生邏輯：Oracle 查詢 → DataFrame → `_derive_*()` → 組裝 response。這條路徑是 RAM spike 的最大來源（DataFrame 可達數百 MB），且在 Phase 3 之後已不再是唯一回傳來源——DuckDB runtime 可從 spool 即時計算相同結果。

四個受影響域：
- **resource-history**：`_derive_summary()` / `_derive_detail()` + `_get_cached_df()` Redis 讀寫
- **hold-history**：`_derive_all_views()` + `_get_cached_df()` Redis 讀寫
- **yield-alert**：`_build_summary_and_trend()` / `_build_alerts_view()` / `_build_heatmap_data()` 等 pandas 衍生
- **reject-history**：`_build_primary_response()` 的 `_derive_analytics_raw()` / `_derive_summary_from_analytics()` / `_derive_trend_from_analytics()`，以及 batch pareto / export 的 `_allow_legacy_fallback()` gate

## Goals / Non-Goals

**Goals:**
- 移除 `execute_primary_query()` 中的 pandas `_derive_*()` 衍生路徑
- 移除 `_get_cached_df()` / Redis 大型 DataFrame 存取
- 重構 `execute_primary_query()` 為 spool-only：Oracle → spool 落盤 → 呼叫 DuckDB `apply_view()` → 回傳 computed result
- 保持 API response 結構不變（前端零感知）
- 移除已無呼叫者的 pandas helper 函式

**Non-Goals:**
- 不修改 `apply_view()` 或 DuckDB SQL runtime（Phase 3 已穩定）
- 不修改前端 410 re-query 行為（Phase 4 已 governance）
- 不移除 Oracle 查詢本身（仍需從 Oracle 取得原始資料落 spool）
- 不處理 `production-history` / `material-trace` / `MSD`（已達標或架構不同）
- 不移除 filter cache 或 metadata Redis（僅移除 large DataFrame Redis）

## Decisions

### D1: `execute_primary_query()` 統一為 spool → DuckDB 回傳

**決定**：`execute_primary_query()` 完成 Oracle 查詢 + spool 落盤後，直接呼叫該域的 DuckDB `apply_view()` 取得 computed result 作為 response，不再用 pandas 衍生。

**替代方案**：只回傳 `query_id`，讓 route 另外呼叫 `apply_view()`。
**否決原因**：resource / hold / yield-alert 的 route 目前直接回傳 `execute_primary_query()` 的結果，改變回傳結構會影響 route 層，增加變更範圍。

### D2: 逐域實作，resource-history 先行

**決定**：按 resource → hold → yield-alert → reject 順序逐域實作。

**原因**：resource-history 的 `_derive_*()` 最獨立（6 個 pure function），改造難度最低，可作為模式驗證。reject 最複雜（有 batch pareto / export 殘留），放最後。

### D3: pandas helper 函式移除策略

**決定**：僅移除「所有呼叫者都已消失」的 pandas 函式。若函式仍有其他呼叫者（如 batch pareto / export），保留但標註為 legacy。

**驗證方法**：對每個 `_derive_*()` 函式執行 grep 確認呼叫者數量，零呼叫者才刪除。

### D4: Redis large DataFrame 清理

**決定**：移除 `_get_cached_df()` 函式與對應的 `redis.set(query_id, pickled_df)` 寫入。保留 `_dataset_cache.set(query_id, True)` metadata marker（L1 cache）。

**原因**：metadata marker 用於 spool 存在性快速檢查，成本極低（幾 bytes），不需移除。

### D5: reject-history `_allow_legacy_fallback()` 全面移除

**決定**：Phase 3 已從 view path 移除 legacy fallback gate。本 Phase 移除 batch pareto（L2024）和 export（L2181）中殘留的 `_allow_legacy_fallback()` 呼叫，以及函式本身。

**前提**：batch pareto 和 export 已有 DuckDB 路徑可用。需驗證。

## Risks / Trade-offs

**[R1] DuckDB 與 pandas 數值精度差異** → 回歸測試覆蓋 summary / trend / kpi 欄位的數值比對。已知 DuckDB 的 DOUBLE 與 pandas float64 在極端值時有 ulp 級差異，但 Phase 3 已驗證 view path 無問題。

**[R2] `execute_primary_query()` 回傳時間增加** → spool 落盤後再跑一次 DuckDB query。但 DuckDB 對 local parquet 的查詢通常在 100ms 以內，相對 Oracle 查詢的秒級延遲可忽略。

**[R3] reject batch pareto / export 的 legacy path 移除** → 需確認 DuckDB path 已覆蓋所有 export 場景。若未覆蓋，保留 `_allow_legacy_fallback()` 作為 emergency escape hatch。

**[R4] 測試覆蓋率** → 現有測試可能 mock 了 pandas 路徑。移除後需更新測試，確保測試走 DuckDB path。

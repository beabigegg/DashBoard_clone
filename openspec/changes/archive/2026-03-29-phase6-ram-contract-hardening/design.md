## Context

`page_query_architecture` 的五個 phase 已把大多數 heavy historical flow 收斂到 `RQ -> spool -> DuckDB` 或 `sync bootstrap -> spool -> DuckDB`。但審核實作後仍有三個跨模組缺口：

1. `MSD` 已被歸類為 Type B async domain，卻仍在 detail/export spool miss 時由 view route 主動補 dispatch。
2. `resource-history` 與 `hold-history` 的 Type A primary query 在產生 spool 後，如果 DuckDB/view stage 失敗，會回傳 `200` 空 payload，讓 runtime failure 被誤判成「無資料」。
3. WIP Parquet-only 路徑對 Redis key 的 canonical naming 尚未完全統一，導致 runtime、health、admin telemetry 看的 key 不一致。

這些問題不需要新的架構層，但會直接影響 phase 完成後的契約可信度、排障效率，以及 RAM/Redis 相關觀測。

## Goals / Non-Goals

**Goals:**
- 讓 MSD detail/export 在 spool miss 時完全符合 Type B view contract，只回 `410 cache_expired`，不從 view 層重送工作。
- 讓 Type A primary query 在 bootstrap 後的 DuckDB/view failure 明確失敗，而不是回空成功結果。
- 統一 WIP Parquet canonical key，讓 updater、reader、health、admin telemetry 使用同一把 Redis key。
- 補齊對應 spec 與 tasks，讓這些收尾項目可直接進入 implementation。

**Non-Goals:**
- 不重新定義 Type A / Type B 分類，也不擴大到其他 domain 的語意重構。
- 不在這個 change 內引入新的 cache backend、queue、或新的 query execution pattern。
- 不處理額外的 RAM 優化議題，例如 material-trace streaming parquet、job-query metadata-only Redis 改造；這些屬於後續優化。

## Decisions

### Decision: MSD detail/export 只保留 view endpoint 職責
MSD detail/export 目前已依賴 canonical spool，因此在 spool miss 時應回 `410 cache_expired`，由 client 依 Type B contract 回到 primary query endpoint 重新發 job。這和 `reject-history`、`material-trace` 的語意一致，也避免 route 在缺少完整原始 query context 的情況下重建工作。

替代方案是保留 route 端 `ensure_analysis_background_job()`，讓 view miss 自動補送工作。這會把 query reconstruction、job admission、以及 view contract 混在同一個 endpoint，且與現有 `query-response-semantic-contract` 明確衝突，因此不採用。

### Decision: Type A primary query 在 bootstrap/render 失敗時必須 fail loudly
`resource-history` 與 `hold-history` 的 primary query 是同步 bootstrap，不走 polling。這代表第一次 query request 本身就是唯一的 bootstrap 成功訊號；如果 spool 已經產出但 `apply_view()` 無法渲染，回 `200` 空 payload 會讓 client、operator、與測試都失去 failure 訊號。

因此本 change 採用明確 failure semantics：同步 query 若在 DuckDB/view stage 得不到有效結果，必須回報失敗，而不是 synthetic empty success。這保留 Type A「同步」特性，但把 bootstrap failure 和 truly empty dataset 分開。

替代方案是維持空 payload，並靠 log 或 telemetry 補判斷。這會繼續把 runtime fault 與 legitimate empty result 混在一起，不利於後續排錯與自動化驗證，因此不採用。

### Decision: WIP Parquet canonical key 以 helper 的 raw suffix 為單一來源
`redis_store_df()` / `redis_load_df()` 會自行套用 namespace prefix，因此呼叫端應只傳 raw suffix，例如 `data:parquet`，不能再先做一次 `get_key()`。本 change 將 runtime、availability probe、admin memory sampling 全部對齊這個 canonical rule。

替代方案是保留雙重 prefix 的 runtime key，僅在 admin/health 做兼容。這會留下永久的觀測漂移，也會讓未來清理 Redis key 時持續存在 ambiguity，因此不採用。

## Risks / Trade-offs

- [MSD 410 path 變嚴格後，若前端仍假設 409 自動補送] → 需要同步驗證現行 client 已依 Type B contract 在 410 後重發 async query。
- [Type A bootstrap failure 由 200 空結果改為明確 failure，可能暴露既有隱性問題] → 補 route/service tests，並在 rollout 前先確認呼叫端對非 200 的 handling。
- [WIP key 對齊後，舊錯誤 key 可能殘留在 Redis] → 以觀測為主，不要求 runtime 讀取舊 key；必要時可在部署說明中加入一次性清理。

## Migration Plan

1. 先修正 spec，明確記錄 MSD Type B miss contract、Type A bootstrap failure semantics、以及 WIP canonical key rule。
2. 修改 MSD route，移除 detail/export miss path 的 auto-dispatch side effect，統一回 `410 cache_expired`。
3. 修改 resource/hold primary query service，讓 bootstrap render failure 回 explicit failure，不再合成空 payload。
4. 修改 WIP cache updater/reader、health check、admin telemetry，使其全部使用 canonical Parquet key。
5. 補 route/service/admin tests，確認 API contract 與 observability 一致。
6. 部署後以 admin performance detail 與 cache health 檢查 canonical key 是否一致、MSD 410 miss path 是否正確。

Rollback 方式維持單純：若新語意造成 client 問題，可回退本 change；不涉及資料遷移或 schema 變更。

## Open Questions

- Type A bootstrap failure 的最終 HTTP/status payload 是否沿用現有 `runtime_error` helper，或在該 domain 定義更明確的 failure code，需在 implementation 時依現有 response helper 最小變更原則決定。
- 若 Redis 中已存在雙前綴 WIP key，是否需要在本 change 中附帶一次性 cleanup，或交由 ops 在部署後觀測與清理，可在實作時視風險決定。

# Change Request

## Original Request

修正所有 admin dashboard 相關問題：
1. log 資訊僅數筆——已同步到 MySQL 就看不到了（log_store.query_logs_all() 仍過濾 synced=0）
2. 抓人員的登入登出紀錄有問題——SQLite cleanup 24h 後刪除已同步 session，KPI 歷史資料斷裂
3. Redis 監控缺口（evicted_keys、expired_keys、mem_fragmentation_ratio、SLOWLOG）
4. DuckDB 零監控（無 temp dir 磁碟用量、無 memory limit 狀態）
5. Log 分頁在 merge 模式下頁碼錯亂（offset 在 merge 排序後才套用）

## Business / User Goal

Admin 人員能在 dashboard 看到完整的系統 log、登入歷史與資源監控數據，不因同步機制而丟失資訊。

## Non-goals

- 不重構 SyncWorker 整體架構
- 不新增 MySQL 強制依賴（MySQL 未設定時系統仍正常運作）
- 不改動 Oracle / RQ worker 邏輯

## Constraints

- MySQL 為可選外部依賴；所有查詢必須在 MySQL 未設定時 graceful degrade 回 SQLite-only 路徑
- 不破壞現有 `/admin/api/logs`、`/admin/api/user-usage-kpi` API 回應結構（前端不需改動 schema）
- SQLite cleanup 保留期延長需評估磁碟用量影響

## Known Context

根因分析（本次 session 已完成）：
- log_store.py `query_logs_all()` line 539：WHERE synced = 0 → 已同步 log 不可見
- cleanup_synced() 1h 後物理刪除已同步 log；login_session cleanup 24h 後刪除
- SyncWorker 首次部署執行 TRUNCATE dashboard_login_sessions（需加保護）
- Redis: 缺 evicted_keys, expired_keys, mem_fragmentation_ratio, SLOWLOG GET
- DuckDB: duckdb_runtime.py 僅為 connection factory，無任何 telemetry

## Open Questions

- SQLite log cleanup 保留期建議從 1h 延長至多久？（建議 24h，與 session 一致）
- DuckDB temp dir 磁碟用量門檻告警值？

## Requested Delivery Date / Priority

高優先，盡快修正

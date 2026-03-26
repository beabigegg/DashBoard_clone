## Phase 1: LineageEngine 模組建立

- [x] 1.1 建立 `src/mes_dashboard/sql/lineage/split_ancestors.sql`（CONNECT BY NOCYCLE，含 recursive WITH 註解替代方案）
- [x] 1.2 建立 `src/mes_dashboard/sql/lineage/merge_sources.sql`（從 `mid_section_defect/merge_lookup.sql` 遷移，改用 `{{ FINISHED_NAME_FILTER }}` 結構參數）
- [x] 1.3 建立 `src/mes_dashboard/services/lineage_engine.py`：`resolve_split_ancestors()`、`resolve_merge_sources()`、`resolve_full_genealogy()` 三個公用函數，使用 `QueryBuilder` bind params + `ORACLE_IN_BATCH_SIZE=1000` 分批
- [x] 1.4 LineageEngine 單元測試：mock `read_sql_df` 驗證 batch 分割、dict 回傳結構、LEVEL <= 20 防護

## Phase 2: mid-section-defect 切換到 LineageEngine

- [x] 2.1 在 `mid_section_defect_service.py` 中以 `LineageEngine.resolve_split_ancestors()` 取代 `_bfs_split_chain()`
- [x] 2.2 以 `LineageEngine.resolve_merge_sources()` 取代 `_fetch_merge_sources()`
- [x] 2.3 以 `LineageEngine.resolve_full_genealogy()` 取代 `_resolve_full_genealogy()`
- [x] 2.4 Golden test：選取 ≥5 個已知血緣結構 LOT，比對 BFS vs CONNECT BY 輸出的 `child_to_parent` 和 `cid_to_name` 結果集合完全一致
- [x] 2.5 標記 `sql/mid_section_defect/genealogy_records.sql` 和 `sql/mid_section_defect/split_chain.sql` 為 deprecated（檔案頂部加 `-- DEPRECATED: replaced by sql/lineage/split_ancestors.sql`）

## Phase 3: query-tool SQL injection 修復

- [x] 3.1 建立 `sql/query_tool/lot_resolve_id.sql`、`lot_resolve_serial.sql`、`lot_resolve_work_order.sql` SQL 檔案（從 inline SQL 遷移到 SQLLoader 管理）
- [x] 3.2 修復 `_resolve_by_lot_id()`：`_build_in_filter()` → `QueryBuilder.add_in_condition()` + `SQLLoader.load_with_params()` + `read_sql_df(sql, builder.params)`
- [x] 3.3 修復 `_resolve_by_serial_number()`：同上模式
- [x] 3.4 修復 `_resolve_by_work_order()`：同上模式
- [x] 3.5 修復 `get_lot_history()` 內部 IN 子句：改用 `QueryBuilder`
- [x] 3.6 修復 lot-associations 查詢路徑（`get_lot_materials()` / `get_lot_rejects()` / `get_lot_holds()` / `get_lot_splits()` / `get_lot_jobs()`）中涉及使用者輸入的 IN 子句：改用 `QueryBuilder`
- [x] 3.7 修復 `lot_split_merge_history` 查詢：改用 `QueryBuilder`
- [x] 3.8 刪除 `_build_in_filter()` 和 `_build_in_clause()` 函數
- [x] 3.9 驗證：`grep -r "_build_in_filter\|_build_in_clause" src/` 回傳 0 結果
- [x] 3.10 更新既有 query-tool 路由測試的 mock 路徑

## Phase 4: query-tool rate limit + cache

- [x] 4.1 在 `query_tool_routes.py` 為 `/resolve` 加入 `configured_rate_limit(bucket='query-tool-resolve', default_max_attempts=10, default_window_seconds=60)`
- [x] 4.2 為 `/lot-history` 加入 `configured_rate_limit(bucket='query-tool-history', default_max_attempts=20, default_window_seconds=60)`
- [x] 4.3 為 `/lot-associations` 加入 `configured_rate_limit(bucket='query-tool-association', default_max_attempts=20, default_window_seconds=60)`
- [x] 4.4 為 `/adjacent-lots` 加入 `configured_rate_limit(bucket='query-tool-adjacent', default_max_attempts=20, default_window_seconds=60)`
- [x] 4.5 為 `/equipment-period` 加入 `configured_rate_limit(bucket='query-tool-equipment', default_max_attempts=5, default_window_seconds=60)`
- [x] 4.6 為 `/export-csv` 加入 `configured_rate_limit(bucket='query-tool-export', default_max_attempts=3, default_window_seconds=60)`
- [x] 4.7 為 resolve 結果加入 L2 Redis cache（key=`qt:resolve:{input_type}:{values_hash}`, TTL=60s）

## Phase 5: lot_split_merge_history fast/full 雙模式

- [x] 5.1 修改 `sql/query_tool/lot_split_merge_history.sql`：加入 `{{ TIME_WINDOW }}` 和 `{{ ROW_LIMIT }}` 結構參數
- [x] 5.2 在 `query_tool_service.py` 中根據 `full_history` 參數選擇 SQL variant（fast: `AND h.TXNDATE >= ADD_MONTHS(SYSDATE, -6)` + `FETCH FIRST 500 ROWS ONLY`，full: 無限制 + `read_sql_df_slow`）
- [x] 5.3 在 `query_tool_routes.py` 的 `/api/query-tool/lot-associations?type=splits` 路徑加入 `full_history` query param 解析，並傳遞到 split-merge-history 查詢
- [x] 5.4 路由測試：驗證 fast mode（預設）和 full mode（`full_history=true`）的行為差異

## Phase 6: EventFetcher 模組建立

- [x] 6.1 建立 `src/mes_dashboard/services/event_fetcher.py`：`fetch_events(container_ids, domain)` + cache key 生成 + rate limit config
- [x] 6.2 遷移 `mid_section_defect_service.py` 的 `_fetch_upstream_history()` 到 `EventFetcher.fetch_events(cids, "upstream_history")`
- [x] 6.3 遷移 query-tool event fetch paths 到 `EventFetcher`（`get_lot_history`、`get_lot_associations` 的 DB 查詢部分）
- [x] 6.4 EventFetcher 單元測試：mock DB 驗證 cache key 格式、rate limit config、domain 分支

## Phase 7: 清理與驗證

- [x] 7.1 確認 `genealogy_records.sql` 和 `split_chain.sql` 無活躍引用（`grep -r` 確認），保留 deprecated 標記
- [x] 7.2 確認所有含使用者輸入的查詢使用 `QueryBuilder` bind params（grep `read_sql_df` 呼叫點逐一確認）
- [x] 7.3 執行完整 query-tool 和 mid-section-defect 路由測試，確認無 regression

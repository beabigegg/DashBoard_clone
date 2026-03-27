## Context

MSD trace pipeline 使用 `useTraceProgress` 三階段流程：seed-resolve → lineage → events。當前架構在所有階段都在 Gunicorn worker 同步執行，沒有記憶體保護。

事故重現路徑：
1. `seed-resolve`：`_fetch_station_detection_data()` 回傳 56,796 unique lots（無上限）
2. `lineage`：`LineageEngine.resolve_full_genealogy(56,796)` 發出 ~260 個 `CONNECT BY` 查詢，產生 93,264 nodes，全部存在 Python dict 中
3. `events`：`is_msd` 豁免 CID limit，嘗試對 93,264 CIDs 做 event fetch
4. 記憶體 86.8% → 94.2%，系統掛掉

系統中已有成熟的大查詢保護架構（reject 頁面的 7 層防護），包含 `batch_query_engine`、`query_spool_store`、`async_query_job_service`、DuckDB runtime 等。MSD 需要複用這些基礎設施。

**限制條件：**
- LineageEngine 是共用元件，`query_tool_service`（max 100 lots）和 `production_history_service`（手動輸入）也在使用，修改不能影響小規模調用的效能
- 前端 `useTraceProgress` 已支援 async polling + NDJSON streaming，不需要改前端
- MSD async job 基礎設施 (`msd_query_job_service.py`) 已存在但只包裝舊的 `query_analysis()` 直接路徑

## Goals / Non-Goals

**Goals:**
- MSD 查詢不論規模大小都不會導致 Gunicorn worker OOM
- 大規模 lineage 解析（>5K seeds）搬到 RQ worker 隔離執行
- lineage 結果 spool 到 parquet，後續 aggregation 用 DuckDB
- 移除 trace events 的 `is_msd` CID limit 豁免，統一走 async fallback
- 保持小規模查詢的效能不變（<5K seeds 走 sync 原路徑）

**Non-Goals:**
- 不重構 LineageEngine 的 SQL 查詢邏輯（`CONNECT BY NOCYCLE` 本身沒問題）
- 不改動前端（`useTraceProgress` 已足夠）
- 不改動 `query_tool_service` 和 `production_history_service` 的 lineage 調用
- 不改動 MSD 的 `/analysis` 舊路徑（已有獨立 async job）

## Decisions

### Decision 1: Lineage 階段加入 seed count 閥值 + 分流

**選擇：** 在 `trace_routes.py /lineage` endpoint 加入 seed count 檢查，超過閥值時 enqueue lineage job 到 RQ worker。

**閥值：** `LINEAGE_SEED_ASYNC_THRESHOLD` = 5,000（env var 可調）

**理由：**
- 5K seeds 的 lineage 解析大約需要 5-10 個 Oracle batch query（5K/1000），在 Gunicorn worker 中可接受
- 56K seeds（事故規模）需要 ~60 batch queries + merge expansion，必須隔離
- 閥值放在 route 層而非 engine 層，因為 async 分流是 HTTP 層決策

**替代方案（未採用）：**
- 在 LineageEngine 內部做 async：破壞了 engine 的純計算職責
- 固定拒絕大查詢（HTTP 413）：損失查詢完整性，使用者無法分析大範圍資料

### Decision 2: Lineage 結果 spool 到 Parquet

**選擇：** lineage job 完成後，將 graph 結構（ancestors、cid_to_name、parent_map 等）序列化為 parquet 存 `query_spool_store`，後續 events/aggregation 從 parquet 讀取。

**序列化格式：** lineage graph → edge list DataFrame（columns: `seed_cid`, `ancestor_cid`, `edge_type`, `cid_name`）→ parquet

**理由：**
- 複用現有 `query_spool_store.py` 基礎設施（TTL、容量管理、atomic write）
- Edge list 是最自然的 graph 表示，可用 DuckDB 做 aggregation
- Parquet 壓縮後記憶體佔用極小（93K edges ≈ 幾 MB）

### Decision 3: LineageEngine 加入 admission control

**選擇：** 在 `resolve_full_genealogy()` 和 `resolve_forward_tree()` 入口加入：
1. `LINEAGE_MAX_SEED_COUNT` hard limit（default 80,000）— 超過直接拒絕
2. RSS guard — 呼叫 `process_rss_mb()` 檢查，RSS > 閥值時拒絕（raise MemoryError）
3. 進度 logging — 每 1000 seeds batch 完成後 log 進度

**理由：**
- Hard limit 防止極端情況（如資料異常產生百萬級 seed）
- RSS guard 讓 engine 在系統已高壓時提前拒絕，而非等到 worker_memory_guard 太晚介入
- 這是 engine 層的 last-resort 保護，正常流量不會觸發（route 層已在 5K 時分流）

### Decision 4: trace_routes /events 移除 MSD 豁免

**選擇：** 刪除 `if is_msd and cid_count > TRACE_EVENTS_CID_LIMIT: (log warning only)` 的特殊路徑，MSD 與其他 profile 一致：超過 CID limit 時自動嘗試 async fallback，async 不可用才回 413。

**理由：**
- 原本 MSD 豁免的理由是「需要所有 CIDs 做準確統計」，但 async job 可以完整處理所有 CIDs，只是移到 RQ worker 執行
- 豁免是事故的直接原因之一

### Decision 5: 複用 batch_query_engine 做 lineage 分批

**選擇：** lineage RQ job 內部使用 `decompose_by_ids()` 將 seed CIDs 分成 1000-lot 批次，逐批呼叫 `resolve_split_ancestors()`，每批結果 append 到 parquet spool。

**理由：**
- `batch_query_engine.py` 已有成熟的分批 + 進度追蹤 + partial failure 機制
- 逐批 spool 保證記憶體上界 = 1 batch 的 lineage graph（~1000 lots 的 ancestors）
- merge_sources 在所有 split ancestors 完成後再統一執行（需要完整 ancestor set）

## Risks / Trade-offs

**[Risk] Lineage parquet 序列化增加延遲** → 93K edges 的 parquet write ≈ 100ms，相對於 60s+ 的 lineage 解析時間可忽略

**[Risk] 分批 lineage 的 merge expansion 不完整** → merge_sources 必須在所有 split batches 完成後統一執行，不能分批。設計中已考慮：先分批做 split_ancestors spool，再一次性做 merge resolution

**[Risk] RQ worker 記憶體也可能不足** → MSD RQ worker 的 systemd service 已設 `MemoryMax=4G`，且分批處理確保峰值記憶體 << 全量。若仍不足可調低 batch size

**[Trade-off] 大查詢從即時變成 async polling** → 使用者體驗變化：大範圍查詢需要等待（但系統不會掛掉）。前端已有 polling UI，不需要額外工作

**[Trade-off] Lineage hard limit 可能拒絕極端查詢** → 80K seed limit 覆蓋 99.9%+ 的正常使用場景。若有合理需求可調高 env var

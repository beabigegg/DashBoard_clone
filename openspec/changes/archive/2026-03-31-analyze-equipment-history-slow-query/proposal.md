## Why

「設備歷史績效」POST /query 在 canonical spool 未命中時須等待 Oracle 查詢完成，依查詢天數可長達數十秒甚至逾分鐘。調查過程中同時發現：全專案所有重查詢的分片執行均為序列（`parallel=1` 且無 env 管理），以及分片失敗時資料靜默缺失的系統性問題，一併納入本次修正範圍。

## What Changes

- **修正** canonical spool TTL 偏短（15 分鐘）導致頻繁 Oracle fallback 的問題
- **改善** 長時間範圍查詢（>10 天）base 與 OEE 分片皆為序列執行，缺乏跨類型平行度
- **評估** OEE SQL（`oee_facts.sql`）的 ±30 天 reject 視窗是否可縮小或以物化彙總取代
- **擴大** warmup 窗口以覆蓋使用者常用的歷史查詢範圍
- **統一** 全專案所有重查詢服務的 parallel 改為 env var 管理（比照 `REJECT_ENGINE_PARALLEL` 模式）
- **修正** 分片 OOM（>192 MB）或失敗時資料靜默缺失問題——`execute_plan` 的 partial failure 必須傳遞到 response `_meta`，不得靜默丟棄

## Capabilities

### New Capabilities
- `resource-history-query-diagnostics`: 量化並暴露 resource-history POST /query 各段耗時與 spool 命中率，作為後續優化決策依據

### Modified Capabilities
- `resource-history-page`: 查詢路徑效能優化——調整 TTL、批次平行度、OEE 查詢策略
- `batch-query-resilience`: 擴充 partial failure 傳遞契約——所有重查詢服務須讀取 execute_plan 後的 progress metadata 並在 response 帶出警告

## Impact

**已確認的根因（按嚴重度排列）**

| # | 根因 | 影響服務 |
|---|------|---------|
| 1 | **Canonical spool TTL 短（15 分鐘）** | resource-history |
| 2 | **長範圍查詢 base + OEE 分片全序列** | resource-history |
| 3 | **OEE SQL ±30 天 reject 窗口** | resource-history |
| 4 | **Warmup 窗口固定最近 90 天** | resource-history |
| 5 | **Parallel 硬寫死 1，無 env 管理** | 全部（resource / hold / job / production / msd） |
| 6 | **分片失敗資料靜默缺失** | 全部（除 reject 外均未讀 partial failure） |

**受影響範圍**
- `src/mes_dashboard/routes/resource_history_routes.py`
- `src/mes_dashboard/services/resource_dataset_cache.py` — TTL、execute_plan parallel、partial failure
- `src/mes_dashboard/services/hold_dataset_cache.py` — parallel env、partial failure
- `src/mes_dashboard/services/job_query_service.py` — parallel env、partial failure
- `src/mes_dashboard/services/production_history_service.py` — parallel env、partial failure
- `src/mes_dashboard/services/mid_section_defect_service.py` — parallel env、partial failure
- `src/mes_dashboard/services/batch_query_engine.py` — _effective_parallelism 上限審查
- `src/mes_dashboard/sql/resource_history/oee_facts.sql` — reject 窗口優化
- `src/mes_dashboard/core/spool_warmup_scheduler.py` — warmup 窗口
- `src/mes_dashboard/config/constants.py` — CACHE_TTL_DATASET

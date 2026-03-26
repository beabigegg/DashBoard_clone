## Why

2026-02-25 生產環境 trace pipeline 處理 114K CIDs（TMTT 站 + 5 個月日期範圍）時，
worker 被 OOM SIGKILL（7GB VM，無 swap）。pool 隔離已完成，連線不再互搶，
但 events 階段的記憶體使用是真正瓶頸：

1. `cursor.fetchall()` 一次載入全部 rows（數十萬筆）
2. `pd.DataFrame(rows)` 複製一份
3. `df.iterrows()` + `row.to_dict()` 再一份
4. `grouped[cid].append(record)` 累積到最終 dict
5. `raw_domain_results[domain]` + `results[domain]["data"]` 在 trace_routes 同時持有雙份

114K CIDs × 2 domains，峰值同時存在 3-4 份完整資料副本，每份數百 MB → 2-4 GB 單一 domain。
7GB VM（4 workers）完全無法承受。

## What Changes

- **Admission control**：trace events endpoint 加 CID 數量上限判斷，超過閾值回 HTTP 413
- **分批處理**：`read_sql_df_slow` 改用 `cursor.fetchmany()` 取代 `fetchall()`，不建 DataFrame
- **EventFetcher 逐批 group**：每批 fetch 完立刻 group 到結果 dict，釋放 batch 記憶體
- **trace_routes 避免雙份持有**：`raw_domain_results` 與 `results` 合併為單一資料結構
- **Gunicorn workers 降為 2**：降低單機記憶體競爭
- **systemd MemoryMax**：加 cgroup 記憶體保護，避免 OOM 殺死整台 VM
- **更新 .env.example**：新增 `TRACE_EVENTS_CID_LIMIT`、`DB_SLOW_FETCHMANY_SIZE` 等 env 文件
- **更新 deploy/mes-dashboard.service**：加入 `MemoryHigh` 和 `MemoryMax`

## Capabilities

### Modified Capabilities

- `trace-staged-api`: events endpoint 加入 admission control（CID 上限）
- `event-fetcher-unified`: 分批 group 記憶體優化，取消 DataFrame 中間層

## Impact

- **後端核心**：database.py（fetchmany）、event_fetcher.py（逐批 group）、trace_routes.py（admission control + 記憶體管理）
- **部署設定**：gunicorn.conf.py、.env.example、deploy/mes-dashboard.service
- **不影響**：前端、即時監控頁、其他 service（reject_history、hold_history 等）
- **前置條件**：trace-pipeline-pool-isolation（已完成）

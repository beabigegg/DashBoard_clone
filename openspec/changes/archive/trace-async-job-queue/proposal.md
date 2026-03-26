## Why

trace pipeline 處理大量 CIDs（> 20K）時，即使經過分批處理優化（提案 1），
仍然面臨以下根本問題：

1. **同步 request-response 模型**：gunicorn 360s timeout 是硬限，lineage + events 合計可能超過 300s
2. **worker thread 被佔住**：大查詢期間 1 個 gunicorn thread 完全被佔用，降低即時頁服務能力
3. **前端無進度回饋**：使用者只能盯著 loading spinner 等 5-6 分鐘，不知道是否正常運作
4. **失敗後需完全重新執行**：中途 timeout/OOM 後，已完成的 seed-resolve 和 lineage 結果全部浪費

業界標準做法是將長時間任務放入非同步佇列（RQ/Dramatiq），API 先回 202 + job_id，
背景 worker 獨立處理，前端輪詢或 SSE 取得結果。

## What Changes

- **引入 RQ（Redis Queue）**：利用既有 Redis 基礎設施，最小化新依賴
- **新增 trace job worker**：獨立進程（systemd unit），不佔 gunicorn worker 資源
- **新增 `POST /api/trace/events-async`**：CID > 閾值時回 202 + job_id
- **新增 `GET /api/trace/job/{job_id}`**：輪詢 job 狀態（queued/running/completed/failed）
- **新增 `GET /api/trace/job/{job_id}/result`**：取得完成後的結果（分頁）
- **前端 useTraceProgress 整合**：自動判斷同步/非同步路徑，顯示 job 進度
- **Job TTL + 自動清理**：結果保留 1 小時後自動過期
- **新增 systemd unit**：`mes-dashboard-trace-worker.service`
- **更新 .env.example**：`TRACE_ASYNC_CID_THRESHOLD`、`TRACE_JOB_TTL_SECONDS`、`TRACE_WORKER_COUNT`

## Capabilities

### New Capabilities

- `trace-async-job`: 非同步 trace job 佇列（RQ + Redis）

### Modified Capabilities

- `trace-staged-api`: events endpoint 整合 async job 路由
- `progressive-trace-ux`: 前端整合 job 輪詢 + 進度顯示

## Impact

- **新增依賴**：`rq>=1.16.0,<2.0.0`（requirements.txt、environment.yml）
- **後端新增**：trace_job_service.py、trace_routes.py（async endpoints）
- **前端修改**：useTraceProgress.js（async 整合）
- **部署新增**：deploy/mes-dashboard-trace-worker.service、scripts/start_server.sh（worker 管理）
- **部署設定**：.env.example（新 env vars）
- **不影響**：其他 service、即時監控頁、admin 頁面
- **前置條件**：trace-events-memory-triage（提案 1）

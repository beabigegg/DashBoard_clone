## Context

提案 1（trace-events-memory-triage）解決了峰值記憶體問題並加入 admission control，
但 CID > 50K 的查詢被直接拒絕（HTTP 413）。
使用者仍有合理需求查詢大範圍資料（例如 TMTT 站 5 個月 = 114K CIDs）。

目前 codebase 完全沒有非同步任務基礎設施（無 Celery、RQ、Dramatiq）。
所有操作都是同步 request-response，受 gunicorn 360s timeout 硬限。

需要引入輕量級 job queue，讓大查詢在獨立 worker 進程中執行，
不佔 gunicorn thread、不受 360s timeout 限制、失敗可重試。

## Goals / Non-Goals

**Goals:**
- CID > 閾值的 trace events 查詢改走非同步 job（API 回 202 + job_id）
- 獨立 worker 進程（systemd unit），不佔 gunicorn 資源
- Job 狀態可查詢（queued/running/completed/failed）
- 結果有 TTL 自動清理，不佔 Redis 長期記憶體
- 前端自動判斷同步/非同步路徑，顯示 job 進度
- 最小新依賴（利用既有 Redis）

**Non-Goals:**
- 不做通用 task queue（只處理 trace events）
- 不做 job 重試（大查詢重試消耗巨大，失敗後使用者手動重新觸發）
- 不做 job 取消（Oracle 查詢一旦發出難以取消）
- 不做 job 持久化到 DB（Redis TTL 足夠）
- 不修改 lineage 階段（仍然同步，通常 < 120s）

## Decisions

### D1: RQ（Redis Queue）而非 Celery/Dramatiq

**決策**：使用 RQ 作為 job queue。

**理由**：
- 專案已有 Redis，零額外基礎設施
- RQ 比 Celery 輕量 10 倍（無 broker 中間層、無 beat scheduler、無 flower）
- RQ worker 是獨立 Python 進程，記憶體隔離
- API 簡單：`queue.enqueue(func, args, job_timeout=600, result_ttl=3600)`
- 社群活躍，Flask 生態整合良好

**替代方案**：
- Celery：過重，專案不需要 beat、chord、chain 等功能 → rejected
- Dramatiq：更輕量但社群較小，Redis broker 整合不如 RQ 成熟 → rejected
- 自製 threading：前面討論已排除（worker 生命週期、記憶體競爭）→ rejected

### D2: 同步/非同步分界閾值

**決策**：

| CID 數量 | 行為 |
|-----------|------|
| ≤ 20,000 | 同步處理（現有 events endpoint） |
| 20,001 ~ 50,000 | 非同步 job（回 202 + job_id） |
| > 50,000 | 非同步 job（回 202 + job_id），worker 內部分段處理 |

**env var**：`TRACE_ASYNC_CID_THRESHOLD`（預設 20000）

**理由**：
- ≤ 20K CIDs 的 events 查詢通常在 60s 內完成，同步足夠
- 20K-50K 需要 2-5 分鐘，超出使用者耐心且佔住 gunicorn thread
- > 50K 是提案 1 的 admission control 上限，必須走非同步

**提案 1 的 HTTP 413 改為 HTTP 202**：
當提案 2 實作完成後，提案 1 的 `TRACE_EVENTS_CID_LIMIT` 檢查改為自動 fallback 到 async job，
不再拒絕請求。

### D3: Job 狀態與結果儲存

**決策**：使用 RQ 內建的 job 狀態追蹤（儲存在 Redis）。

```
Job lifecycle:
  queued → started → finished / failed

Redis keys:
  rq:job:{job_id}          # RQ 內建 job metadata
  trace:job:{job_id}:meta  # 自訂 metadata（profile, cid_count, domains, progress）
  trace:job:{job_id}:result # 完成後的結果（JSON，設 TTL）
```

**env vars**：
- `TRACE_JOB_TTL_SECONDS`：結果保留時間（預設 3600 = 1 小時）
- `TRACE_JOB_TIMEOUT_SECONDS`：單一 job 最大執行時間（預設 1800 = 30 分鐘）

### D4: API 設計

```
POST /api/trace/events           ← 現有，CID ≤ 閾值時同步
POST /api/trace/events           ← CID > 閾值時回 202 + job_id（同一 endpoint）
GET  /api/trace/job/{job_id}     ← 查詢 job 狀態
GET  /api/trace/job/{job_id}/result          ← 取得完整結果
GET  /api/trace/job/{job_id}/result?domain=history&offset=0&limit=5000  ← 分頁取結果
```

**202 回應格式**：
```json
{
  "stage": "events",
  "async": true,
  "job_id": "trace-evt-abc123",
  "status_url": "/api/trace/job/trace-evt-abc123",
  "estimated_seconds": 300
}
```

### D5: Worker 部署架構

```
systemd (mes-dashboard-trace-worker.service)
  → conda run -n mes-dashboard rq worker trace-events --with-scheduler
  → 獨立進程，獨立記憶體空間
  → MemoryMax=4G（cgroup 保護）
```

**env vars**：
- `TRACE_WORKER_COUNT`：worker 進程數（預設 1）
- `TRACE_WORKER_QUEUE`：queue 名稱（預設 `trace-events`）

### D6: 前端整合

`useTraceProgress.js` 修改：

```javascript
// events 階段
const eventsResp = await fetchStage('events', payload)
if (eventsResp.status === 202) {
  // 非同步路徑
  const { job_id, status_url } = eventsResp.data
  return await pollJobUntilComplete(status_url, {
    onProgress: (status) => updateProgress('events', status.progress),
    pollInterval: 3000,
    maxPollTime: 1800000,  // 30 分鐘
  })
}
// 同步路徑（現有）
return eventsResp.data
```

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| RQ 新依賴增加維護成本 | RQ 穩定、API 簡單、只用核心功能 |
| Worker 進程增加記憶體使用 | 獨立 cgroup MemoryMax=4G；空閒時幾乎不佔記憶體 |
| Redis 儲存大結果影響效能 | 結果 TTL=1h 自動清理；配合提案 3 串流取代全量儲存 |
| Worker crash 丟失進行中 job | RQ 內建 failed job registry；使用者可手動重觸發 |
| 前端輪詢增加 API 負載 | pollInterval=3s，只有 active job 才輪詢 |

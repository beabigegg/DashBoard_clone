## Why

即使有非同步 job（提案 2）處理大查詢，結果 materialize 仍然是記憶體瓶頸：

1. **job result 全量 JSON**：114K CIDs × 2 domains 的結果 JSON 可達數百 MB，
   Redis 儲存 + 讀取 + Flask jsonify 序列化，峰值記憶體仍高
2. **前端一次性解析**：瀏覽器解析數百 MB JSON 會 freeze UI
3. **Redis 單 key 限制**：大 value 影響 Redis 效能（阻塞其他操作）

串流回傳（NDJSON/分頁）讓 server 逐批產生資料、前端逐批消費，
記憶體使用與 CID 總數解耦，只與每批大小成正比。

## What Changes

- **EventFetcher 支援 iterator 模式**：`fetch_events_iter()` yield 每批結果而非累積全部
- **新增 `GET /api/trace/job/{job_id}/stream`**：NDJSON 串流回傳 job 結果
- **前端 useTraceProgress 串流消費**：用 `fetch()` + `ReadableStream` 逐行解析 NDJSON
- **結果分頁 API**：`GET /api/trace/job/{job_id}/result?domain=history&offset=0&limit=5000`
- **更新 .env.example**：`TRACE_STREAM_BATCH_SIZE`

## Capabilities

### New Capabilities

- `trace-streaming-response`: NDJSON 串流回傳 + 結果分頁

### Modified Capabilities

- `event-fetcher-unified`: 新增 iterator 模式（`fetch_events_iter`）
- `trace-staged-api`: job result 串流 endpoint
- `progressive-trace-ux`: 前端串流消費 + 逐批渲染

## Impact

- **後端核心**：event_fetcher.py（iterator 模式）、trace_routes.py（stream endpoint）
- **前端修改**：useTraceProgress.js（ReadableStream 消費）
- **部署設定**：.env.example（`TRACE_STREAM_BATCH_SIZE`）
- **不影響**：同步路徑（CID < 閾值仍走現有流程）、其他 service、即時監控頁
- **前置條件**：trace-async-job-queue（提案 2）

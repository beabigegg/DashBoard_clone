## Context

提案 2（trace-async-job-queue）讓大查詢在獨立 worker 中執行，
但結果仍然全量 materialize 到 Redis（job result）和前端記憶體。

114K CIDs × 2 domains 的結果 JSON 可達 200-500MB：
- Worker 記憶體：grouped dict ~500MB + JSON serialize ~500MB = ~1GB 峰值
- Redis：SETEX 500MB 的 key 耗時 5-10s，阻塞其他操作
- 前端：瀏覽器解析 500MB JSON freeze UI 數十秒

串流回傳讓 server 逐批產生、前端逐批消費，記憶體使用只與每批大小成正比。

## Goals / Non-Goals

**Goals:**
- Job 結果以 NDJSON 串流回傳，避免全量 materialize
- EventFetcher 支援 iterator 模式，逐批 yield 結果
- 前端用 ReadableStream 逐行解析，逐批渲染
- 結果也支援分頁 API（給不支援串流的 consumer 使用）

**Non-Goals:**
- 不改動同步路徑（CID < 閾值仍走現有 JSON 回傳）
- 不做 WebSocket（NDJSON over HTTP 更簡單、更通用）
- 不做 Server-Sent Events（SSE 只支援 text/event-stream，不適合大 payload）
- 不修改 MSD aggregation（aggregation 需要全量資料，但結果較小）

## Decisions

### D1: NDJSON 格式

**決策**：使用 Newline Delimited JSON（NDJSON）作為串流格式。

```
Content-Type: application/x-ndjson

{"type":"meta","job_id":"abc123","domains":["history","materials"],"cid_count":114892}
{"type":"domain_start","domain":"history","batch":1,"total_batches":23}
{"type":"records","domain":"history","batch":1,"data":[...5000 records...]}
{"type":"records","domain":"history","batch":2,"data":[...5000 records...]}
...
{"type":"domain_end","domain":"history","total_records":115000}
{"type":"domain_start","domain":"materials","batch":1,"total_batches":12}
...
{"type":"aggregation","data":{...}}
{"type":"complete","elapsed_seconds":285}
```

**env var**：`TRACE_STREAM_BATCH_SIZE`（預設 5000 records/batch）

**理由**：
- NDJSON 是業界標準串流 JSON 格式（Elasticsearch、BigQuery、GitHub API 都用）
- 每行是獨立 JSON，前端可逐行 parse（不需要等整個 response）
- 5000 records/batch ≈ 2-5MB，瀏覽器可即時渲染
- 與 HTTP/1.1 chunked transfer 完美搭配

### D2: EventFetcher iterator 模式

**決策**：新增 `fetch_events_iter()` 方法，yield 每批 grouped records。

```python
@staticmethod
def fetch_events_iter(container_ids, domain, batch_size=5000):
    """Yield dicts of {cid: [records]} in batches."""
    # ... same SQL building logic ...
    for oracle_batch_ids in batches:
        for columns, rows in read_sql_df_slow_iter(sql, params):
            batch_grouped = defaultdict(list)
            for row in rows:
                record = dict(zip(columns, row))
                cid = record.get("CONTAINERID")
                if cid:
                    batch_grouped[cid].append(record)
            yield dict(batch_grouped)
```

**理由**：
- 與 `fetch_events()` 共存，不影響同步路徑
- 每次 yield 只持有一個 fetchmany batch 的 grouped 結果
- Worker 收到 yield 後立刻序列化寫出，不累積

### D3: 結果分頁 API

**決策**：提供 REST 分頁 API 作為 NDJSON 的替代方案。

```
GET /api/trace/job/{job_id}/result?domain=history&offset=0&limit=5000
```

**回應格式**：
```json
{
  "domain": "history",
  "offset": 0,
  "limit": 5000,
  "total": 115000,
  "data": [... 5000 records ...]
}
```

**理由**：
- 某些 consumer（如外部系統）不支援 NDJSON 串流
- 分頁 API 是標準 REST pattern
- 結果仍儲存在 Redis（但按 domain 分 key），每個 key 5000 records ≈ 5MB

### D4: 前端 ReadableStream 消費

```javascript
async function consumeNDJSON(url, onChunk) {
  const response = await fetch(url)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()  // 保留不完整的最後一行
    for (const line of lines) {
      if (line.trim()) onChunk(JSON.parse(line))
    }
  }
}
```

**理由**：
- ReadableStream 是瀏覽器原生 API，無需額外依賴
- 逐行 parse 記憶體使用恆定（只與 batch_size 成正比）
- 可邊收邊渲染，使用者體驗好

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| NDJSON 不支援 HTTP 壓縮 | Flask 可配 gzip middleware；每行 5000 records 壓縮率高 |
| 中途斷線需重新開始 | 分頁 API 可從斷點繼續取；NDJSON 用於一次性消費 |
| 前端需要處理部分結果渲染 | 表格元件改用 virtual scroll（既有 vue-virtual-scroller） |
| MSD aggregation 仍需全量資料 | aggregation 在 worker 內部完成，只串流最終結果（較小） |
| 結果按 domain 分 key 增加 Redis key 數量 | TTL 清理 + key prefix 隔離 |

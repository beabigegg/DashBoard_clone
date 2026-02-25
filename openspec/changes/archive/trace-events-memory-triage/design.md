## Context

2026-02-25 生產環境 OOM crash 時間線：

```
13:18:15  seed-resolve (read_sql_df_slow): 525K rows → 70K lots (38.95s)
13:20:12  lineage (read_sql_df_slow): 114K CIDs, 54MB JSON (65s)
13:20:16  events (read_sql_df_slow): 2 domains × 115 batches × 2 workers
13:20:16  cursor.fetchall() 開始累積 rows → DataFrame → dict → grouped
          每個 domain 同時持有 ~3 份完整資料副本
          峰值記憶體: (fetchall rows + DataFrame + grouped dict) × 2 domains ≈ 4-6 GB
13:37:47  OOM SIGKILL — 7GB VM, 0 swap
```

pool 隔離（前一個 change）解決了連線互搶問題，但 events 階段的記憶體使用才是 OOM 根因。

目前 `read_sql_df_slow` 使用 `cursor.fetchall()` 一次載入全部結果到 Python list，
然後建 `pd.DataFrame`，再 `iterrows()` + `to_dict()` 轉成 dict list。
114K CIDs 的 upstream_history domain 可能回傳 100 萬+ rows，
每份副本數百 MB，3-4 份同時存在就超過 VM 記憶體。

## Goals / Non-Goals

**Goals:**
- 防止大查詢直接 OOM 殺死整台 VM（admission control）
- 降低 events 階段峰值記憶體 60-70%（fetchmany + 跳過 DataFrame）
- 保護 host OS 穩定性（systemd MemoryMax + workers 降為 2）
- 不改變現有 API 回傳格式（對前端透明）
- 更新部署文件和 env 設定

**Non-Goals:**
- 不引入非同步任務佇列（提案 2 範圍）
- 不修改 lineage 階段（54MB 在可接受範圍）
- 不修改前端（提案 3 範圍）
- 不限制使用者查詢範圍（日期/站別由使用者決定）

## Decisions

### D1: Admission Control 閾值與行為

**決策**：在 trace events endpoint 加入 CID 數量上限判斷，**依 profile 區分**。

| Profile | CID 數量 | 行為 |
|---------|-----------|------|
| `query_tool` / `query_tool_reverse` | ≤ 50,000 | 正常同步處理 |
| `query_tool` / `query_tool_reverse` | > 50,000 | 回 HTTP 413（實務上不會發生） |
| `mid_section_defect` | 任意 | **不設硬限**，正常處理 + log warning（CID > 50K 時） |

**env var**：`TRACE_EVENTS_CID_LIMIT`（預設 50000，僅對非 MSD profile 生效）

**MSD 不設硬限的理由**：
- MSD 報廢追溯是聚合統計（pareto/表格），不渲染追溯圖，CID 數量多寡不影響可讀性
- 漏掉 CID 會導致報廢數量統計失準，資料完整性至關重要
- 114K CIDs 是真實業務場景（TMTT 站 5 個月），不能拒絕
- OOM 風險由 systemd `MemoryMax=6G` 保護 host OS（service 被殺但 VM 存活，自動重啟）
- 提案 2 實作後，MSD 大查詢自動走 async job，記憶體問題根本解決

**query_tool 設 50K 上限的理由**：
- 追溯圖超過數千節點已無法閱讀，50K 是極寬鬆的安全閥
- 實務上 query_tool seed 通常 1-50 lots → lineage 後幾百到幾千 CIDs

**替代方案**：
- 全 profile 統一上限 → MSD 被擋住，報廢統計不完整 → rejected
- 無上限 + 只靠 fetchmany → MSD 接受此風險（有 MemoryMax 保護）→ adopted for MSD
- 上限設太低（如 10K）→ 影響正常 MSD 查詢（通常 5K-30K CIDs）→ rejected

### D2: fetchmany 取代 fetchall

**決策**：`read_sql_df_slow` 新增 `fetchmany` 模式，不建 DataFrame，直接回傳 iterator。

```python
def read_sql_df_slow_iter(sql, params=None, timeout_seconds=None, batch_size=5000):
    """Yield batches of (columns, rows) without building DataFrame."""
    # ... connect, execute ...
    columns = [desc[0].upper() for desc in cursor.description]
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield columns, rows
    # ... cleanup in finally ...
```

**env var**：`DB_SLOW_FETCHMANY_SIZE`（預設 5000）

**理由**：
- `fetchall()` 強制全量 materialization
- `fetchmany(5000)` 每次只持有 5000 rows 在記憶體
- 不建 DataFrame 省去 pandas overhead（index、dtype inference、NaN handling）
- EventFetcher 可以 yield 完一批就 group 到結果 dict，釋放 batch

**trade-off**：
- `read_sql_df_slow`（回傳 DataFrame）保留不動，新增 `read_sql_df_slow_iter`
- 只有 EventFetcher 使用 iter 版本；其他 service 繼續用 DataFrame 版本
- 這樣不影響任何既有 consumer

### D3: EventFetcher 逐批 group 策略

**決策**：`_fetch_batch` 改用 `read_sql_df_slow_iter`，每 fetchmany batch 立刻 group 到 `grouped` dict。

```python
def _fetch_batch(batch_ids):
    builder = QueryBuilder()
    builder.add_in_condition(filter_column, batch_ids)
    sql = EventFetcher._build_domain_sql(domain, builder.get_conditions_sql())

    for columns, rows in read_sql_df_slow_iter(sql, builder.params, timeout_seconds=60):
        for row in rows:
            record = dict(zip(columns, row))
            # sanitize NaN
            cid = record.get("CONTAINERID")
            if cid:
                grouped[cid].append(record)
    # rows 離開 scope 即被 GC
```

**記憶體改善估算**：

| 項目 | 修改前 | 修改後 |
|------|--------|--------|
| cursor buffer | 全量 (100K+ rows) | 5000 rows |
| DataFrame | 全量 | 無 |
| grouped dict | 全量（最終結果） | 全量（最終結果） |
| **峰值** | ~3x 全量 | ~1.05x 全量 |

grouped dict 仍然是全量，但省去了 fetchall list + DataFrame 的兩份副本。
對於 50K CIDs × 10 events = 500K records，從 ~1.5GB 降到 ~500MB。

### D4: trace_routes 避免雙份持有

**決策**：events endpoint 中 `raw_domain_results` 直接複用為 `results` 的來源，
`_flatten_domain_records` 在建完 flat list 後立刻 `del events_by_cid`。

目前的問題：
```python
raw_domain_results[domain] = events_by_cid  # 持有 reference
rows = _flatten_domain_records(events_by_cid)  # 建新 list
results[domain] = {"data": rows, "count": len(rows)}
# → events_by_cid 和 rows 同時存在
```

修改後：
```python
events_by_cid = future.result()
rows = _flatten_domain_records(events_by_cid)
results[domain] = {"data": rows, "count": len(rows)}
if is_msd:
    raw_domain_results[domain] = events_by_cid  # MSD 需要 group-by-CID 結構
else:
    del events_by_cid  # 非 MSD 立刻釋放
```

### D5: Gunicorn workers 降為 2 + systemd MemoryMax

**決策**：
- `.env.example` 中 `GUNICORN_WORKERS` 預設改為 2
- `deploy/mes-dashboard.service` 加入 `MemoryHigh=5G` 和 `MemoryMax=6G`

**理由**：
- 4 workers × 大查詢 = 記憶體競爭嚴重
- 2 workers × 4 threads = 8 request threads，足夠處理並行請求
- `MemoryHigh=5G`：超過後 kernel 開始 reclaim，但不殺進程
- `MemoryMax=6G`：硬限，超過直接 OOM kill service（保護 host OS）
- 保留 1GB 給 OS + Redis + 其他服務

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| 50K CID 上限可能擋住合理查詢 | env var 可調；提案 2 實作後改走 async |
| fetchmany iterator 模式下 cursor 持有時間更長 | timeout_seconds=60 限制；semaphore 限制並行 |
| grouped dict 最終仍全量 | 這是 API contract（需回傳所有結果）；提案 3 的 streaming 才能根本解決 |
| workers=2 降低並行處理能力 | 歷史頁查詢是 semaphore 限制的，降 workers 主要影響即時頁 throughput（但即時頁很輕量） |
| MemoryMax kill service 會中斷所有在線使用者 | systemd Restart=always 自動重啟；比 host OS crash 好得多 |

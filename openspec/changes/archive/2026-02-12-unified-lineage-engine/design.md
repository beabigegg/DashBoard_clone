## Context

兩個高查詢複雜度頁面（`/mid-section-defect` 和 `/query-tool`）各自實作了 LOT 血緣追溯邏輯。mid-section-defect 使用 Python BFS（`_bfs_split_chain()` + `_fetch_merge_sources()`），query-tool 使用 `_build_in_filter()` 字串拼接。兩者共用的底層資料表為 `DWH.DW_MES_CONTAINER`（5.2M rows, CONTAINERID UNIQUE index）和 `DWH.DW_MES_PJ_COMBINEDASSYLOTS`（1.97M rows, FINISHEDNAME indexed）。

現行問題：
- BFS 每輪一次 DB round-trip（3-16 輪），加上 `genealogy_records.sql` 全掃描 `HM_LOTMOVEOUT`（48M rows）
- `_build_in_filter()` 字串拼接存在 SQL injection 風險
- query-tool 無 rate limit / cache，可打爆 DB pool (pool_size=10, max_overflow=20)
- 兩份 service 各 1200-1300 行，血緣邏輯重複

既有安全基礎設施：
- `QueryBuilder`（`sql/builder.py`）：`add_in_condition()` 支援 bind params `:p0, :p1, ...`
- `SQLLoader`（`sql/loader.py`）：`load_with_params()` 支援結構參數 `{{ PARAM }}`
- `configured_rate_limit()`（`core/rate_limit.py`）：per-client rate limit with `Retry-After` header
- `LayeredCache`（`core/cache.py`）：L1 MemoryTTL + L2 Redis

## Goals / Non-Goals

**Goals:**
- 以 `CONNECT BY NOCYCLE` 取代 Python BFS，將 3-16 次 DB round-trip 縮減為 1 次
- 建立 `LineageEngine` 統一模組，消除血緣邏輯重複
- 消除 `_build_in_filter()` SQL injection 風險
- 為 query-tool 加入 rate limit + cache（對齊 mid-section-defect）
- 為 `lot_split_merge_history` 加入 fast/full 雙模式

**Non-Goals:**
- 不新增 API endpoint（由後續 `trace-progressive-ui` 負責）
- 不改動前端
- 不建立 materialized view / 不使用 PARALLEL hints
- 不改動其他頁面（wip-detail, lot-detail 等）

## Decisions

### D1: CONNECT BY NOCYCLE 作為主要遞迴查詢策略

**選擇**: Oracle `CONNECT BY NOCYCLE` with `LEVEL <= 20`
**替代方案**: Recursive `WITH` (recursive subquery factoring)
**理由**:
- `CONNECT BY` 是 Oracle 原生遞迴語法，在 Oracle 19c 上執行計劃最佳化最成熟
- `LEVEL <= 20` 等價於現行 BFS `bfs_round > 20` 防護
- `NOCYCLE` 處理循環引用（`SPLITFROMID` 可能存在資料錯誤的循環）
- recursive `WITH` 作為 SQL 檔案內的註解替代方案，若 execution plan 不佳可快速切換

**SQL 設計**（`sql/lineage/split_ancestors.sql`）:
```sql
SELECT
    c.CONTAINERID,
    c.SPLITFROMID,
    c.CONTAINERNAME,
    LEVEL AS SPLIT_DEPTH
FROM DWH.DW_MES_CONTAINER c
START WITH {{ CID_FILTER }}
CONNECT BY NOCYCLE PRIOR c.SPLITFROMID = c.CONTAINERID
    AND LEVEL <= 20
```
- `{{ CID_FILTER }}` 由 `QueryBuilder.get_conditions_sql()` 生成，bind params 注入
- Oracle IN clause 上限透過 `ORACLE_IN_BATCH_SIZE=1000` 分批，多批結果合併

### D2: LineageEngine 模組結構

```
src/mes_dashboard/services/lineage_engine.py
├── resolve_split_ancestors(container_ids: List[str]) -> Dict
│   └── 回傳 {child_to_parent: {cid: parent_cid}, cid_to_name: {cid: name}}
├── resolve_merge_sources(container_names: List[str]) -> Dict
│   └── 回傳 {finished_name: [{source_cid, source_name}]}
└── resolve_full_genealogy(container_ids: List[str], initial_names: Dict) -> Dict
    └── 組合 split + merge，回傳 {cid: Set[ancestor_cids]}

src/mes_dashboard/sql/lineage/
├── split_ancestors.sql    (CONNECT BY NOCYCLE)
└── merge_sources.sql      (from merge_lookup.sql)
```

**函數簽名設計**:
- profile-agnostic：接受 `container_ids: List[str]`，不綁定頁面邏輯
- 回傳原生 Python 資料結構（dict/set），不回傳 DataFrame
- 內部使用 `QueryBuilder` + `SQLLoader.load_with_params()` + `read_sql_df()`
- batch 邏輯封裝在模組內（caller 不需處理 `ORACLE_IN_BATCH_SIZE`）

### D3: EventFetcher 模組結構

```
src/mes_dashboard/services/event_fetcher.py
├── fetch_events(container_ids: List[str], domain: str) -> List[Dict]
│   └── 支援 domain: history, materials, rejects, holds, jobs, upstream_history
├── _cache_key(domain: str, container_ids: List[str]) -> str
│   └── 格式: evt:{domain}:{sorted_cids_hash}
└── _get_rate_limit_config(domain: str) -> Dict
    └── 回傳 {bucket, max_attempts, window_seconds}
```

**快取策略**:
- L2 Redis cache（對齊 `core/cache.py` 模式），TTL 依 domain 配置
- cache key 使用 `hashlib.md5(sorted(cids).encode()).hexdigest()[:12]` 避免超長 key
- mid-section-defect 既有的 `_fetch_upstream_history()` 遷移到 `fetch_events(cids, "upstream_history")`

### D4: query-tool SQL injection 修復策略

**修復範圍**（6 個呼叫點）:
1. `_resolve_by_lot_id()` (line 262): `_build_in_filter(lot_ids, 'CONTAINERNAME')` + `read_sql_df(sql, {})`
2. `_resolve_by_serial_number()` (line ~320): 同上模式
3. `_resolve_by_work_order()` (line ~380): 同上模式
4. `get_lot_history()` 內部的 IN 子句
5. `get_lot_associations()` 內部的 IN 子句
6. `lot_split_merge_history` 查詢

**修復模式**（統一）:
```python
# Before (unsafe)
in_filter = _build_in_filter(lot_ids, 'CONTAINERNAME')
sql = f"SELECT ... WHERE {in_filter}"
df = read_sql_df(sql, {})

# After (safe)
builder = QueryBuilder()
builder.add_in_condition("CONTAINERNAME", lot_ids)
sql = SQLLoader.load_with_params(
    "query_tool/lot_resolve_id",
    CONTAINER_FILTER=builder.get_conditions_sql(),
)
df = read_sql_df(sql, builder.params)
```

**`_build_in_filter()` 和 `_build_in_clause()` 完全刪除**（非 deprecated，直接刪除，因為這是安全漏洞）。

### D5: query-tool rate limit + cache 配置

**Rate limit**（對齊 `configured_rate_limit()` 模式）:
| Endpoint | Bucket | Max/Window | Env Override |
|----------|--------|------------|-------------|
| `/resolve` | `query-tool-resolve` | 10/60s | `QT_RESOLVE_RATE_*` |
| `/lot-history` | `query-tool-history` | 20/60s | `QT_HISTORY_RATE_*` |
| `/lot-associations` | `query-tool-association` | 20/60s | `QT_ASSOC_RATE_*` |
| `/adjacent-lots` | `query-tool-adjacent` | 20/60s | `QT_ADJACENT_RATE_*` |
| `/equipment-period` | `query-tool-equipment` | 5/60s | `QT_EQUIP_RATE_*` |
| `/export-csv` | `query-tool-export` | 3/60s | `QT_EXPORT_RATE_*` |

**Cache**:
- resolve result: L2 Redis, TTL=60s, key=`qt:resolve:{input_type}:{values_hash}`
- 其他 GET endpoints: 暫不加 cache（結果依賴動態 CONTAINERID 參數，cache 命中率低）

### D6: lot_split_merge_history fast/full 雙模式

**Fast mode**（預設）:
```sql
-- lot_split_merge_history.sql 加入條件
AND h.TXNDATE >= ADD_MONTHS(SYSDATE, -6)
...
FETCH FIRST 500 ROWS ONLY
```

**Full mode**（`full_history=true`）:
- SQL variant 不含時間窗和 row limit
- 使用 `read_sql_df_slow()` (120s timeout) 取代 `read_sql_df()` (55s timeout)
- Route 層透過 `request.args.get('full_history', 'false').lower() == 'true'` 判斷

### D7: 重構順序與 regression 防護

**Phase 1**: mid-section-defect（較安全，有 cache + distributed lock 保護）
1. 建立 `lineage_engine.py` + SQL files
2. 在 `mid_section_defect_service.py` 中以 `LineageEngine` 取代 BFS 三函數
3. golden test 驗證 BFS vs CONNECT BY 結果一致
4. 廢棄 `genealogy_records.sql` + `split_chain.sql`（標記 deprecated）

**Phase 2**: query-tool（風險較高，無既有保護）
1. 修復所有 `_build_in_filter()` → `QueryBuilder`
2. 刪除 `_build_in_filter()` + `_build_in_clause()`
3. 加入 route-level rate limit
4. 加入 resolve cache
5. 加入 `lot_split_merge_history` fast/full mode

**Phase 3**: EventFetcher
1. 建立 `event_fetcher.py`
2. 遷移 `_fetch_upstream_history()` → `EventFetcher`
3. 遷移 query-tool event fetch paths → `EventFetcher`

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| CONNECT BY 對超大血緣樹 (>10000 nodes) 可能產生不預期的 execution plan | `LEVEL <= 20` 硬上限 + SQL 檔案內含 recursive `WITH` 替代方案可快速切換 |
| golden test 覆蓋率不足導致 regression 漏網 | 選取 ≥5 個已知血緣結構的 LOT（含多層 split + merge 交叉），CI gate 強制通過 |
| `_build_in_filter()` 刪除後漏改呼叫點 | Phase 2 完成後 `grep -r "_build_in_filter\|_build_in_clause" src/` 必須 0 結果 |
| fast mode 6 個月時間窗可能截斷需要完整歷史的追溯 | 提供 `full_history=true` 切換完整模式，前端預設不加此參數 = fast mode |
| QueryBuilder `add_in_condition()` 對 >1000 值不自動分批 | LineageEngine 內部封裝分批邏輯（`for i in range(0, len(ids), 1000)`），呼叫者無感 |

## Migration Plan

1. **建立新模組**：`lineage_engine.py`, `event_fetcher.py`, `sql/lineage/*.sql` — 無副作用，可安全部署
2. **Phase 1 切換**：mid-section-defect 內部呼叫改用 `LineageEngine` — 有 cache/lock 保護，regression 可透過 golden test + 手動比對驗證
3. **Phase 2 切換**：query-tool 修復 + rate limit + cache — 需重新跑 query-tool 路由測試
4. **Phase 3 切換**：EventFetcher 遷移 — 最後執行，影響範圍最小
5. **清理**：確認 deprecated SQL files 無引用後刪除

**Rollback**: 每個 Phase 獨立，可單獨 revert。`LineageEngine` 和 `EventFetcher` 為新模組，不影響既有程式碼直到各 Phase 的切換 commit。

## Open Questions

- `DW_MES_CONTAINER.SPLITFROMID` 欄位是否有 index？若無，`CONNECT BY` 的 `START WITH` 性能可能依賴全表掃描而非 CONTAINERID index。需確認 Oracle execution plan。
- `ORACLE_IN_BATCH_SIZE=1000` 對 `CONNECT BY START WITH ... IN (...)` 的行為是否與普通 `WHERE ... IN (...)` 一致？需在開發環境驗證。
- EventFetcher 的 cache TTL 各 domain 是否需要差異化（如 `upstream_history` 較長、`holds` 較短）？暫統一 300s，後續視使用模式調整。

## Context

目前專案在高量查詢上的防 OOM 手段已分散落地（slow query channel、fetchmany、RSS guard、batch chunking、spool），但「資料完整性可見化」契約未統一：

- reject-history 已有 partial-failure / failed-ranges / spool fallback 的完整語意。
- EventFetcher 使用 `__meta__` 混入 `cid -> records` map 回傳截斷資訊，下游路徑對此處理不一致。
- trace sync / async / NDJSON 與前端呈現缺少一致 metadata 傳遞規格。
- Query Tool 與 Material Trace 在高量 detail/export 路徑仍有全量 payload/materialize 問題。

這是一個跨 `services/routes/frontend/tests` 的橫切變更，且涉及行為契約、相容性、性能與可觀測性，需先設計再實作。

## Goals / Non-Goals

**Goals:**
- 定義跨工具共用的 Query Quality Meta 契約，統一描述 `complete/partial/truncated` 與原因。
- 消除 EventFetcher `__meta__` 混入資料結構的隱患，將資料與 metadata 解耦。
- 讓 trace sync、async job、NDJSON、前端都能一致接收與呈現完整性狀態。
- 補齊 Query Tool 高量明細的 server-side pagination，避免單次全量載入。
- 將 Material Trace export 改為串流輸出，保留資料完整性訊號。
- 以模組化方式提取可重用能力，讓後續查詢工具可直接沿用。

**Non-Goals:**
- 不重寫 lineage/event 演算法與 domain SQL 商業邏輯。
- 不在本變更中導入全新儲存引擎或替換現有 Redis/Parquet 架構。
- 不調整 UI 視覺風格，只新增必要警示與完整性訊息呈現。

## Decisions

### D1: 建立共用 `QueryQualityMeta` 契約並模組化
**Decision:** 新增共用模組（例如 `core/query_quality_contract.py`），定義標準欄位：
- `status`: `complete | partial | truncated | failed`
- `reasons`: string[]（如 `chunk_failure`, `row_guard_truncated`, `timeout`, `cache_partial_restore`）
- `scope`: `domain | query | export`
- `failed_domains`, `failed_ranges`, `truncated_domains`
- `fetched_rows`, `max_rows`, `retry_after_seconds`（選配）

**Rationale:** 將「資料品質訊號」從各模組私有格式提升為共用契約，避免不同 API 各說各話。

**Alternatives considered:**
- 沿用各模組既有 `meta` 自由格式：短期快，但無法跨工具治理與測試。

### D2: EventFetcher 回傳資料與 metadata 分離
**Decision:** EventFetcher 內部與對外回傳改為 `{records_by_cid, quality_meta}`，不再將 `__meta__` 塞進 records map。

**Rationale:** `Dict[str, List[Dict]]` 與 metadata 混放會導致下游迭代時型別風險，且難以驗證。

**Alternatives considered:**
- 保留 `__meta__` 並要求所有呼叫端過濾：容易遺漏且持續製造脆弱點。

### D3: Trace API（sync/async/NDJSON）端到端傳遞同一 quality meta
**Decision:**
- `/api/trace/events` 同步回應新增 `quality_meta`。
- async result 與 NDJSON 新增對應 chunk（或 meta 欄位）傳遞 quality meta。
- 前端 `useTraceProgress` 收斂為單一解析路徑，統一顯示非完整結果警示。

**Rationale:** 非同步路徑目前資訊落差最大，必須契約一致才可避免「同步看得到、串流看不到」。

**Alternatives considered:**
- 僅同步路徑支援：會造成不同執行模式下語意不一致。

### D4: MSD 正規化與聚合流程顯式忽略 metadata
**Decision:** 在 MSD 相關 normalizer/aggregation 入口，僅處理 `records_by_cid`，metadata 透過獨立參數/欄位傳遞。

**Rationale:** 從型別層切斷 meta 混入資料列的可能，避免高量截斷時例外。

### D5: Query Tool 高量明細改 server-side pagination
**Decision:** 對 high-risk detail endpoints（lot-history、lot-associations batch、equipment lots）引入 `page/per_page`，回傳 `pagination`。

**Rationale:** 防止單次全量 payload 造成記憶體與傳輸峰值；與其他報表頁一致。

**Alternatives considered:**
- 保持全量 + 僅加 RSS guard：仍會有大 payload 及使用者等待成本。

### D6: Material Trace export 改串流輸出
**Decision:** export 路徑改 generator streaming，避免 `to_csv().encode()` 全量 materialize；保留 `export_max_rows` 與截斷標記。

**Rationale:** 匯出是高記憶體尖峰來源，串流是最低風險的改善。

### D7: 沿用 reject-history 的 partial-failure 模式作為 cross-tool baseline
**Decision:** 將 `has_partial_failure/failed_chunk_count/failed_ranges` 的語意擴展為可重用 helper（不限定 reject namespace）。

**Rationale:** 現有 reject-history 已有完整測試與實戰驗證，直接抽象可降低回歸風險。

## Risks / Trade-offs

- [相容性風險：EventFetcher 回傳契約變更] → 增加過渡 adapter 與全域 grep 檢查，先改內部呼叫端再移除舊格式。
- [分頁導致舊客戶端假設失效] → 在 route 層保留明確錯誤/指引訊息，前端同步改為顯式分頁請求。
- [metadata 傳遞增加 payload 複雜度] → 統一 schema 並加型別測試，避免每條 API 各自擴充。
- [串流匯出導致錯誤處理時機變晚] → 增加 streaming 失敗保護與可觀測 log（包含 query_id/phase）。
- [跨模組改動面大] → 分階段落地（contract -> backend propagation -> frontend consumption -> performance follow-up）。

## Migration Plan

1. 定義 `QueryQualityMeta` schema 與 helper（不改業務邏輯）。
2. 改 EventFetcher 與呼叫端（trace routes / trace job service / MSD）使用新契約，保留短期 adapter。
3. 改 trace 前端消費 `quality_meta`，新增可視警示與 diagnostics。
4. 對 Query Tool 高量端點導入 server-side pagination，前後端同步。
5. Material Trace export 切換至 streaming，維持既有 API 參數與截斷語意。
6. 補測試與 `.env.example` 文件，完成回歸驗證。

Rollback:
- 若新契約造成事故，可暫時啟用 compatibility adapter（將 `quality_meta` 映回舊結構）並回退前端消費。

## Open Questions

- Query Tool 分頁預設值是否採 `per_page=200`（效能優先）或 `50`（UI一致性優先）？
- `status=partial` 是否一律回 HTTP 200，或在特定 profile 回 206？
- NDJSON 是否新增獨立 `quality_meta` chunk，或掛在 `complete` chunk 內？
- 是否在本 change 直接納入 EventFetcher spool 化，或分拆為下一個 performance change？

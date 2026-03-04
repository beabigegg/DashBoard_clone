## Context

reject-history 目前的 cache 後查詢主要依賴 pandas（`apply_view`、`compute_batch_pareto`、`export_csv_from_cache`），在大範圍資料（百 MB 級）下會出現高峰值 RSS，導致 interactive memory guard 拒絕請求與 worker RSS guard 觸發重啟。現有系統已具備 parquet spool（`query_spool_store`），但後續計算仍常回載為 DataFrame 再做全表運算。

本次設計目標是在不改變 API 介面與回應 schema 的前提下，將 cache 後運算遷移到 SQL runtime（DuckDB）以降低 Python 記憶體壓力，同時保留既有 guard 作為最後保護。

約束條件：
- 不破壞 `reject-history` 前端既有參數與資料結構。
- 需保留 materialized pareto 的命中路徑與語意。
- 需維持明細/匯出的篩選一致性與資料完整性。
- rollout 必須可開關、可回退。

## Goals / Non-Goals

**Goals:**
- 在 cache/spool 資料上導入 DuckDB SQL 執行路徑，避免 pandas 全表 copy/groupby 成為主路徑。
- 第一階段優先改造 `batch-pareto`，在 materialized miss 時改走 cache-SQL。
- 第二階段改造 `view`，使 summary/trend/detail 分頁以 SQL 聚合與查詢產生。
- 第三階段改造 `export-cached`，改為串流輸出，避免一次性 `to_dict` 全載入。
- 保留並持續觀測現有 memory guard，穩定後再調整門檻。

**Non-Goals:**
- 不變更 Oracle primary query 與 chunk engine 的核心策略。
- 不新增或移除 reject-history API endpoint。
- 不變更前端查詢流程、URL 參數格式與欄位命名。
- 不在此變更中重寫其他頁面（hold/resource/material-trace）的 cache 運算。

## Decisions

### D1. 採用 DuckDB 作為 cache-SQL runtime（非 SQLite）

- **Decision**: 新增 DuckDB 依賴，作為 parquet/spool 查詢與聚合執行引擎。
- **Rationale**:
  - DuckDB 可直接查 parquet，支援 predicate pushdown、projection pushdown、aggregation/window，符合本次需求。
  - SQLite 無原生 parquet 掃描能力，需先灌入資料，反而增加一次記憶體與 I/O 成本。
  - 相較 pandas，DuckDB 在大資料篩選/聚合路徑更容易控制 worker RSS。
- **Alternatives considered**:
  - pandas 優化（減欄位、category）: 已做但仍有高 RSS 與 guard 誤擋。
  - SQLite 臨時表: 需要 ETL 步驟，不能直接利用 parquet spool。

### D2. 建立 reject-history 專用 cache-SQL facade

- **Decision**: 新增 `reject_cache_sql_runtime`（名稱可依實作調整）統一提供：
  - 載入來源解析（parquet spool 優先，必要時 fallback）
  - 參數綁定與安全 SQL 片段組裝
  - 共用 filter 條件建構（policy/supplementary/trend/pareto selections）
- **Rationale**:
  - 避免 SQL 字串組裝分散在 route/service，降低語意漂移。
  - 將 parity 規則集中管理，便於與 legacy pandas 對照測試。
- **Alternatives considered**:
  - 直接在 `reject_dataset_cache.py` 內內嵌 SQL: 快但可維護性差、測試切面不清。

### D3. batch-pareto 路徑優先改造，保留 materialized-hit

- **Decision**:
  - `try_materialized_batch_pareto` 命中時行為不變。
  - miss/stale/build-fail 時，先走 cache-SQL 批次計算。
  - cache-SQL 不可用時，才回退 legacy DataFrame 計算。
- **Rationale**:
  - `batch-pareto` 是高頻且高成本聚合點，改造收益最大。
  - 保留既有 materialized 快路，避免重工。
- **Alternatives considered**:
  - 直接移除 materialized 層: 風險高，且會放棄既有命中收益。

### D4. view 改為 SQL 聚合 + SQL 分頁

- **Decision**:
  - `summary`/`trend` 透過 SQL 聚合計算。
  - `detail` 透過 SQL 套用所有篩選後再排序分頁。
  - 保持現有輸出結構（`analytics_raw`、`summary`、`detail.pagination`）。
- **Rationale**:
  - 解決目前「先 guard 後篩選」導致的大量誤拒。
  - 減少 pandas 多段中間 DataFrame 生命週期。

### D5. export-cached 改為串流匯出

- **Decision**:
  - 使用 generator 逐批讀取並寫出 CSV response。
  - 不再先建立完整 rows list / to_dict 再回應。
- **Rationale**:
  - 匯出為典型大輸出場景，串流可有效降低峰值 RSS。
  - 維持既有篩選條件與欄位契約不變。

### D6. 以 feature flags 漸進 rollout，保留雙路 fallback

- **Decision**: 新增 runtime 開關（命名待實作定稿），至少包含：
  - 全域開關（cache-SQL 啟用/停用）
  - endpoint 級開關（batch/view/export 分別啟用）
  - fallback 開關（允許回退到 legacy pandas）
- **Rationale**:
  - 便於線上灰度與快速回退。
  - 降低一次性替換風險。

## Risks / Trade-offs

- **[DuckDB 依賴與執行環境相容性]** → 在 `requirements`/`environment.yml` 固定可用版本，CI 與 VM 啟動腳本納入檢查。
- **[SQL 與 pandas 語意偏差]** → 建立 parity 測試（同 query_id、同 filter，對比 summary/trend/detail/pareto 結果）。
- **[spool 缺失時路徑回退造成行為不一致]** → 定義明確來源優先序與 fallback reason telemetry，保證可觀測。
- **[查詢計畫在極端條件下退化]** → 保留 guard 與 timeout，必要時對 SQL runtime 增加最大掃描/輸出限制。
- **[導入初期同時維護雙路徑成本]** → 分階段啟用，待穩定後再收斂 legacy 路徑。

## Migration Plan

1. **Phase 1（batch-pareto）**
- 引入 DuckDB runtime 與基本來源解析。
- `batch-pareto` materialized miss 路徑改接 cache-SQL。
- 加入 endpoint 級開關與 fallback telemetry。

2. **Phase 2（view SQL 化）**
- 將 `summary/trend/detail` 改為 SQL 路徑。
- 調整 memory guard 觸發位置（先縮小資料再 guard 或改為 SQL 結果預估守門）。

3. **Phase 3（export 串流）**
- `export-cached` 改為串流生成 CSV。
- 驗證與明細資料的篩選一致性。

4. **Rollout / Rollback**
- 預設先灰度啟用（batch -> view -> export）。
- 若觀測到錯誤率或結果偏差升高，可關閉對應 endpoint 開關回退 legacy。

## Open Questions

- 是否要求 `view` 的 `analytics_raw` 維持完全相同排序（若前端對排序有隱性依賴）？
- 是否在本次就引入「cache-SQL 專屬 memory budget 指標」，或先沿用現有 worker guard telemetry？

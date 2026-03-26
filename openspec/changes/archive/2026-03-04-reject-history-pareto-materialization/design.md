## Context

Reject History 目前採兩階段模式：`POST /api/reject-history/query` 先建立 lot-level dataset cache，後續 `reason-pareto` / `batch-pareto` / `view` 反覆在 worker 內以 pandas 對全量明細重算。當使用者在大日期區間下進行多維 Pareto 互相篩選時，會在多 worker 環境放大記憶體壓力，造成高 RSS、回應抖動，甚至 worker 不穩定。

本變更目標是在不改前端 API contract 的前提下，新增「Pareto 預聚合/物化」層，讓互動式 Pareto 請求改讀聚合快照，而非每次掃描 lot-level 明細。

## Goals / Non-Goals

**Goals:**
- 讓 `batch-pareto` 與 `reason-pareto`（cache 路徑）優先讀取 materialized Pareto snapshot。
- 降低每次互動所需的 worker 計算記憶體與 CPU，避免反覆全量 groupby。
- 對 snapshot 建立一致性規則（version/freshness/invalidation），確保不回傳過期或錯配資料。
- 補齊可營運觀測：build latency、hit/miss、fallback 原因、snapshot 大小。
- 保持回傳 schema 與前端互動語意（cross-filter、top80/top20）相容。

**Non-Goals:**
- 不改 Oracle 明細 SQL 與 primary query 的資料來源。
- 不新增「大日期範圍硬拒絕」規則。
- 不改前端 Pareto 元件與 URL 參數契約。
- 不在此變更導入全新儲存系統（沿用現有 process cache + Redis/spool 生態）。

## Decisions

### 1) 新增獨立 Pareto materialization service，與 lot-level cache 解耦
- Decision: 新增 `reject_pareto_materialized.py`（名稱可調整）負責 build/read/invalidate snapshot，不把邏輯直接塞進 route。
- Why: 可將聚合生命週期、key 策略、遙測統一管理，降低 `reject_dataset_cache.py` 複雜度。
- Alternative considered:
  - 直接在 `compute_batch_pareto()` 內加 dict 快取：容易與 dataset cache 生命週期糾纏，且跨 worker 命中率不足。

### 2) Snapshot key 綁定 query dataset 與 filter context，並附 schema version
- Decision: key 至少包含 `query_id`、policy toggles、supplementary filters、trend_dates hash、materialization schema version。
- Why: 避免不同篩選上下文誤用同一 snapshot；schema 變更可強制失效舊資料。
- Alternative considered:
  - 僅用 `query_id`：無法區分補充篩選，容易回傳錯誤 Pareto。

### 3) Materialized payload 儲存「可交叉運算所需最小聚合」，而非完整明細
- Decision: snapshot 儲存 6 維度聚合結果與交叉篩選必要中介結構（以可重建 cross-filter 為原則），不複製 lot-level rows。
- Why: 目標是減少記憶體放大，若儲存完整明細會失去價值。
- Alternative considered:
  - 直接存每個 dimension 最終 items：空間小但無法支援任意 cross-filter 重算。

### 4) Read path 採「materialized 優先 + 安全 fallback」
- Decision: `batch-pareto` / `reason-pareto(query_id)` 先讀 snapshot；miss/stale/build-fail 時 fallback 到既有 cache DataFrame 計算，並打 telemetry。
- Why: 保留功能可用性與漸進上線，避免一次切換造成功能中斷。
- Alternative considered:
  - snapshot miss 直接錯誤：風險高，對既有使用者不友善。

### 5) 建立 single-flight build 與容量上限
- Decision: 同一 snapshot key 同時間僅允許一個 build，其餘請求等待或讀舊值；並限制單 snapshot size 與總 key TTL。
- Why: 避免 thundering herd 與 Redis/spool 不受控成長。
- Alternative considered:
  - 完全不鎖：高併發下會重複建構，放大 CPU/記憶體與 IO。

### 6) 將 observability 併入既有 cache telemetry 合約
- Decision: 在現有 cache observability 結構新增 pareto-materialized 欄位（hit/miss/fallback/build/size/freshness）。
- Why: operations 可以在同一入口判斷 cache 問題來源，不需分散查多個 API。
- Alternative considered:
  - 只寫 log：難做趨勢與告警。

## Risks / Trade-offs

- [Risk] Snapshot key 組成不完整導致污染（cross-user/filter 汙染）。
  - Mitigation: key builder 單元測試覆蓋參數排序、空值正規化與 version 隔離。

- [Risk] 中介聚合結構設計錯誤，cross-filter 結果與舊路徑不一致。
  - Mitigation: 建立 parity tests，對同一 query_id 比對 materialized 與 legacy 計算結果。

- [Risk] Fallback 比率長期偏高，materialization 失去效益。
  - Mitigation: telemetry 強制輸出 fallback reason，設定告警門檻並納入 rollout gate。

- [Risk] 新增 build 步驟拉長首次 Pareto 回應時間。
  - Mitigation: 首次 build 可回 legacy 結果並背景填充，或採同步 build 但有 timeout 上限；由配置控制。

## Migration Plan

1. 實作 materialization service（key、payload、build/read/invalidate、telemetry）。
2. 在 `compute_batch_pareto` 與 `compute_dimension_pareto(query_id path)` 接入 read-through/fallback。
3. 加入 parity 測試（legacy vs materialized）與壓力測試（重複 cross-filter 切換）。
4. 灰度啟用：先開 telemetry-only / build-disabled，再開 read-through，再提高命中比例。
5. 監控 hit ratio、fallback ratio、worker RSS 趨勢；達標後再考慮收斂 legacy 路徑。

Rollback strategy:
- 以 feature flag 關閉 materialized read path，立即回退至現行 DataFrame 計算，不影響 API schema。

## Open Questions

- materialized payload 要儲存在 Redis（快速）還是 spool（耐久）為主？是否需要雙層策略。
- 首次 build 採同步阻塞還是背景建置（與 UX latency 取捨）。
- 長期是否將 materialization 前移至 primary query 完成後立即建立，以換取互動穩定性。

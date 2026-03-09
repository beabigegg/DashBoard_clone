## Context

目前系統已有「報廢歷史查詢」可做事後分析，但缺少以良率變化為主軸的前置偵測入口。為了避免改壞既有報廢查詢邏輯，本次採新增獨立功能「Yield Alert Center」，由 ERP 生產移轉資料提供良率基底，再回鑽既有報廢歷史資料。

核心資料來源與角色分工如下：
- `ERP_WIP_MOVETXN`: 較輕量聚合來源，用於快速良率基底與趨勢計算。
- `ERP_WIP_MOVETXN_DETAIL`: 細維度聚合來源，用於告警候選與維度 drilldown。
- `DW_MES_LOTREJECTHISTORY`: 報廢歷史細節來源，用於根因追溯與明細查核。

此變更橫跨前端新頁面、後端新 API、跨資料源映射與運維邊界，屬於跨模組變更，需要先明確設計再實作。

## Goals / Non-Goals

**Goals:**
- 新增獨立 Yield Alert Center 頁面與 API，不影響既有 Reject History 頁的既有行為。
- 以 ERP 表計算 `transaction_qty`、`scrap_qty`、`yield_pct`，提供趨勢與告警候選清單。
- 建立 ERP 到 Reject History 的可重現映射契約（`date_bucket + workorder + reason_code`）。
- 提供 drilldown payload，讓工程師可由告警快速跳轉到報廢明細上下文。
- 以查詢視窗限制、分頁上限、快取與監控，控制 Oracle 負載與回應延遲。

**Non-Goals:**
- 不改寫既有 Reject History API/頁面的核心查詢語意。
- 不在本次導入完整規則引擎式告警管理（如通知排程、訂閱、推播）。
- 不在本次替換既有資料倉儲模型或建立新 ETL 管線。

## Decisions

### Decision 1: 以「新增獨立能力」取代「改造既有報廢頁」
- Decision: Yield Alert Center 採新 route + 新 API，並保留 Reject History 原有流程。
- Rationale: 可避免既有報廢查詢受告警邏輯耦合影響，降低回歸風險，並讓告警能力可獨立演進。
- Alternatives considered:
  - 在 Reject History 頁內直接新增告警區塊：開發看似快，但交互與查詢語意混雜，回歸面積過大。
  - 先只做 API 不做頁面：無法形成可用分析入口，使用者仍需人工拼湊。

### Decision 2: 良率計算主路徑優先使用 ERP 聚合表
- Decision: 基礎彙總/趨勢使用 `ERP_WIP_MOVETXN`；告警候選與多維切分使用 `ERP_WIP_MOVETXN_DETAIL`。
- Rationale: 兼顧速度與細節，降低高維查詢對主路徑延遲的影響。
- Alternatives considered:
  - 全部只用 DETAIL：維度完整但負載高，長時間窗成本偏大。
  - 全部只用 MOVETXN：效能佳但維度不足，無法支撐追溯分析。

### Decision 3: Drilldown 採 canonical key + 正規化策略
- Decision: 以 `date_bucket + workorder + normalized_reason_code` 作為主映射鍵，並輸出 match status（`exact`/`partial`/`none`）。
- Rationale: 實測在細粒度鍵下與 Reject History 的 `REJECT_TOTAL_QTY` 對應最穩定，且可審計。
- Alternatives considered:
  - 僅用日期+工單：粒度太粗，對應品質不足。
  - 直接用原始原因文字：格式變異高，無法穩定匹配。

### Decision 4: API 安全邊界採硬限制 + 元資料揭露
- Decision: 實作最大時間窗、最大分頁、固定排序欄位白名單；回應提供 cache hit/miss 與 linkage quality metadata。
- Rationale: 可避免高基數查詢拖垮服務，且讓前端能正確揭示資料完整性。
- Alternatives considered:
  - 僅靠前端限制：無法防止直接 API 濫用。
  - 不揭露品質 metadata：使用者會把部分匹配誤判為完整結果。

### Decision 5: 前端交互採雙區塊模式（Trend + Alert List）
- Decision: 頁面主體分為趨勢總覽與告警清單，列層級提供「查看追溯」動作。
- Rationale: 製程工程師先看異常範圍，再逐列追溯，符合工作流；同時降低一次呈現過多細節造成的認知負擔。
- Alternatives considered:
  - 單頁同時堆疊大量 Pareto/明細：資訊密度過高，首次使用成本高。

## Risks / Trade-offs

- [Risk] 原因碼異質性導致映射不完全 → Mitigation: 建立正規化表與未知碼分類（`unmapped_reason`），並揭露 unmatched ratio。
- [Risk] 大時間窗或高維組合造成 Oracle 壓力升高 → Mitigation: 後端硬性視窗限制、分頁上限、快取與慢查詢監控。
- [Risk] 使用者誤解 partial linkage 結果 → Mitigation: 在 API 與 UI 同步顯示 match status 與警示文案。
- [Trade-off] 新增獨立頁面會增加導覽節點與維護面積 → Mitigation: 復用既有查詢元件與 shared state 模式，降低維護成本。
- [Trade-off] 快取提升效能但可能引入短暫非即時性 → Mitigation: 設定短 TTL，並提供手動刷新入口。

## Migration Plan

1. 後端先上線（feature flag 關閉）
- 新增 Yield Alert API 與 linkage service，完成單元測試與契約測試。
- 於 staging 驗證查詢延遲、快取命中率、unmatched ratio 指標。

2. 前端頁面與導覽接入（feature flag 控制）
- 增加新工具入口與頁面，與既有 Reject History 完全解耦。
- 串接 API metadata（cache/linkage quality）顯示狀態。

3. 小流量驗證
- 僅對指定角色開放，觀察 Oracle 壓力、API P95、drilldown 成功率。
- 依觀測調整視窗上限、預設查詢範圍與正規化規則。

4. 全量開放
- 移除角色限制，保留 feature flag 作為緊急開關。

Rollback strategy:
- 若發生效能或資料品質問題，立即關閉 Yield Alert feature flag。
- 由於既有 Reject History 未改寫，關閉後可回到原本作業流程。

## Open Questions

- 原因碼正規化規則由誰維護（製程/IT）與變更週期為何？
- `risk_level` 的門檻是否採固定值，或需依產品別/製程別設定？
- drilldown 導頁時是否需要攜帶更多維度（如 department/line）以提高匹配準確率？
- 是否需要在首版就提供告警快照匯出（CSV）供會議檢討使用？

## Context

`portal-shell` 已建立 Vue Router 導覽骨架與抽屜資料載入，但目前主內容仍以 `PageBridgeView` 導向既有頁面，尚未完成 route-view 內容整合。這代表「不使用 iframe」雖已成為主要技術方向，但使用者操作仍處於 shell 與舊頁間切換，抽屜治理、健康資訊呈現與頁面可用性驗收仍分散。

同時，營運中的抽屜設定已由後端 `page_status.json` 管理，且 admin/non-admin 可見性、排序與頁面釋出狀態都依此決定。若 route-view 整合未與抽屜契約同步，就會發生「抽屜有項目但 shell 無法直接承載」或「權限可見性與實際可達性不一致」的風險。

本 change 的定位是「完成遷移」，不只做 shell 外觀，而是把導航、內容承載、健康檢查、wrapper 退場與 cutover gate 收斂為單一可驗收遷移路徑。

## Goals / Non-Goals

**Goals:**
- 完成 `portal-shell` route-view 整合，讓已重寫頁面直接在 shell 內容區承載。
- 將 legacy 頁面採「短期 wrapper、最終 rewrite」策略，並在本 change 內完成 wrapper 退場。
- 抽屜治理維持後端單一事實來源，並在 shell 端落實 deterministic 顯示與 fallback 行為。
- 健康檢查改為「摘要優先、詳情展開」，避免 header 資訊過載。
- 建立每頁 rewrite smoke 驗收清單與 cutover gate，確保遷移可上線且可回滾。
- 對 table/chart/filter/互動/matrix 建立遷移前後對照驗證，未達標不得切換。

**Non-Goals:**
- 不重設 `page_status.json` 的資料模型（`drawers/pages/status/admin_only` 維持）。
- 不改變核心業務 API 的欄位語義與查詢語義。
- 不在本 change 導入新的後端框架或跨服務拆分。

## Decisions

### Decision 1: Shell 採雙模式承載（native route-view + temporary wrapper），並以能力清單管理
- **選擇**: 在 shell route registry 中明確標註每個頁面的承載模式（`native` 或 `wrapper`），由 router 決定掛載元件。
- **理由**:
  - 允許先整合既有重寫頁面，再逐步替換 wrapper，不阻塞整體切換。
  - 能清楚量化「尚未完成遷移」的頁面數量，避免無限期 wrapper。
- **備選方案**:
  - 全部先走 wrapper：風險低但無法達成完整遷移目標。
  - 全部一次性 native 化：風險高、驗收與回滾壓力過大。

### Decision 2: 抽屜契約保持後端治理，前端僅做 route-ready 映射與可達性保護
- **選擇**: `GET /api/portal/navigation` 仍為抽屜來源；shell 只加上 route-ready 驗證、可達 fallback、admin 入口一致呈現。
- **理由**:
  - 不破壞既有營運調整流程（排序/隱藏/發佈狀態）。
  - 避免抽屜資訊在 server/client 出現雙寫與漂移。
- **備選方案**:
  - 前端本地抽屜配置：會與管理後台脫鉤，維運成本高。

### Decision 3: 健康資訊採「摘要固定 + 詳情互動展開」
- **選擇**: shell header 僅顯示高層摘要（狀態燈 + 簡短字串）；詳細欄位移至點擊展開面板。
- **理由**:
  - 解決 header 文案過長與可讀性下降問題。
  - 保留診斷深度，不犧牲 ops 能力。
- **備選方案**:
  - 全部資訊常駐：視覺噪音高，對導航可用性不利。
  - 僅顯示摘要且不提供詳情：故障排查資訊不足。

### Decision 4: 以「每頁 smoke 清單 + Gate」作為切換條件，不以主觀完成度判斷
- **選擇**: 每頁 rewrite 需有可執行 smoke 清單；G1~G7 gate 不通過不得 final cutover。
- **理由**:
  - 遷移規模大，必須機械化驗收標準。
  - 可追蹤 regressions 與回滾觸發條件。
- **備選方案**:
  - 僅靠人工巡檢：可重複性不足，易漏檢。

### Decision 5: Wrapper 必須在本 change 內歸零，並保留短期 kill-switch
- **選擇**: `job-query`、`excel-query`、`query-tool`、`tmtt-defect` 先保 wrapper 可用，但設里程碑在同一 change 完成 rewrite，最後移除 wrapper 路由。
- **理由**:
  - 符合「完整遷移」目標，避免技術債延宕。
  - 有 kill-switch 可在突發問題時快速退回上一穩定路徑。
- **備選方案**:
  - Wrapper 長期保留：短期省工，但不符合完整遷移與長期維護成本控制。

### Decision 6: 互動語義採「基線快照 + 自動驗證 + 發佈門檻」三層保障
- **選擇**: 針對 table/chart/filter/互動/matrix，先錄製遷移前基線（資料欄位、互動序列、視覺語義），遷移後以自動測試和 smoke 清單做逐頁比對，並設 release-block gate。
- **理由**:
  - 你的核心風險在「功能看起來可開，但語義已偏移」，必須用可比對證據治理。
  - 可量化是否「真的等價」，而不是靠人工主觀判斷。
- **備選方案**:
  - 僅做路由可達 smoke：不足以驗證 chart/table/matrix 深層語義。

## Risks / Trade-offs

- **[Risk] Route-view 整合後，頁面初次載入時間可能上升** → **Mitigation**: 以 route-level code split、懶載與快取策略控管，並建立切頁延遲基線比較。
- **[Risk] 抽屜配置與 route registry 失配造成死連結** → **Mitigation**: 導入 route-ready contract test 與 runtime fallback（不可達時導向 shell home + 訊息）。
- **[Risk] Wrapper 退場時漏掉邊緣流程（export/進階查詢）** → **Mitigation**: 每頁 smoke 清單納入核心與進階流程；未通過不得切換 native。
- **[Risk] 健康詳情收合後，使用者誤判資訊不足** → **Mitigation**: 摘要保留關鍵狀態詞，並提供單擊展開完整 diagnostics。
- **[Risk] 最後切換期回滾窗口過短** → **Mitigation**: 預演 rollback runbook，保留 kill-switch 與既有入口直到所有 gate 連續通過。
- **[Risk] Chart 在 route 切換後容器尺寸或互動狀態異常** → **Mitigation**: 加入 chart resize lifecycle 驗證與互動回放測試（縮放/篩選/聯動）。
- **[Risk] Table/filter/matrix 在重掛載後狀態漂移** → **Mitigation**: 建立 query-state、排序、分頁、選取高亮的前後對照測試。

## Validation Strategy (Pre/Post Migration)

1. **Pre-migration baseline capture**
- 逐頁紀錄：table 欄位與排序語義、chart series 與互動行為、filter query contract、matrix 選取/高亮邏輯。
- 產出基線檔與 screenshot/資料快照，作為遷移後對照來源。

2. **Post-migration parity verification**
- 自動化驗證：payload key/type、query semantics、table/chart/matrix 行為一致性。
- 互動 smoke：filter 套用、chart-table 聯動、matrix drill/select、分頁/返回流程。
- 視覺語義檢查：狀態色、零值顯示、圖例/tooltip、highlight 狀態不漂移。

3. **Gate policy**
- 任一頁面的核心 table/chart/filter/互動/matrix 對照失敗即阻擋 cutover。
- 僅在所有頁面 parity 證據完整且無 critical gap 時，才允許 wrapper 退場與 default cutover。

## Migration Plan

1. **Contract Freeze**
- 鎖定抽屜/路由/權限契約，建立 route-ready 檢查與 mismatch 告警。

2. **Parity Baseline Freeze**
- 完成 table/chart/filter/互動/matrix 基線快照與驗收腳本凍結。

3. **Shell Route-View Host 完成**
- 建立 `native/wrapper` 承載策略、router 動態掛載、fallback 與 breadcrumb/title 一致性。

4. **Health Summary/Detail 改版**
- header 僅顯示摘要，詳細資料改為展開視圖；補齊前後端契約與測試。

5. **Native Integration Wave A（已重寫頁）**
- 將既有 Vite/Vue 頁面直接整合到 shell route-view，移除 PageBridge 導向依賴。

6. **Legacy Rewrite Wave B（wrapper 頁）**
- 完成 `job-query`、`excel-query`、`query-tool`、`tmtt-defect` rewrite，逐頁替換 wrapper。

7. **Gate Enforcement & Rollout**
- 每頁 smoke 清單、drawer parity、health/route 穩定性、性能閾值全部通過後切換 default。

8. **Decommission & Cleanup**
- 移除 wrapper 路由與殘留遷移旗標，更新 runbook 與 spec，同步封存標準。

## Open Questions

- `native/wrapper` 承載模式是否需回傳於 `navigation` API payload，或僅前端 registry 管理即可？
- Wave B 的四頁是否按使用量排序，或以技術風險排序優先重寫？
- cutover 期間是否保留短期雙入口（`/portal` 與 `/portal-shell`）觀測窗口？

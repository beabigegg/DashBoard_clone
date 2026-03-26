## Context

目前 `portal.html` 透過 `iframe + frame_id + toolFrame` 在同一頁面切換多個報表。此模式雖可避免整頁跳轉，但帶來以下問題：

- 內容生命週期拆成多個 frame，除錯與事件追蹤困難
- 導覽邏輯被 iframe lazy-load、高度同步、active frame 狀態綁死
- 測試對 DOM/互動契約依賴 iframe 結構，變更成本高
- 已完成 Vite 模組化的頁面其實已可獨立路由載入，不需要 iframe 承載

此外，`drawers` 設定在目前環境已不是初始預設值，而是營運中配置（來源：`data/page_status.json`）：

- `reports`（即時報表，order=1，admin_only=false）
- `drawer-2`（歷史報表，order=2，admin_only=false）
- `drawer`（查詢工具，order=3，admin_only=false）
- `dev-tools`（開發工具，order=4，admin_only=true）

對應頁面已分散配置在上述抽屜，例如：

- 即時報表：`/wip-overview`、`/hold-overview`、`/resource`、`/qc-gate`
- 歷史報表：`/hold-history`、`/resource-history`
- 查詢工具：`/job-query`
- 開發工具：admin pages 與部分工具頁（含 `tables`、`excel-query`、`query-tool`、`tmtt-defect`、`mid-section-defect`）

因此本次改造不只是移除 iframe，而是要把「抽屜資訊架構」從「載入技術（frame）耦合」解耦到「路由與權限治理」。

## Goals / Non-Goals

**Goals:**
- 移除 portal 內容區的 iframe 依賴與 frame 管理邏輯
- 保留抽屜分組、admin 權限過濾、健康狀態檢查 UI
- 將側欄點擊行為改為同視窗路由導頁
- 維持既有 route path 與頁面業務邏輯不變
- 更新測試使其驗證新契約（link/navigation）
- 在不破壞既有 `drawers/pages` 資料模型下，支持 Router-based 導覽

**Non-Goals:**
- 不在第一階段一次重寫全部 legacy 頁面內容
- 不調整後端 API 介面或權限模型
- 不更動 page_status.json 的資料模型（僅調整 portal 消費方式）

## Decisions

### Decision 1: 抽屜保留後端治理，前端改為 Router-aware 導覽
- **選擇**: `get_navigation_config()` 仍作為抽屜與頁面來源，前端側欄只消費 route / status / admin_only，不再消費 frame_id/toolFrame。
- **理由**:
  - 保留既有營運中的抽屜設定與管理流程
  - 抽屜責任回到 IA（分類、排序、權限），避免綁定載入技術
  - 降低一次性資料遷移與管理頁調整風險
- **備選方案**:
  - 改由前端硬編抽屜：短期可行，但與管理後台脫鉤，營運成本增加

### Decision 2: 導入 SPA Shell + Vue Router，分階段替換多入口模式
- **選擇**: 建立 SPA shell 承接抽屜導覽，主要報表頁優先轉為 router view；既有可獨立頁先保持可直接訪問。
- **理由**:
  - 符合大型遷移所需的漸進路線
  - 可保留既有 URL 合約並分批改造
- **備選方案**:
  - 一次切成全 SPA：改動面過大，回歸與 rollback 風險高

### Decision 3: Legacy 頁面採先包裝、後重寫策略（已確認）
- **選擇**: `job-query`、`excel-query`、`query-tool`、`tmtt-defect` 先以 wrapper route 納入新殼層，再逐頁重寫為標準 Vue 模組。
- **理由**:
  - 先完成抽屜/導航/樣式治理，不被單頁重寫阻塞
  - 可逐步替換，控制每次上線風險
- **備選方案**:
  - 直接重寫四頁：會延後主幹遷移，且依賴資料邏輯盤點完整度

### Decision 4: Tailwind 為主樣式系統，保留過渡期雙軌
- **選擇**: 新增 Tailwind 設計 token 與元件規範，新功能優先用 Tailwind；舊頁 CSS 分批遷移。
- **理由**:
  - 先建立統一規範，避免繼續累積散落 CSS
  - 遷移節奏可與功能迭代對齊

## Risks / Trade-offs

- **[Risk] 切頁不再常駐多頁狀態，使用者感知切換較慢** → **Mitigation**: 保持頁面 bundle 切分與快取策略，後續再評估 prefetch。
- **[Risk] 既有測試仍假設 iframe DOM 結構** → **Mitigation**: 分階段更新 template/e2e/stress 斷言為 router/navigation 契約。
- **[Risk] 抽屜配置與路由表可能出現不一致** → **Mitigation**: 新增導航一致性檢查（缺失 route、權限錯置、排序衝突）。
- **[Risk] Tailwind 與既有 CSS 共存期造成樣式衝突** → **Mitigation**: 設定 migration lint 規則與 page-level ownership，限制新增散落 CSS。
- **[Risk] Legacy wrapper 週期拉長導致技術債滯留** → **Mitigation**: 在 tasks 中明確列出逐頁重寫里程碑與退出條件。

## Migration Plan

1. 定義抽屜-路由契約（來源、排序、權限、可見性）並建立檢查機制。
2. 建立 SPA shell 與 Router，先接管 portal 導覽與主要報表頁入口。
3. 移除 iframe 導覽路徑，保留舊 URL 行為與 fallback。
4. 導入 Tailwind 設計系統並建立共用元件層。
5. 將四個 legacy 頁面先包裝接入新殼層，再分批重寫。
6. 完成測試與觀測遷移（模板、E2E、壓測、性能基線）。

## Current Baseline Snapshot (2026-02-11)

### Effective drawer visibility (derived from current `drawers + pages + status + admin_only`)

- Non-admin visible routes:
  - `reports`: `/wip-overview`, `/resource`, `/qc-gate`
  - `drawer-2`: `/resource-history`
  - `drawer`: `/job-query`
- Admin visible routes:
  - `reports`: `/wip-overview`, `/hold-overview`, `/resource`, `/qc-gate`
  - `drawer-2`: `/hold-history`, `/resource-history`
  - `drawer`: `/job-query`
  - `dev-tools`: `/tables`, `/admin/pages`, `/excel-query`, `/admin/performance`, `/query-tool`, `/tmtt-defect`, `/mid-section-defect`

### Query/route contracts that must not regress

- `/wip-overview`: query filters `workorder`, `lotid`, `package`, `type`, `status`
- `/wip-detail`: query filters `workcenter`, `workorder`, `lotid`, `package`, `type`, `status`
- `/hold-detail`: required query `reason` (missing reason redirects away by current server/client guard)
- `/resource-history`: query params built from date range, granularity, groups/families/machines, production flags

## Functional Parity Matrix

| Route / Surface | Migration Mode | Must Preserve |
| --- | --- | --- |
| `/` portal shell | SPA (router host) | Drawer grouping/order/visibility, health widget, auth-linked visibility |
| `/wip-overview` | Vue route view | Filter URL sync, status filter behavior, drill-down to detail pages |
| `/wip-detail` | Vue route view | Query-param entry, pagination/filter semantics, back-link query continuity |
| `/hold-overview` | Vue route view | Hold type/reason filter behavior, treemap/matrix interaction |
| `/hold-history` | Vue route view | Date/record type filter semantics, reason pareto interactions |
| `/resource` | Vue route view | Group/status filtering and summary parity |
| `/resource-history` | Vue route view | Query validation, summary/detail/export behavior parity |
| `/qc-gate` | Vue route view | Chart↔table linked filtering and refresh behaviors |
| `/job-query` | Wrapper first | Resource/date query, transaction query, CSV export |
| `/excel-query` | Wrapper first | Upload/column detect/query/export workflow |
| `/query-tool` | Wrapper first | Resolve/history/association/equipment-period workflow |
| `/tmtt-defect` | Wrapper first | Date-range query and CSV export workflow |

## Data Contract Safety Net

- 建立「遷移前基線快照」：
  - drawer visibility snapshot（admin / non-admin）
  - route response smoke snapshot（HTTP status + critical payload keys）
  - critical page JSON schema snapshots（summary/detail/pagination key sets）
- 建立「遷移後對等檢查」：
  - key presence parity（不可缺欄位）
  - type compatibility（數值/字串/陣列型別）
  - empty-state semantics（空資料行為一致）
- 對 legacy wrapper 頁面增加 wrapper-contract 測試：
  - route reachable
  - primary query path success
  - export path reachable (where applicable)

## Go / No-Go Gates (Cutover)

- G1 Route availability:
  - P0 路由（portal + major report routes）100% 回應 2xx/3xx
- G2 Drawer parity:
  - admin/non-admin 可見路由集合與 baseline 差異為 0
- G3 Workflow parity:
  - parity matrix 中每頁核心流程至少 1 條 smoke path 通過率 100%
- G4 Client stability:
  - E2E 測試中未捕獲未處理 JS runtime error（critical path）
- G5 Data contract:
  - critical API payload key/type parity gate 全部通過
- G6 Performance:
  - route switch latency 與 baseline 比較不得惡化超過既定閾值
- G7 Rollback readiness:
  - rollback rehearsal 完成且時間達標（可在目標時間內恢復舊路徑）

## Rollback / Kill-Switch Strategy

1. 保留舊入口路徑與必要 fallback，直到全量 gate 通過。
2. 使用可配置切換（feature flag / env-based toggle）控制新 shell 導航啟用。
3. 一旦觸發回滾條件（G1/G2/G3 任一 critical fail），立即切回舊導航路徑。
4. 回滾後保留觀測資料並建立失敗歸因報告，再進行下一輪修復與 rehearsal。

## Open Questions

- `frame_id/tool_src` 欄位何時在資料模型層正式退場？
- legacy wrapper 對使用者是否顯示遷移標記（例如 beta badge）？
- 動效方案是否在第一版限定 `Vue Transition`，GSAP 延後到二階段？

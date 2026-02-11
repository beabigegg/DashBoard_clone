## Why

目前前端處於「多入口頁 + portal iframe 切頁 + 分散 CSS」型態，已出現幾個結構性問題：頁面生命週期分裂、導覽與內容耦合、樣式規範難以統一、重用元件難以制度化。專案已大量採用 Vite + Vue 3，現在具備升級為單一 SPA Shell 的條件，應趁此時移除 iframe 並建立可持續擴充的前端架構基線。

## What Changes

- 建立前端 SPA Shell：以 `Vite + Vue 3` 為單一入口，採 `Vue Router` 管理報表模組切換。
- 完整移除 iframe 架構：portal 不再以 `frame_id/toolFrame` 嵌入內容，改為標準路由渲染。
- 導入 Tailwind CSS 作為主樣式系統，建立統一設計 token、元件風格與版面規則，逐步取代現有分散 CSS。
- 建立前端動效機制基線：以 `Vue Transition` 為預設，保留 `Motion/GSAP` 擴充通道，用於跨頁過場與重點互動。
- 盤點可重用元件並收斂成共用 UI 層（如 Filter、Table、Card、KPI、Pagination 等），降低重複實作。
- 明確採用 legacy 頁面過渡策略：`job-query`、`excel-query`、`query-tool`、`tmtt-defect` 先以路由包裝整合進新殼層，後續再分批重寫為標準 Vue 模組。
- 保留既有後端 API 與權限邏輯，優先完成前端殼層與導航機制遷移，再進行頁面內部重構。
- **BREAKING**: portal 由「iframe 同頁切頁」改為「SPA 路由切換」，舊有 frame 相關 DOM/測試契約不再成立。

## Capabilities

### New Capabilities
- `spa-shell-navigation`: 建立 Vue Router 為核心的報表導航殼層，取代 iframe 切頁機制。
- `tailwind-design-system`: 以 Tailwind + token + 共用元件規範統一前端樣式。
- `frontend-motion-system`: 定義頁面過場與互動動效的可維護實作策略（Vue Transition 為主，進階情境可擴充）。
- `legacy-page-wrapper-strategy`: 定義 legacy 頁面先包裝、後重寫的過渡標準與邊界。

### Modified Capabilities
- `portal-drawer-navigation`: 從 iframe frame-target 導覽改為 router-aware 導覽，維持抽屜分組與權限規則。
- `vue-vite-page-architecture`: 從多獨立頁入口演進到 SPA shell + 路由模組化，並納入 legacy-wrapper 相容模式。
- `full-vite-page-modularization`: 將既有共用邏輯由頁面級搬移至共用模組與設計系統層，提升重用與一致性。
- `migration-gates-and-rollout`: 將本次搬遷的上線/回滾條件明確化為可量測 gate，避免「可部署但不可用」風險。

## Impact

- Affected frontend app structure:
  - `frontend/src/portal/*`（改為 SPA shell / router host）
  - `frontend/vite.config.js`（入口與打包策略調整）
  - `frontend/src/*` 多頁模組（路由化、共用元件化、樣式收斂）
- Affected templates/routes:
  - `src/mes_dashboard/templates/portal.html`（iframe 區塊移除）
  - Flask route 對 SPA entry 與 fallback 行為需重新定義
- Affected shared styling:
  - 現有 `wip-shared/resource-shared` 樣式與各頁 style.css 將分階段合併到 Tailwind 設計系統
- Affected testing:
  - 模板整合測試、E2E、壓測需從 iframe 契約改為 router/navigation 契約
  - 需新增 route-level smoke、drawer visibility parity、legacy wrapper contract、核心 API parity gate
- Dependency change:
  - 新增 Tailwind CSS（必要時含 PostCSS 生態）
  - 動效方案預設不新增第三方；僅在必要場景引入 GSAP 或等價方案
- Explicit migration decision:
  - `job-query`、`excel-query`、`query-tool`、`tmtt-defect` 採「先包裝、後重寫」策略

## Implementation Start Protocol

- 實作啟動時（第一個 `/opsx:apply` session）必須先完成 baseline 產出，再進行功能改造：
  - drawer visibility baseline（admin / non-admin）
  - route + query contract baseline（P0/P1 頁面）
  - critical API payload key/type baseline
- 在 baseline 產出並經 review 確認前，不進行 iframe 拆除與 Router 切換提交。
- 所有切換以 gate 驅動，不以主觀感受判定可上線。

## Release Safety Criteria

- 不可發生 P0 route 無法進入或 core workflow 中斷。
- 抽屜可見性（admin / non-admin）與 baseline 差異必須為 0。
- 既有 URL/query 行為不可破壞（含 drill-down 與 direct-link）。
- 必須具備可演練且可在時限內完成的回滾路徑（含 kill-switch）。

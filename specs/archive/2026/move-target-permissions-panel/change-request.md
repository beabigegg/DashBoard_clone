# Change Request

## Original Request

將「生產達成率」目標值編輯權限白名單管理面板（可編輯 can_edit_targets 的使用者授權，現位於
frontend/src/admin-pages/App.vue 內的 TargetPermissionsPanel.vue，對應
GET/PUT /admin/api/production-achievement/permissions[/{user_identifier}]）從
/admin/pages（頁面管理）遷移到 /admin/dashboard（管理儀表板），以新增分頁（tab）的形式呈現。

使用者原始需求是在 admin/dashboard 新增全線管理頁面，但實際落點在
production-achievement-kanban 變更（specs/archive/2026/production-achievement-kanban/
implementation-plan.md IP-8）中被放進了既有的 admin-pages（頁面管理）app，造成使用者找不到
該功能。此次變更修正落點，使其符合使用者原本預期。

## Business / User Goal

使用者（管理者）能在 /admin/dashboard（管理儀表板，既有的分頁式系統監控 app：總覽/效能/快取/
Worker/用戶/日誌）新增一個分頁存取「生產達成率目標值編輯權限」白名單管理，不必再去 /admin/pages
才找得到。

## Non-goals

- 不新增/修改任何後端 API endpoint；GET/PUT /admin/api/production-achievement/permissions[/{user_identifier}]
  維持原樣，仍走 admin_required 權限模型。
- 不改變 can_edit_targets 的授權語意或資料表結構。
- 不強制從 admin-pages 移除該面板功能本身所依賴的既有元件（TargetPermissionsPanel.vue 元件本體）；
  是否同時從 /admin/pages 移除該區塊由 implementation-planner 依現況決定並記錄理由。

## Constraints

- CSS 需改用 `.theme-admin-dashboard` scope（元件現在掛載於 admin-dashboard app，而非 admin-pages app），
  遵循 css-contract.md Rule 4.2/4.3（feature CSS 必須 scoped）。
- admin-dashboard/App.vue 是既有的分頁式（tabs 陣列 + defineAsyncComponent）架構，新分頁需依循相同模式
  （tabs.push 一個新 tab，對應的 Tab 元件放在 admin-dashboard/tabs/ 下）。
- /admin/dashboard 與 /admin/pages 的 visibilityPolicy 皆為 admin_only（routeContracts.js），此次變更不
  改變兩個路由本身的可見性/導覽權限。
- 若涉及 navigationManifest.js / nativeModuleRegistry.js / route_scope_matrix.json /
  asset_readiness_manifest.json，僅做必要的既有頁面內部結構調整（新增分頁不等於新增路由），非新增路由
  的情況下應避免不必要的 manifest 變更。

## Known Context

- 現有元件：frontend/src/admin-pages/components/TargetPermissionsPanel.vue（純表格 + toggle/grant UI，
  props: permissions，emits: toggle/grantNew）。
- 現有掛載位置：frontend/src/admin-pages/App.vue（頁面管理 app，PageHeader「頁面管理」，已有
  「所有頁面」與「生產達成率 — 目標值編輯權限」兩個 panel，都在 `.theme-admin-pages` scope 下）。
- 目標掛載位置：frontend/src/admin-dashboard/App.vue（管理儀表板 app，tabs: overview/performance/cache/
  worker/usage/logs，各 tab 元件在 frontend/src/admin-dashboard/tabs/*.vue，`.theme-admin-dashboard` scope）。
- API 層完全不變：src/mes_dashboard/routes 內對應的 admin permission endpoints 維持原樣。

## Open Questions

- 是否同時從 /admin/pages 移除「生產達成率 — 目標值編輯權限」panel，或兩處並存？
  （implementation-planner 決定並記錄理由；預設傾向移除舊位置以避免重複維護與使用者混淆，除非有相容性
  理由需要並存一段時間）

## Requested Delivery Date / Priority

一般優先度，隨下一個前端 release 一併處理。

## 1. Motion Design Tokens 基礎層

- [x] 1.1 在 `frontend/src/styles/tailwind.css` 的 `@layer base` 新增 `:root` CSS 變數（`--motion-fast`, `--motion-normal`, `--motion-slow`, `--motion-ease`, `--hover-lift`, `--overlay-bg`）
- [x] 1.2 在 `frontend/tailwind.config.js` extend 新增 `transitionDuration`（fast/normal/slow）和 `transitionTimingFunction`（smooth）引用 CSS 變數

## 2. 統一按鈕系統

- [x] 2.1 在 `frontend/src/styles/tailwind.css` 定義 `.ui-btn`、`.ui-btn--primary`、`.ui-btn--ghost`、`.ui-btn--sm`、`.ui-btn.is-loading` class，使用 motion tokens
- [x] 2.2 移除 `frontend/src/styles/tailwind.css` 中舊的 `.btn-primary`、`.btn-secondary`、`.btn` 定義
- [x] 2.3 移除 `wip-shared/styles.css`、`resource-shared/styles.css`、各頁面 `style.css` 中的舊按鈕 class 定義
- [x] 2.4 全部頁面 `.vue` 檔案中的 `btn-primary`/`btn-secondary`/`btn` class 替換為 `ui-btn ui-btn--primary` 等對應新 class

## 3. 統一搜尋觸發動畫

- [x] 3.1 在 `frontend/src/styles/tailwind.css` 新增 `.ui-table-wrap.is-loading` 和 `.ui-table-wrap .fade-in` 動畫 class
- [x] 3.2 各頁面表格容器套用 `.ui-table-wrap` class，綁定 loading 狀態切換 `is-loading`

## 4. 共用元件 — Loading

- [x] 4.1 建立 `frontend/src/shared-ui/components/LoadingSpinner.vue`（props: size sm/md/lg，對應 14px/24px/42px）
- [x] 4.2 建立 `frontend/src/shared-ui/components/LoadingOverlay.vue`（props: tier page/section，使用 LoadingSpinner + `--overlay-bg`）
- [x] 4.3 各頁面替換 inline loading overlay 和 spinner 為 `LoadingOverlay`/`LoadingSpinner` 元件

## 5. 共用元件 — EmptyState

- [x] 5.1 建立 `frontend/src/shared-ui/components/EmptyState.vue`（props: type no-data/filter-empty/error/loading，顯示對應中文文案）
- [x] 5.2 各頁面替換所有空狀態文字（"無資料"/"No data"/"無符合項目" 等）為 `EmptyState` 元件

## 6. 共用元件 — MultiSelect

- [x] 6.1 建立 `frontend/src/shared-ui/components/MultiSelect.vue`，以 resource-shared 版為基礎，加入 mid-section-defect 的 label+value 搜尋，新增 `selectAllScope` prop
- [x] 6.2 更新所有 `resource-shared/components/MultiSelect` import 改為 `shared-ui/components/MultiSelect`
- [x] 6.3 更新所有 `mid-section-defect/components/MultiSelect` import 改為 `shared-ui/components/MultiSelect`
- [x] 6.4 刪除 `frontend/src/mid-section-defect/components/MultiSelect.vue`

## 7. 共用 Composables

- [x] 7.1 建立 `frontend/src/shared-composables/useRequestGuard.js`（`nextRequestId()` + `isStaleRequest(id)` 防抖模式）
- [x] 7.2 建立 `frontend/src/shared-composables/useUrlSync.js`（URL query 參數序列化/反序列化）
- [x] 7.3 建立 `frontend/src/shared-composables/useFilterOrchestrator.js`（配置驅動，支援四種模式 + dependencies + pagination reset + URL sync）

## 8. 頁面遷移 — hold-overview（模式 A: Draft→Apply + immediate + matrix）

- [x] 8.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：HoldType immediate、Panel fields draft-apply、dependencies（HoldType→Reason reload + Matrix clear；Panel draft→Reason debounce reload；Apply→Matrix clear + page=1）
- [x] 8.2 替換 inline requestId 防抖為 `useRequestGuard`
- [x] 8.3 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 8.4 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 9. 頁面遷移 — hold-detail（模式 D: 互斥切換）

- [x] 9.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：3 個互斥 toggle fields，mutual-exclusive clear dependencies
- [x] 9.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 9.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 10. 頁面遷移 — hold-history（模式 B: 兩階段）

- [x] 10.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：Date Apply→primary query、HoldType→cache read、RecordType/Reason/Duration→cache read，dependencies（Date→RecordType reset ['new'] + Reason/Duration clear；HoldType→Reason/Duration clear）
- [x] 10.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 10.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 11. 頁面遷移 — wip-overview（模式 A: Draft→Apply + immediate status）

- [x] 11.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：Status immediate（僅 Matrix 重載）、Panel fields draft-apply（Apply→Summary + Matrix 全重載）
- [x] 11.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 11.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 12. 頁面遷移 — wip-detail（模式 A + workcenter）

- [x] 12.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：Status immediate（→page + lot clear + table 重載）、Panel Apply（→Status clear + page + lot clear + 全重載）
- [x] 12.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 12.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 13. 頁面遷移 — reject-history（模式 B: 兩階段 + DuckDB）

- [x] 13.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：primary query → supplementary unlock（workcenter_groups, packages, reasons）、cache expiry→auto requery
- [x] 13.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 13.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 14. 頁面遷移 — yield-alert-center（模式 B: 兩階段 + sort + DuckDB）

- [x] 14.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：primary query、date dirty→button label、supplementary/sort→page=1
- [x] 14.2 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 14.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 15. 頁面遷移 — resource-status（模式 C: 級聯即時）

- [x] 15.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：Group/Flags→Family prune→Machine prune，全部 immediate
- [x] 15.2 替換 loading/empty/button/MultiSelect 為共用元件和 `ui-btn` class
- [x] 15.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 16. 頁面遷移 — resource-history（模式 C: 獨立即時）

- [x] 16.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：全部 immediate，無級聯
- [x] 16.2 替換 loading/empty/button/MultiSelect 為共用元件和 `ui-btn` class
- [x] 16.3 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 17. 頁面遷移 — mid-section-defect（模式 C: 級聯）

- [x] 17.1 替換 filter 狀態為 `useFilterOrchestrator` 配置：Station→Upstream prune→Spec prune
- [x] 17.2 替換 MultiSelect import 為 `shared-ui/components/MultiSelect`
- [x] 17.3 替換 loading/empty/button class 為共用元件和 `ui-btn` class
- [x] 17.4 替換 CSS 硬編碼 transition 和 hover 為 motion tokens

## 18. 清理與契約更新

- [x] 18.1 刪除 `frontend/src/mid-section-defect/components/MultiSelect.vue`
- [x] 18.2 清除 `wip-shared/styles.css` 中重複的 loading/spinner/error-banner 定義
- [x] 18.3 清除 `resource-shared/styles.css` 中重複的 loading/empty-state 定義
- [x] 18.4 清除各頁面 `style.css` 中殘留的舊 `.btn-*`、硬編碼 transition、不統一 hover
- [x] 18.5 更新 `contract/css_inventory.md` 反映新增和修改的 CSS 檔案

## 19. 驗證

- [x] 19.1 執行 grep 驗證：無 `.btn-primary` 殘留、無硬編碼 transition 時間、無舊 MultiSelect import
- [x] 19.2 逐頁驗證篩選器交叉影響矩陣（比對 Network tab API 呼叫一致性）
- [x] 19.3 驗證 URL bookmark 帶篩選參數重載後狀態完整還原
- [x] 19.4 驗證快速連續篩選變更無競態殘留
- [x] 19.5 視覺回歸驗證：hover、transition、spinner、overlay 一致性

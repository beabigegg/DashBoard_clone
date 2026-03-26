## Why

目前前端樣式同時存在多份 route-local `:root` token、`body/html/*` 全域規則與大量重複 class 名稱，且 portal shell 會持續載入多個頁面樣式，導致跨頁污染與維護成本快速上升。專案已經有 CSS 契約與重構計畫草案，現在需要將其升級為可驗收、可追蹤的 OpenSpec 變更，才能穩定落地。

## What Changes

- 將 CSS 契約治理範圍擴大到 shell 載入的所有 route 樣式，而非僅限部分 shared 檔案。
- 明確要求 route 樣式以 theme root class 作用域隔離，並禁止 route-local 檔案宣告 `html/body/*` 全域規則。
- 將設計 token 的單一真實來源收斂到 `frontend/tailwind.config.js`，並要求 CSS 以 `theme()` 消費 token。
- 定義遷移期間的共存規則：允許有限 legacy CSS，但需有例外清單、里程碑與禁止新增違規項。
- 新增共享視覺語意的抽象規範：重複樣式組合應沉澱為 `ui-*` 共用元件層。
- 納入靜態 inline style 治理，要求模板中的靜態視覺樣式移出 `style="..."`。

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `style-isolation-and-token-enforcement`: 從「in-scope」擴展為所有 shell-governed route，補強 theme root、全域 selector 禁令與靜態 inline style 治理。
- `tailwind-design-system`: 強化 token 單一來源與 `theme()` 使用契約，並規範共享視覺語意的 `ui-*` 抽象化要求與遷移共存邊界。

## Impact

- **Contract / plan documents**
  - `contract/css_development_contract.md`
  - `contract/css_refactoring_plan.md`
- **Frontend style architecture**
  - `frontend/src/styles/tailwind.css`
  - `frontend/tailwind.config.js`
  - `frontend/src/*/style.css`
  - `frontend/src/*/styles.css`
- **Route entry and shell loading paths**
  - `frontend/src/portal-shell/nativeModuleRegistry.js`
  - route-level `App.vue` root containers
- **Governance tooling**
  - style lint / CI checks for forbidden selectors, token usage, and static inline style

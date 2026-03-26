## Context

現行前端樣式結構已累積大量 legacy 模式：多個 route 樣式檔同時定義 `:root` tokens、`body/html/*` 全域規則、重複的通用 class（如 `.btn`, `.header`, `.panel`），且 token 消費幾乎完全依賴 `var(--*)`。同時，portal shell 透過動態 loader 載入多頁樣式並常駐，讓 class 名衝突與 cascade 汙染風險顯著放大。

盤點基線（2026-03-10）：
- CSS 檔案數：23
- CSS 總行數：約 9,117
- `:root` 定義：8 處
- `var(--*)` 使用：410 處
- CSS `theme()` 使用：0 處
- 靜態 inline `style="..."`（Vue）：59 處

限制條件：
- 必須維持既有頁面可運行，不可一次性大爆改。
- preflight 已停用，base reset 必須明確集中治理。
- 路由模組多、交叉載入高，需優先處理隔離與防回歸機制。

## Goals / Non-Goals

**Goals:**
- 讓 CSS 行為符合契約：作用域隔離、token 單一來源、禁止 route-local 全域 reset、治理靜態 inline style。
- 建立可漸進執行的遷移路徑與驗收門檻，避免一次性重構風險。
- 將高重複視覺語意收斂為共享 `ui-*` 元件層，降低後續樣式分歧。
- 導入自動化檢查，避免新違規持續累積。

**Non-Goals:**
- 不追求本次把所有頁面完全改寫為純 Tailwind utility。
- 不改動後端 API 行為與資料模型。
- 不在本次重構中全面重設所有 UI 視覺設計語言。

## Decisions

### 1. 採用四階段漸進式遷移，而非一次性重寫

**Decision**
- Phase 0（治理準備）：建立 route/theme root 對照表、違規基線報表、例外清單格式。
- Phase 1（隔離優先）：補上每個 route 根容器 `theme-*` class，將 route 規則改為 theme scope，移除 route-local `html/body/*`。
- Phase 2（token 收斂）：把設計 token 收斂到 `tailwind.config.js`，以 `theme()` 取代 token 類 `var()`。
- Phase 3（治理收斂）：處理靜態 inline style、抽象高重複 `ui-*` 元件，補齊 CI 規則。

**Rationale**
- 先止血（隔離）再收斂（token），可降低視覺回歸與衝突風險。

**Alternatives considered**
- Big-bang 全量改寫：速度快但風險不可控，回歸面積過大。

### 2. 明確區分「設計 token」與「區域運算變數」

**Decision**
- 設計 token（顏色、字級、間距、陰影等）必須在 `tailwind.config.js` 定義並用 `theme()` 消費。
- 僅允許區域運算變數保留 CSS custom properties，且必須在 `.theme-*` 作用域內，不得放在 `:root`。

**Rationale**
- 保留必要彈性（例如局部布局計算）同時維持 token 一致性與可治理性。

**Alternatives considered**
- 禁止所有 CSS 變數：過度僵化，對圖表與互動布局不實際。

### 3. 共享語意以 `ui-*` 收斂，頁面差異維持在 theme scope

**Decision**
- 重複出現 >=3 次的視覺語意（按鈕、卡片、輸入框、狀態標記）沉澱到 `frontend/src/styles/tailwind.css` 的 `@layer components`，命名為 `ui-*`。
- route 特有差異保留在 `.theme-*` 下，避免跨頁污染。

**Rationale**
- 同時達成可重用與隔離，避免全專案 class 名互踩。

**Alternatives considered**
- 完全維持 route-local class：短期快，長期分歧持續放大。

### 4. 自動化檢查作為遷移護欄

**Decision**
- 新增 lint/check 規則，至少覆蓋：
  - route CSS 禁止新增 `:root` token 與 `html/body/*` 規則
  - token 類樣式不得用硬編碼顏色替代
  - Vue 模板禁止靜態 `style="..."`（保留 `:style` 動態綁定）

**Rationale**
- 沒有守門機制，重構完成後會快速回彈。

**Alternatives considered**
- 只靠 code review：可行但不穩定，無法規模化。

## Risks / Trade-offs

- **[Risk] 批次加 prefix 誤傷 at-rule（如 `@keyframes`）** → 以 selector-aware 工具或腳本處理，只改一般規則，at-rule 白名單保留。
- **[Risk] token 映射不完整造成視覺差異** → 建立 token mapping 表與視覺回歸清單，分頁驗收。
- **[Risk] 多路由共載時仍有漏網 class 衝突** → 先處理高衝突類（`.btn/.header/.panel`）並在 shell 路由切換情境回歸測試。
- **[Trade-off] 遷移期間會短暫同時存在新舊風格** → 透過里程碑與例外到期機制控制時間窗。

## Migration Plan

1. 盤點並鎖定基線：輸出違規報表與優先順序（shared 檔與高流量頁先）。
2. 先改隔離：每頁補 `theme-*` root，route CSS 全面加 scope，搬移全域 reset 到 `@layer base`。
3. 再改 token：建立 token map，逐檔把 token 類 `var()`/硬編碼替換為 `theme()`。
4. 收斂共享語意：將高重複樣式抽到 `ui-*` 並替換使用點。
5. 佈署治理：CI 規則上線，未遷移例外需具 owner+deadline。
6. 完成後收斂：清理過期例外，將契約與重構計畫更新為穩態文檔。

Rollback strategy:
- 每一階段以 route 群組為單位提交；若出現重大視覺回歸可回退該群組變更，不影響其他群組。

## Open Questions

- `theme-*` 命名是否採用「域別」(`theme-resource/theme-wip`) 還是「路由別」(`theme-query-tool` 等) 為主？
- 靜態 inline style 治理是否允許「過渡期白名單」，或直接全量禁止並一次清空？

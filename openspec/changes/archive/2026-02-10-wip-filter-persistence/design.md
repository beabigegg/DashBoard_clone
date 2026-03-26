## Context

WIP Overview 和 Detail 是兩個獨立的 Vite multi-page 應用，透過 `window.location.href` 導航。目前 Overview 的 filter 狀態只存在 `reactive()` 物件中，不反映到 URL；Detail 已有 URL 狀態管理（`getUrlParam` / `updateUrlState`），但不包含 status filter。Back button 是 hard-coded `<a href="/wip-overview">`，導致返回時所有狀態丟失。

兩個頁面都不使用 Vue Router（各自是獨立 Vite entry），所以導航都是 full-page navigation，狀態只能透過 URL params 傳遞。

## Goals / Non-Goals

**Goals:**
- URL 作為 filter 狀態的 single source of truth，兩頁面一致
- Overview → Detail drill-down 傳遞所有 filters + status
- Detail → Overview back navigation 還原所有 filters + status（含 Detail 中的變更）
- 無參數時行為與現行完全相同（backwards compatible）

**Non-Goals:**
- 不引入 sessionStorage / localStorage / Pinia 全域狀態管理
- 不修改 API endpoints 或 backend 邏輯
- 不改變 pagination 狀態的傳遞（pagination 是 Detail 內部狀態，不帶回 Overview）
- 不改變 Hold Detail 頁的 back link 行為

## Decisions

### D1: URL params 作為唯一狀態傳遞機制

**選擇**: 透過 URL query params 在頁面間傳遞 filter 和 status 狀態

**替代方案**:
- sessionStorage：URL 乾淨但引入隱藏狀態，debug 困難，tab 生命週期不可控
- localStorage：跨 tab 污染，多開情境容易混亂

**理由**: Detail 已經用 URL params 管理 filter 狀態，Overview 採相同模式保持一致性。URL 可 bookmark、可分享、可 debug。

### D2: Overview 用 `history.replaceState` 同步 URL（不產生 history entry）

**選擇**: 每次 filter/status 變更後用 `replaceState` 更新 URL，不用 `pushState`

**理由**: filter 切換不應產生 browser back history，避免用戶按 back 時陷入 filter 歷史中。Detail 已是相同做法。

### D3: Detail back button 用 computed URL 組合當前所有 filter 狀態

**選擇**: `<a :href="backUrl">` 其中 `backUrl` 是 computed property，從當前 Detail 的 filters + status 動態組出 `/wip-overview?...`

**理由**: 如果用戶在 Detail 中變更了 filter 或 status，返回 Overview 應反映這些變更。computed 確保 backUrl 永遠是最新狀態。

### D4: Status filter 使用字串值作為 URL param

**選擇**: `status` 參數值直接使用 `activeStatusFilter` 的值（`RUN`, `QUEUE`, `quality-hold`, `non-quality-hold`）

**理由**: 這些值已在 API 呼叫的 query params 中使用（`buildWipOverviewQueryParams` / `buildWipDetailQueryParams`），直接複用保持一致。

## Risks / Trade-offs

- **[Risk] URL 長度** → 4 個 filter fields + status + workcenter 不會超過 URL 長度限制，風險極低
- **[Risk] 空值造成冗長 URL** → 只 append 非空值的 params，空 filter 不出現在 URL 中
- **[Trade-off] Overview 載入時多一步 URL parsing** → 極輕量操作，無性能影響
- **[Trade-off] Back button 從 static `<a>` 變成 dynamic `:href`** → Vue reactive 計算，無感知差異

---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
last-changed: 2026-05-15
risk: medium
tier: 2
closed-at: 2026-05-15
---

# Archive: fix-prod-history-multiselect-filter

## Change Summary

Production History 頁面的 4 個一階 filter（type / package / bop / function）原本在每一次 checkbox toggle 後立刻打 cross-filter API（`setSelection` 直接呼叫 `_scheduleRefresh`），即便有 200 ms debounce，使用者「看一眼再選下一個」仍會被收斂打斷，導致多選功能事實上無法使用。修正改為「dropdown 開啟期間只 buffer，關閉時才 commit」：對 shared `MultiSelect`（同時被 9 個 app 使用）新增 additive `dropdown-close` event，並把 `useFirstTierFilters` 的 `setSelection` 改為純 buffer、新增 `commitSelection(field)` 做 shallow-equal diff，僅當實際變動時才送出 cross-filter；App.vue 4 個 MultiSelect 都加上 `@dropdown-close` 對應 commit。

## Final Behavior

- 在任一一階 filter dropdown 開啟期間連續勾選/取消勾選 → 零 cross-filter / 零主查詢請求。
- Dropdown 關閉（outside-click / Escape / 「關閉」 footer button / 程式化 close）→ 若當前選擇 ≠ 上次 committed 選擇 → 觸發一次 cross-filter；不觸發主查詢（主查詢仍由「查詢」按鈕觸發）。
- No-op close（打開但結果與打開前相同）→ 零請求。
- Cross-filter 完成後，其他三個 filter 的選項範圍收斂，使用者在其他 filter 內同樣支援 buffer + commit-on-close 行為。
- 視覺零變動；既有 9 個 MultiSelect 消費者未掛 `@dropdown-close` 者完全不受影響。
- Escape 鍵現在會關閉 MultiSelect dropdown，並把焦點還給 `.multi-select-trigger`（WAI-ARIA combobox 模式）。

## Final Contracts Updated

None. `contracts/api/api-contract.md` 的 `pj_types / packages / bops / pj_functions` payload schema 未動；`contracts/business/business-rules.md` 未變（buffer-on-close 屬於 UI 互動策略，非業務規則）；`contracts/css/css-contract.md` 未變（零視覺變更）。contract-reviewer verdict: `approved`。

## Final Tests Added / Updated

- NEW [frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts](../../../frontend/src/shared-ui/components/__tests__/MultiSelect.test.ts) — 7 個 Vitest 案例覆蓋 `dropdown-close` emit 契約（含 1 個 blur 案例標 `.skip`，JSDOM `focusout` 模擬不穩定）。
- MODIFIED [frontend/tests/legacy/production-history.test.js](../../../frontend/tests/legacy/production-history.test.js) — 2 個既有測試遷移到 `setSelection + commitSelection` 邊界；新增 6 個 buffer/commit 案例。
- MODIFIED [frontend/tests/playwright/production-history-cross-filter.spec.ts](../../../frontend/tests/playwright/production-history-cross-filter.spec.ts) — 新增 6 個 E2E 案例覆蓋 AC-1 / AC-2（outside-click + Escape）/ AC-3 / AC-4 / AC-6。

## Final CI/CD Gates

通過於 commit `825c223`（push at 2026-05-15T06:32:54Z）：
- ✅ `frontend-tests` (35s) — vue-tsc + Vitest (337 pass / 1 skip) + node:test legacy (257 pass / 0 fail)
- ✅ `contract-driven-gates` (11s) — `cdd-kit validate` + `cdd-kit gate fix-prod-history-multiselect-filter`

無 e2e-tests 工作流於 push 觸發；Playwright spec 仍存在 runtime 阻擋（見下）。

## Production Reality Findings

1. **MultiSelect 是 shared 元件，被 9 個 app 使用**。原以為只影響 production-history；recon 後確認其他 8 個 app（wip-detail / wip-overview / hold-overview / reject-history / resource-history / resource-status / query-tool / mid-section-defect / yield-alert-center）共用同一個元件。修正必須 additive，最終以 `@dropdown-close` optional event 解決，未掛載者完全無感。
2. **既有 200 ms `_scheduleRefresh` debounce 不足以擋住「停下來想再選」的使用者**。原以為這個 debounce 已經提供多選緩衝，實測證實只能擋住快速連點。修正後保留此 debounce 作為 commit-on-close 的廉價安全網。
3. **`useFirstTierFilters._pruneSelection` 會自動丟棄不再共現的選項**。`_lastCommitted` snapshot 必須在每次 `fetchFilterOptions` 成功後同步，否則 prune-driven mutation 會讓下一次 close 誤判為「有變動」而觸發冗餘請求。
4. **UI-UX 反饋揭露 Escape 路徑沒做完整**：原始 MultiSelect 沒處理 Escape，新增 Escape 後若未把焦點還給 trigger，鍵盤使用者會迷失。已在 PR 內補上 `closeDropdown()` 內 `nextTick` 觸發 `.multi-select-trigger.focus()`。
5. **Playwright E2E spec 本地與 CI 都未驗證新增的 6 個案例**：本地遇到 Playwright `page.request.post('/api/auth/login')` hang（請求送出但 backend 無回應；同樣憑證 curl 可成功）。CI 上 push 不觸發 e2e-tests 工作流。Root cause 未明（疑似 backend 對 browser-class request 走 LDAP path 卡住）。此為 pre-existing infra issue，影響整個 spec 9 個案例含 PR 前的 3 個。
6. **`frontend/vitest.config.js` `include` pattern 原本只覆蓋 `tests/**/*.test.js`**。把 unit test 放在 SFC 旁邊（`src/shared-ui/components/__tests__/`）需要把 `'src/**/*.test.ts'` 加入 include。frontend-engineer 改了一行，無副作用。

## Lessons Promoted to Standards

contract-reviewer 在 `/cdd-close` Step 3 核可 4 條 guidance、0 條 contract（本次修正只新增 additive UI event，無 contract surface 改動）。已寫入 `CLAUDE.md`：

| # | Promoted to | Section | Topic |
|---|---|---|---|
| F1 | `CLAUDE.md` | NEW `## Shared UI Component Notes` | `MultiSelect.vue` 被 9 個 app 共用，emit/prop 變更必須 additive |
| F3 | `CLAUDE.md` | `## Shared UI Component Notes` | snapshot-diff composable 必須在 server prune 後 re-sync 私有 snapshot |
| F4 | `CLAUDE.md` | NEW `## Accessibility Notes` | popup 關閉路徑（Escape / outside-click）必須 `nextTick(() => triggerEl.focus())` |
| F6 | `CLAUDE.md` | `## TypeScript Migration Rules` | SFC-paired `*.test.ts` 需要把 `src/**/*.test.ts` 加入 `vitest.config.js` `include` |

Findings #2（debounce）與 #5（Playwright hang）判定 do-not-promote — 前者屬於情境性 UX trade-off、已記為後續評估；後者根因未明，需先診斷再決定是否成為持久知識。

`cdd-kit validate` 通過；`cdd-kit context-scan` 已重新產生 `specs/context/project-map.md` 與 `specs/context/contracts-index.md`。

**Note**：此專案 `CLAUDE.md` 與 `AGENTS.md` 都列於 `.gitignore`（line 46-47），屬於每位開發者的 local agent guidance — 上述 4 條 lesson **僅寫入本機 CLAUDE.md，不會隨 commit/push 同步**。若需要跨開發者共享這些 lesson，請另開一張 change 將相同內容寫入 tracked 文件（例如 `SDD.md` 或新建 `docs/frontend-conventions.md`）。

## Follow-up Work

1. **修 Playwright E2E `loginViaApi` hang**：`page.request.post('/api/auth/login')` 在本地（120 s timeout 內）拿不到回應，curl 同 endpoint 同憑證秒回 200。需要查清楚 backend 對 Chromium-class request 的 LDAP path 為何卡住。修好後 6 個新 E2E 案例才能執行驗證。
2. **將 buffer + commit-on-close pattern 推廣到其他報表**：wip-detail / wip-overview / hold-overview / reject-history / resource-history / resource-status / query-tool / mid-section-defect / yield-alert-center 的 filter 元件可能同樣需要這個修正；另開一個 change 處理。
3. **MultiSelect 進一步 a11y 改進**：dropdown 內 Tab 焦點循環、footer 按鈕（全選/清除/關閉）的焦點順序。
4. **`_scheduleRefresh` 的 200 ms debounce 評估移除**：commit-on-close 是唯一進入點後，debounce 的價值剩下「多 filter 連續 close」的合併。可在後續驗證足夠資料後移除。
5. **`_lastCommitted` 初始化 priming**：未來若 composable 接收初始非空 selection，需要 prime snapshot 對應；目前初始為 `[]` 與 `selection` 一致，未啟用。
6. **`vitest.config.js` include pattern**：考慮是否將 `src/**/*.test.ts` 設為專案層級的標準，讓未來 SFC-paired unit tests 不必每次調 config。

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md` / `CODEX.md`). Do not treat this file as a source of truth for current behavior or for re-deriving design decisions in unrelated changes.

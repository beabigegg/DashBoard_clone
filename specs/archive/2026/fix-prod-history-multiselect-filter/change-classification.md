# Change Classification

## Change Types
- primary: bug-fix
- secondary: ui-behavior

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- no
- reason: 不變更架構；只調整既有 filter 元件的事件觸發時機（多選緩衝 + dropdown 關閉時 apply）。

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | 需明確記錄目前每次 checkbox click 即 emit 的位置，方便 reviewer 不重讀程式即可驗證修正點 |
| proposal.md | no | 解法明確（buffer selection + apply on dropdown close），單一可行路徑 |
| spec.md | no | tier-2 UI bug fix，change-request + classification + current-behavior 已足 |
| design.md | yes | 若觸碰共用 dropdown 或 useFilterOrchestrator，需在一頁 design 釐清「buffered apply」契約並標明影響範圍是 feature-local 或 shared，避免回歸 wip / hold-history |
| qa-report.md | yes | tier-2 預設需要 QA 簽核 |
| regression-report.md | no | 不涉及 schema/data；視覺與 API 介面不變 |

## Required Contracts
- API: contracts/api/api-contract.md（不變更 endpoint，僅確認多選後 payload 仍符合既有契約）
- CSS/UI: contracts/css/css-contract.md（不新增 token、不變更視覺，需確認契約未被破壞）
- Env: 無
- Data shape: 無
- Business logic: contracts/business/business-rules.md（可能新增一條「一階 filter apply trigger = dropdown 關閉」行為規則）
- CI/CD: 無新增

## Required Tests
- unit: production-history filter composable 緩衝勾選邏輯 / no-op 偵測（先寫失敗測試 → 修補）
- contract: 確認 cross-filter / 主查詢 payload 仍符合 api-contract
- integration: 無
- E2E: 更新 production-history-cross-filter.spec.ts — 多次 checkbox toggle 期間 request 數為 0；dropdown 關閉觸發單一 cross-filter + 單一主查詢
- visual: ui-ux + visual reviewer 確認無視覺變動
- data-boundary: 不適用
- resilience: 不適用
- fuzz/monkey: 不適用
- stress: 不適用
- soak: 不適用

## Required Agents
- change-classifier (done)
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- frontend-engineer
- ui-ux-reviewer
- visual-reviewer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: 在任一第一階 filter (type / package / bop / function) 的 dropdown 內勾選或取消勾選 item，dropdown 仍開啟期間，前端不發送主查詢 (production-history 主資料) 也不發送 cross-filter 收斂請求（網路請求數為 0）。
- AC-2: 當 dropdown 關閉（blur / 點 dropdown 外面 / Escape）時，該 filter 的最終勾選集合一次性套用；若集合與套用前狀態不同，觸發一次 cross-filter 重算讓另外 3 個 filter 的可選範圍依目前選擇收斂，並觸發一次主查詢更新表格。
- AC-3: 經 cross-filter 收斂後，使用者在其他三個 filter 中的任何一個 dropdown 內，同樣可在不觸發查詢的情況下多選 item；行為（多選暫存、關閉時 apply、cross-filter 收斂）四個 filter 完全一致。
- AC-4: 在 dropdown 內進行多選後若使用者最終勾選結果與打開前相同（例如先勾再取消），dropdown 關閉時不應觸發任何 cross-filter 或主查詢請求（no-op 防抖）。
- AC-5: 維持既有視覺呈現與 design tokens：不新增 Apply 按鈕、dropdown 樣式、checkbox 樣式、欄位排版皆無視覺差異（CSS / DOM 結構僅在事件 wiring 層面變動）。
- AC-6: 不變更後端 API 介面與請求參數 schema；單次 cross-filter / 主查詢請求 payload 在多選情境下仍符合既有 contracts/api/api-contract.md 的 production-history endpoint 定義。

## Tasks Not Applicable
- not-applicable: 3.4, 3.5, 4.1, 4.3

## Clarifications or Assumptions
- 假設目前共用的 multi-select dropdown 元件位於 frontend/src/shared-ui/ 或 production-history 自有 components/；實際路徑由 frontend-engineer 在 plan 階段確認。
- 假設 `useFilterOrchestrator.ts` 是觸發 cross-filter 的中央點；若 emit 點實際在元件層，design.md 會另行記載。
- 「Dropdown 關閉時套用」涵蓋 blur、點外部、Escape 三個來源；不含元件 unmount。

## Context Manifest Draft

### Affected Surfaces
- production-history feature app
- 共用 filter / multi-select dropdown 元件（若被 production-history 使用）
- 共用 filter orchestrator composable

### Allowed Paths
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- contracts/api/
- contracts/business/
- contracts/css/
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

### Agent Work Packets

#### change-classifier
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- contracts/api/
- contracts/business/
- contracts/css/
- specs/changes/fix-prod-history-multiselect-filter/
- specs/context/contracts-index.md

#### test-strategist
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- specs/changes/fix-prod-history-multiselect-filter/

#### ci-cd-gatekeeper
- contracts/
- specs/changes/fix-prod-history-multiselect-filter/

#### implementation-planner
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- specs/changes/fix-prod-history-multiselect-filter/

#### frontend-engineer
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/playwright/
- specs/changes/fix-prod-history-multiselect-filter/

#### ui-ux-reviewer
- frontend/src/production-history/
- frontend/src/shared-ui/
- contracts/css/
- specs/changes/fix-prod-history-multiselect-filter/

#### visual-reviewer
- frontend/src/production-history/
- frontend/src/shared-ui/
- specs/changes/fix-prod-history-multiselect-filter/

#### qa-reviewer
- specs/changes/fix-prod-history-multiselect-filter/
- frontend/tests/

---
change-id: downtime-analysis-page
archived: 2026-06-01
schema-version: 0.1.0
---

# Archive: downtime-analysis-page

> **Cold Data Warning:** This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).

---

## Change Summary

新增「設備停機與維修分析」頁面（`/downtime-analysis`），供工廠設備工程師與主管自助查詢 MES 的 E10 停機時數（UDT/SDT/EGT）、大類別分析、停機原因排行、設備明細、以及關聯工單（JOB）明細。後端採用 Type-A spool 模式（POST /query → spool → GET /view），以 DuckDB parquet 快取 Oracle 查詢結果。前端為獨立 Vue3 SPA，透過 portal-shell 懶加載。

---

## Final Behavior

- `GET /api/downtime-analysis/options` — 回傳 workcenter/family/resource/package_group/big_category/reason 篩選項（設備以 RESOURCENAME 顯示）
- `POST /api/downtime-analysis/query` — Oracle 查詢 → 60s 容差跨班次合併（DA-02）→ JOBID 橋接（Path A: JOBID 直配, Path B: RESOURCEID+時間重疊）→ spool；支援 workcenter/family/resource/package_group/big_category/status_type/is_production/is_key/is_monitor 濾鏡
- `GET /api/downtime-analysis/view` — 從 spool 重組 summary/daily_trend/big_category/top_reasons
- `GET /api/downtime-analysis/equipment-detail` — 設備維度停機彙總
- `GET /api/downtime-analysis/event-detail` — 停機事件分頁明細，含 JOB 橋接來源標記（jobid/overlap/none）
- FilterBar 有 生產設備/重點設備/監控設備 checkbox 及日期/粒度/工站/型號/設備/停機類型 篩選
- 設備 dropdown 與明細表顯示 RESOURCENAME（不顯示 RESOURCEID）
- `DOWNTIME_BRIDGE_VERSION` 常數控制 spool cache key 失效（DA-06）

---

## Final Contracts Updated

- `contracts/api/api-contract.md` §10 — 新增 5 endpoints（api 1.13.1）
- `contracts/data/data-shape-contract.md` §3.12 — 新增 DowntimeKpiShape/DailyTrendRow/BigCategoryRow/TopReasonRow/EquipmentDetailRow/EventDetailRow/JobEnrichment（data 1.12.1）
- `contracts/business/business-rules.md` DA-01..DA-06 — E10 filter / cross-shift merge / JOBID bridge / big-category taxonomy / wait-repair hours / bridge-version invalidation（business 1.12.1）
- `contracts/css/css-contract.md` — `.theme-downtime-analysis` 新增到 portal-shell CSS scope 條款
- `contracts/CHANGELOG.md` — api 1.13.0→1.13.1, data 1.12.0→1.12.1, business 1.12.0→1.12.1

---

## Final Tests Added / Updated

**Backend（pytest）:**
- `tests/test_downtime_analysis_service.py` — 63 tests（DA-01..DA-06 各 business rule；filter cross-narrow；bridge version cache key）
- `tests/test_downtime_analysis_routes.py` — 29 tests（5 endpoints；kwarg forwarding per-kwarg；granularity 400 rejection）
- `tests/test_api_contract.py` — 28 new tests（§3.12.1..§3.12.7 shape contract）
- `tests/test_modernization_policy_hardening.py::TestDowntimeAnalysisPage` — 3 asserts（page_status, asset_readiness_manifest, route_scope_matrix）
- `tests/e2e/test_downtime_analysis_e2e.py` — 4 local_e2e tests

**Frontend（vitest）:**
- `frontend/src/downtime-analysis/__tests__/formatDowntimeDate.test.ts` — midnight-UTC DATE boundary
- `frontend/src/downtime-analysis/__tests__/useBigCategory.test.ts`
- `frontend/src/downtime-analysis/__tests__/useFilterState.test.ts`
- `frontend/src/downtime-analysis/__tests__/css-scope.test.ts`

**Playwright:**
- `frontend/tests/playwright/downtime-analysis.spec.js` — 4 tests（ESM; mock all 6 API routes）

---

## Final CI/CD Gates

| gate | tier | result |
|---|---|---|
| lint (ruff) | 0 | PASS |
| contract-validate (cdd-kit) | 0 | PASS |
| unit-mock-integration (pytest) | 1 | PASS (4314 total) |
| frontend-unit (vitest) | 1 | PASS (487 total) |
| css-governance (css:check Rule 6) | 1 | PASS (0 unscoped) |
| playwright-downtime-analysis | 1 | PASS (CI: 6fac60c) |
| frontend-type-check (vue-tsc) | 2 (informational) | PASS |

---

## Production Reality Findings

1. **JOBID 覆蓋率缺口**：`DW_MES_RESOURCESTATUS_SHIFT.JOBID` 約 50% UDT/14% SDT 在 2025-09 後缺值（IT 尚未回填）。JOBID-primary + 時間重疊橋接（DA-03）可處理此情況；無法橋接的事件以 `match_source='none'` 呈現，JOB 欄位渲染 `—`。已核准帶風險上線；IT 回填後透過 DOWNTIME_BRIDGE_VERSION bump 觸發 spool 重建。
2. **Playwright CI 缺少 browser install**：CI runner 無預裝 Chromium；初次加入 Playwright spec 時需在 workflow 中補 `npx playwright install --with-deps chromium` step（已於 commit `6fac60c` 修正）。
3. **resource-shared CSS `:is()` 擴充**：portal-shell 的 `resource-shared/styles.css` 使用 `:is(.theme-X, ...)` 選擇器；新增頁面時需將新主題加入所有 `:is()` 群組（共 95 處），否則 header/filter/section-card 樣式不套用。已以 sed 批次處理。
4. **設備明細/事件明細資料形狀錯配**：`equipment-detail` 回傳 `{equipment_detail:[...]}` 而非陣列；`event-detail` 回傳 key 為 `events` 而非 `rows`。前端初稿讀取錯誤，修正後正常（commit `1931d26`）。
5. **AI 測試 mock 目標**：`TestCallLlmText` 應 patch `_AI_SESSION`（Session object）而非 `requests.post`，否則 mock 不攔截實際呼叫（commit `ccb9347`）。

---

## Lessons Promoted to Standards

| lesson | classification | target | evidence |
|---|---|---|---|
| L1: Playwright CI 需加 `npx playwright install --with-deps chromium` step | promote-to-guidance | `CLAUDE.md §CI Workflow Notes` | commit `6fac60c` |
| L2: `resource-shared/styles.css` `:is()` group 新頁面需批次更新全部群組 | promote-to-contract + promote-to-guidance | `contracts/css/css-contract.md` rule 4.5 (v1.6.0); `CLAUDE.md §Portal-Shell CSS Architecture Notes` | commit `1931d26`; `contracts/CHANGELOG.md ##[css 1.6.0]` |
| L3: 設備 filter 回傳 RESOURCENAME 並透過 resource_cache 解析為 ID | do-not-promote | — | 頁面特定決策，非通用規則 |
| L4: Type-A spool 前端 key 錯誤靜默空表格 | promote-to-guidance | `CLAUDE.md §Cache Architecture Notes` | commit `1931d26` |
| L5: `_AI_SESSION` 必須在 service boundary patch，不得 patch `requests.post` | promote-to-guidance | `CLAUDE.md §AI Pipeline Architecture Notes` | commit `ccb9347` |

---

## Follow-up Work

- **IT JOBID 回填**：完成後 bump `DOWNTIME_BRIDGE_VERSION`（`constants.py`）並 deploy，spool 自動失效重建。
- **週/月粒度**：`granularity` 目前僅支援 `day`；非 day 回傳 400。後續可擴充 `_build_daily_trend` 支援 week/month 重採樣。
- **落差分析（KEY IN / 切換不確實）**：列為 TBD，待 MES 資料品質確認後另立 change。

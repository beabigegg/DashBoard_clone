---
change-id: add-uph-performance-page
schema-version: 0.1.0
last-changed: 2026-07-13
---

# Interaction Design: add-uph-performance-page

## Provenance

Citations that could not resolve cleanly against the current contracts:

1. **state-initial has no contract discriminator by nature.** It is a pre-request client state ("user hasn't submitted yet"), so none of the five ADR 0012 §2 forms apply. This is inherent, not a contract gap — flagged only so the empty `discriminator` is understood, not "silently missing".
2. **Family DB/WB adornment is a gloss, not a data field.** The confirmed requirement wants the family filter labeled "GDBA/GWBA (DB/WB)". The only DB/WB provenance in the contract is per-equipment `db_wb_label` derived from WORKCENTERNAME→`workcenter_groups` (UPH-05), which can be `NULL`/unmapped — it is NOT a clean per-family mapping. Presenting GDBA=DB / GWBA=WB at the family selector is a static naming convenience, not a `data-shape` fact. See Open Decisions.
3. **`spool/status → status=failed` resolves only via the generic async envelope (§1.3), not a UPH-specific row.** The api-contract row for `/spool/status` lists errors 400/410 and `GenericSuccessResponse`; a FAILED job surfaces as a status value inside the 200 envelope. Minor; noted for completeness, not blocking.

## Screens

| screen | who is here | what they are deciding | what they fear | what would make them abandon | what must not be shown |
|---|---|---|---|---|---|
| UPH表現 page (`/uph-performance`) | a process/equipment engineer self-serving Die-Bond (GDBA) / Wire-Bond (GWBA) UPH data | which machines are underperforming on units-per-hour, and whether a Package/Type is systematically lower | trusting a "0 / empty" chart that actually means "the query broke" or "the parameter isn't collected yet", and chasing a phantom underperformer | a heavy query that spins with no progress and no way to cancel; a chart gap that looks like zero output | a fabricated/scaled UPH number (UPH-04: raw `PARAMETER_VALUE`, never `×100`/`÷100`), or a threshold "alert" color the contract explicitly does not provide |

## Presented Information

<!--
Ranking's per-row fields (sample_count, db_wb_label, workcenter_name) all cite
the same `items` array field, mirroring fix-equipment-lots-trim's precedent:
the citation resolver cannot decompose per-array-item fields further once the
array's item schema is itself a named type (`UphPerformanceRankingItem`);
citing `items` proves the array field is real and contract-typed, and
data-shape-contract.md §3.29 Ranking is the authoritative per-column source
(named in each row's rationale below).
-->

| item | rationale | provenance |
|---|---|---|
| UPH trend series per group | "How is UPH trending over the window, and does one group lag the others?" | GET /api/uph-performance/trend → series |
| Trend time-bucket labels (native M[60] hourly) | "Which hour does each trend point represent?" | GET /api/uph-performance/trend → labels |
| Current trend group dimension | "Am I looking at this grouped by family, equipment, or Package right now?" | GET /api/uph-performance/trend → group_by |
| Equipment ranking, ascending by avg UPH | "Which machines have the lowest average UPH — i.e. who are the underperformers?" | GET /api/uph-performance/ranking → items |
| Per-equipment sample_count in ranking (type/nullability: data-shape-contract.md §3.29 Ranking) | "Is this low average trustworthy, or based on too few events?" | GET /api/uph-performance/ranking → items |
| Per-equipment db_wb_label + workcenter_name in ranking (nullable when WORKCENTERNAME unmapped, UPH-05; type/nullability: data-shape-contract.md §3.29 Ranking) | "Is this a Die-Bond or Wire-Bond machine, and where does it sit?" | GET /api/uph-performance/ranking → items |
| Available Type values for the ranking's own filter | "Which Types can I narrow the ranking block to?" | GET /api/uph-performance/ranking → pj_types |
| Per-event detail rows: lot_id, equipment_id, event_time, raw uph_value, package, pj_type (type/nullability: data-shape-contract.md §3.29 Detail) | "What are the raw events behind a machine's number, so I can verify it?" | GET /api/uph-performance/detail → rows |
| Detail pagination position + total | "How many events matched, and where am I within them?" | GET /api/uph-performance/detail → meta |
| Post-spool fine-filter option lists (equipment/workcenter/package/type actually present in this result) | "Which values actually appear in the result I just pulled, so I narrow without guessing?" | GET /api/uph-performance/filter-options → equipment_id_options |
| Pre-query Package/Type dropdown options | "What Packages/Types can I choose before I've run any query?" | GET /api/uph-performance/product-filter-options → product_lines |
| Async job progress (status / pct / elapsed) | "Is my heavy query still running, and roughly how far along?" | POST /api/uph-performance/spool → 202 |

## User Intents

| id | intent | frequency | path |
|---|---|---|---|
| intent-run-query | set global filters (date range required) and run the async UPH query | every visit, first action | global filter bar → 查詢 → progress → results |
| intent-scan-trend | read UPH-over-time and regroup the trend (family / equipment / Package) | most sessions, repeatedly | results → trend chart → change group-by |
| intent-find-underperformers | read the ascending equipment ranking and narrow it by its own Type multi-select | the core goal, most sessions | results → ranking block → adjust ranking Type filter |
| intent-narrow-results | re-slice the loaded result set by equipment/workcenter/Package/Type without re-spooling | common follow-up | results → fine-filter controls → views refresh |
| intent-inspect-detail | drill into the raw per-event rows and page through them | occasional, verification | results → detail table → paginate |
| intent-recover | cancel a running job, clear/reset filters, or retry after an error/empty result | as needed | progress → cancel, or error/empty → clear / re-query |

## Controls

| id | control | intent |
|---|---|---|
| ctrl-date-range | date-range picker (required) | intent-run-query |
| ctrl-family-select | GDBA/GWBA family multi-select (closed enum; empty = both) | intent-run-query |
| ctrl-workcenter-select | WORKCENTERNAME multi-select (global) | intent-run-query |
| ctrl-package-select | Package (PRODUCTLINENAME) multi-select (global) | intent-run-query |
| ctrl-type-select-global | Type (PJ_TYPE) multi-select (global scope, feeds spool key) | intent-run-query |
| ctrl-equipment-search | equipment-ID search/multi-select (max 200) | intent-run-query |
| ctrl-submit | 查詢 (run async spool) | intent-run-query |
| ctrl-cancel-job | cancel the in-flight async job | intent-recover |
| ctrl-clear | 清除 (reset global filters to default date range) | intent-recover |
| ctrl-trend-groupby | trend group-by selector (equipment_id / family / package) | intent-scan-trend |
| ctrl-ranking-type-filter | ranking block's OWN Type multi-select, independent of the global Type filter | intent-find-underperformers |
| ctrl-fine-filter | post-spool fine-filter controls (equipment / workcenter / package / type) re-slicing the loaded result | intent-narrow-results |
| ctrl-detail-pagination | detail-table page controls (per_page ≤ 200) | intent-inspect-detail |

### Deleted Controls

| control | reason |
|---|---|
| trend day/hour granularity switch | eap-alarm's trend has one, but UPH trend is native M[60] hourly only — the contract states "no day/hour granularity switch (unlike eap-alarm trend)". A granularity control would be a lie about a switch that has no backing param. |
| threshold / alert-coloring control | explicit non-goal for this version. No endpoint or field supplies a threshold; a control here would invent product scope. |
| CSV / Parquet export button | no export endpoint exists for `/api/uph-performance/*` in the API contract. A control with no endpoint cannot be derived. |
| summary / KPI cards | eap-alarm has a `/summary` endpoint; UPH has none. No aggregate-count field exists to render. |
| separate "reset ranking filter" button | reversibility for the ranking's independent Type filter is already met by that multi-select's own clear affordance; a second global control would be a redundant, unrequested way to do the same thing. |
| pareto chart | eap-alarm's pareto is a different analysis; UPH replaces it with the ranking block. No `/pareto` endpoint exists here. |

## States

<!--
state-initial (nothing run yet, engineer must pick filters and submit) has NO
backend-contract discriminator by design: before any request is sent there is,
by definition, no field or status code to point at -- this is pure client
bookkeeping (a pre-request flag), never observable on the wire. Documented
here in prose rather than forced into the table below, mirroring
fix-equipment-lots-trim's interaction-design.md treatment of its own
client-only state-loading distinction.
-->

| id | meaning | discriminator |
|---|---|---|
| state-spooling | heavy query accepted and running; show cancellable progress | POST /api/uph-performance/spool → 202 |
| state-spool-hit | coarse-filter key already spooled (async=false branch); results available immediately, no job | POST /api/uph-performance/spool → query_id |
| state-ready-populated | spool complete and the result set has ≥1 UPH row | data-shape: non-empty dataset |
| state-empty | spool succeeded but zero UPH rows for this window/family — graceful empty, NOT an error | data-shape: empty dataset |
| state-unavailable | no worker available; purely-async page cannot fall back | POST /api/uph-performance/spool → 503 |
| state-validation-error | bad/missing dates, range > 730d, or a family outside {GDBA, GWBA} | POST /api/uph-performance/spool → 400 |
| state-expired | the spool / query_id aged out; the result can no longer be sliced and must be re-run | GET /api/uph-performance/spool/status → 410 |
| state-job-failed | the background job errored during execution (status field resolves to "failed") | GET /api/uph-performance/spool/status → status |
| state-coarse-options-degraded | the pre-query Package/Type dropdowns could not load; page still usable via other filters | GET /api/uph-performance/product-filter-options → 500 |

state-empty and state-ready-populated cite different discriminators (`zero rows for window/family` vs `non-empty dataset`), and state-empty is never conflated with state-job-failed / state-unavailable — "the parameter has no data yet" must look different from "the system broke".

## Reversibility

- **state-spooling** — the progress bar shows status/pct/elapsed and offers `ctrl-cancel-job`; cancelling returns cleanly to state-initial (or the prior loaded result), matching eap-alarm's `cancelAsyncJob`. The user always knows a job is running and can get out.
- **Global filters (coarse)** — each applied filter is visible in the global bar; `ctrl-clear` resets to the default date range. The user can always see and undo what was submitted.
- **Ranking independent Type filter** — because this filter is decoupled from the global Type filter, the user must be able to tell (a) that it is narrowed and (b) that its scope is the ranking block only. Its own clear affordance is the exit; it must never silently inherit or overwrite the global Type selection.
- **Fine filters (post-spool)** — auto-apply on change (no submit, mirroring eap-alarm's FineFilterBar) and re-slice the existing spool; clearing them returns to the full loaded result without re-spooling.
- **state-empty** — must offer the way back in plain language: widen the date range / adjust family or filters and re-run. Without that, the engineer cannot distinguish "I filtered myself to nothing" from "there is genuinely no UPH signal".
- **Trend group-by** — the current dimension is shown (`group_by` in the response); switching back is immediate and non-destructive.

## Consistency Commitments

Closest precedent: **eap-alarm** (same drawer sibling `production-achievement` for the async page shell).

- **Async progress = one form, one meaning.** Reuse `AsyncQueryProgress` + hide the page `LoadingOverlay` while a job is active (css-contract 4.6), exactly as eap-alarm. A spinning heavy query always looks the same across both pages.
- **Empty ≠ broken.** `EmptyState` is reserved for state-empty and state-initial; errors (503 / job-failed / expired) use `ErrorBanner`. These two visual languages must never swap.
- **Coarse-submit vs fine-auto-apply distinction is preserved.** Global filters require an explicit 查詢 (they rebuild the spool key); fine filters and the ranking Type filter auto-apply against the existing spool. The same "multi-select" widget must not silently carry both meanings without a visible submit boundary.
- **The two Type selectors must be visibly different.** `ctrl-type-select-global` (feeds the spool key) and `ctrl-ranking-type-filter` (ranking-only, not part of the spool key) are the SAME widget shape carrying DIFFERENT meaning and DIFFERENT scope. They must be labeled/placed so a user can never mistake one for the other. This is the single highest-risk consistency point in this design, because the independent ranking filter is a deliberate, human-requested decoupling.
- **A trend gap is not a zero.** Missing hour buckets arrive as `null`, never `0`. The chart must render a gap as a gap.

## Open Decisions

- [x] **Empty-state wording.** When BondUPH/fHCM_UPH return zero rows, what exact message? Options: (a) generic "no UPH data for these filters, widen the window"; (b) family/parameter-specific, calling out that GWBA/fHCM_UPH was configured recently and may not yet have data. Trade-off: (b) is more honest about the known data risk but leaks a parameter name to end users.
- [x] **Ranking independent Type filter default.** Should `ctrl-ranking-type-filter` default to all-Types-selected (show everything, ranked) or none-selected (force the engineer to pick a Type before the ranking populates)?
- [x] **Trend legend interaction.** Should clicking a legend entry hide/show that series (standard ECharts behavior) or be inert?
- [x] **Default trend group-by.** Contract default is `family`. Confirm the product wants `family` as the landing view vs `equipment_id` (more granular) vs `package`.
- [x] **Detail table page size.** Contract caps `per_page` at 200; eap-alarm defaults to 20. What default page size, and do we expose a page-size control at all?
- [x] **`product-filter-options` (500) failure behavior.** When the pre-query Package/Type coarse dropdowns fail to load, degrade silently (dropdowns just empty, other filters still work) or show an inline warning?
- [x] **Surface a distinct post-spool fine-filter bar?** Should `ctrl-fine-filter` be a visible dedicated bar (like eap-alarm) or should re-slicing be driven only implicitly (e.g. clicking a ranked machine to filter the detail)?
- [x] **Family DB/WB adornment semantics.** Is "GDBA=DB / GWBA=WB" an approved static label on the family filter, or should any DB/WB shown be the data-derived per-equipment `db_wb_label` (which can be NULL)? These can disagree for a given machine.

## Confirmed

<!-- AGENT-FORBIDDEN. No agent -- not interaction-designer, not main Claude acting on its own judgment, not any other role -- may invent, paraphrase, or "fill in" an answer here. -->

**2026-07-13 — human answers, transcribed verbatim:**

1. **Empty-state wording**: 通用提示：「此範圍無 UPH 資料，請放寬日期或調整篩選器」(generic message; does not name `BondUPH`/`fHCM_UPH` or any internal parameter).
2. **Ranking Type filter default**: 默認不選（要求工程師先選 Type 才顯示排行）— defaults to none-selected; the ranking block stays empty/prompting until the engineer picks at least one Type.
3. **Default trend group-by**: 依照機型分組 — defaults to `group_by=family` (GDBA vs GWBA), matching the contract's stated default.
4. **Fine-filter bar**: 要，顯示一列狨立的細篩選列（與 eap-alarm 一致）— yes, `ctrl-fine-filter` is a visible dedicated bar, consistent with eap-alarm's FineFilterBar.
5. **Trend legend interaction**: 可點擊圖例隱藏/顯示系列（推薦）— legend clicks toggle series visibility (standard ECharts behavior).
6. **`product-filter-options` 500 failure behavior**: 顯示內背提示訊息（inline warning）— show an inline warning banner near the Package/Type dropdowns; other filters remain usable.
7. **Family DB/WB adornment**: 不要，篩選器只顯示 GDBA/GWBA，DB/WB 標籤只在排行區當筆資料 db_wb_label 存在時顯示 — the global family filter shows only "GDBA"/"GWBA" with no static DB/WB gloss; the DB/WB label appears only in the ranking block, per-row, sourced from `db_wb_label` (and is absent/blank when that field is `NULL`).
8. **Detail table page size**: 50 — default `per_page=50` for the detail table (contract cap remains 200); no page-size control was separately requested.

<!-- Once every Open Decisions item above has a real transcribed answer here, lock this file against later tampering by running: cdd-kit design confirm <this-change-id> -->

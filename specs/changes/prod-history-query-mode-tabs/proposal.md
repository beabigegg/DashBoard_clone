---
change-id: prod-history-query-mode-tabs
schema-version: 0.1.0
last-changed: 2026-05-14
risk: medium
tier: 2
---

# Proposal: prod-history-query-mode-tabs

## Architecture Summary

The Production History 查詢 page splits into two explicit query-mode tabs, each
owning a self-contained validation rule set: Tab A (classification) requires
`pj_types` + a date range; Tab B (identifier) requires only wildcard tokens and
treats dates as genuinely optional. The only architecturally non-obvious decision
is the backend no-date query path: when identifier tokens are present and no dates
are supplied, the backend substitutes a **wide default window** (the existing
`MAX_DATE_RANGE_DAYS` = 730-day cap, anchored at "today") instead of dropping the
`TRACKINTIMESTAMP` predicate. This keeps the entire chunked-scan + spool + DuckDB
pipeline structurally unchanged — the change is a conditional date-default inside
`validate_query_params`, not a new query path. Frontend adds a tab control, a
mode-scoped payload builder, and a broadened 清除篩選 reset spanning both
composables.

## Affected Components

| component | file path(s) | nature of change |
|---|---|---|
| Query param validation | `src/mes_dashboard/services/production_history_service.py` | `validate_query_params` becomes mode-aware: dates optional when wildcard tokens present, else still required; injects wide-window default when no dates |
| Oracle chunk pipeline | `src/mes_dashboard/services/production_history_service.py` | No structural change — `_run_oracle_to_spool` / `decompose_by_time_range` consume the normalized (possibly defaulted) date range as today |
| SQL templates | `src/mes_dashboard/sql/production_history/main_query.sql`, `count_query.sql` | No change — `TRACKINTIMESTAMP` predicate stays; the wide window flows through the same binds |
| Route layer | `src/mes_dashboard/routes/production_history_routes.py` | No logic change; relies on validation; error envelope unchanged |
| DuckDB view runtime | `src/mes_dashboard/services/production_history_sql_runtime.py` | No change — result row shape identical |
| Page shell + tabs | `frontend/src/production-history/App.vue` | New two-tab control; per-tab field visibility (Tab B hides date row) |
| Query composable | `frontend/src/production-history/composables/useProductionHistory.ts` | Mode-aware validation + payload builder (omit `start_date`/`end_date` in identifier mode when unset); broadened `clearAll` |
| First-tier filters composable | `frontend/src/production-history/composables/useFirstTierFilters.ts` | `clearAll` wired into the new 清除篩選 button |
| Styles | `frontend/src/production-history/style.css` | Tab + 清除篩選 button styling using existing Tailwind tokens; no new `@layer` |
| Contracts | `contracts/api/api-contract.md`, `contracts/business/business-rules.md`, `contracts/css/css-contract.md` | Conditional-optional dates; per-mode validation rule; tab/button token compliance note |
| i18n | locale bundles under `frontend/src/production-history/` | Tab labels, 清除篩選, mode validation messages synced across all locales |

## Key Decisions

- **No-date identifier query path → Option B (wide default window).** When
  identifier wildcard tokens are present and no dates are supplied,
  `validate_query_params` substitutes `end_date = today` and
  `start_date = today − MAX_DATE_RANGE_DAYS` (730 days), then proceeds exactly as
  the classification path. *Rationale:* the chunked-scan pipeline
  (`decompose_by_time_range` → `execute_plan` → `merge_chunks_to_spool`) is
  structurally bound to a finite `(start_date, end_date)` pair, and `main_query.sql`
  binds `TRACKINTIMESTAMP` in its fixed WHERE clause (not in the
  `{{ EXTRA_FILTERS }}` placeholder). Option B is the only choice that keeps both
  the SQL template and the chunk loop byte-identical, bounds Oracle load to the
  same envelope already enforced for classification queries, and is
  deterministically testable. AC-5 is verified by
  `test_query_identifier_wide_window_bounded`: assert the no-date identifier path
  produces chunk binds whose span equals the 730-day cap (and `chunk_start` ≥
  today − 730d), proving no unbounded predicate reaches Oracle.
  - *Rejected — A (truly unbounded):* would require editing `main_query.sql` to
    make the date predicate conditional, introducing a second SQL shape and a
    full-table-scan risk on `DWH.DW_MES_CONTAINER` that depends entirely on
    Oracle's index-access choice — not deterministically testable and a silent
    regression risk if the optimizer ever picks a different plan.
  - *Rejected — C (unbounded + ROWNUM safety cap):* same SQL-shape divergence as
    A, plus a row cap produces non-deterministic *truncated* result sets
    (arbitrary which rows survive), which violates the data-shape expectation and
    is worse UX than a 2-year window for an identifier lookup. The existing
    `MAX_ROWS_PER_CHUNK` guard already provides a per-chunk backstop under
    Option B.
- **Wide-window anchor = "today", not "earliest data".** Anchoring at today keeps
  the window deterministic across calls and dataset_id stable enough for spool
  reuse within a day; an "all data ever" anchor would be unbounded again. 730 days
  is reused (not a new constant) so there is one cap to reason about. Identifier
  lots older than 2 years are an accepted edge case — the user can switch to a
  date-bearing query; this is documented in `business-rules.md`.
- **One mode = one validation rule set.** Validation is cleanly split: Tab A
  enforces `pj_types` + dates; Tab B enforces ≥1 wildcard token and never
  inspects dates. The two rule sets do not share conditional branches beyond the
  shared wildcard parser. *Cross-cutting concern:* the active tab is the single
  source of truth for which payload fields are sent — the frontend must not send
  stale date state from a previously-visited Tab A when the user submits from
  Tab B (the payload builder is mode-gated, and 清除篩選 resets both).
- **Backward compatibility preserved.** Callers that always send
  `start_date`/`end_date` (classification flow, existing tests) hit the unchanged
  branch — same binds, same dataset_id, same spool. The new behaviour is reached
  only when dates are absent *and* tokens are present.

## Migration / Rollback

No data migration. No spool schema change — `main_query.sql` output columns are
untouched, so existing `tmp/query_spool/production_history/*.parquet` files stay
compatible. Rollback is a pure code revert of the validation branch and the
frontend tab UI; no parquet cleanup required. The API contract bump
(`start_date`/`end_date` required → conditionally-optional) is additive —
old clients that always send dates are unaffected, so the contract change is
backward compatible and needs no client migration. If the wide-window path proves
too heavy in production, the fallback is to lower `PROD_HISTORY_MAX_DATE_RANGE_DAYS`
via env (already a tunable) rather than a code change.

## Open Risks

- `FIRSTNAME` (wafer_lots column) index coverage is unconfirmed. A wafer-lot-only
  no-date query relies on that predicate to bound the 730-day scan; if `FIRSTNAME`
  is unindexed the scan is wide but still date-bounded (not full-table). Low
  severity — backend-engineer should note this in `business-rules.md`; not a
  blocker.
- Spool reuse: the wide window's `start_date` shifts daily, so identical no-date
  identifier queries on different calendar days produce different `dataset_id`s.
  Accepted — production-history is on-demand-only and not warmup-enrolled; intra-day
  reuse still works.

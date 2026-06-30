---
change-id: msd-forward-cause-effect
schema-version: 0.1.0
last-changed: 2026-06-30
---

# Implementation Plan: msd-forward-cause-effect

## Objective
Deliver MSD forward (front-detection → downstream effect) analysis at DuckDB-backed parity with the backward path, and close the per-CONTAINERID attribution hole. Concretely: (1) write a forward lineage stage spool `(SEED_ID, DESCENDANT_ID)` + self-edge with SEED_ID denormalized onto event rows at write time; (2) re-key descendant rejects to SEED_ID in `_attribute_forward_defects` (TDD: failing test first); (3) implement `get_summary(direction="forward")` via DuckDB and retire the in-memory forward path (flip 2 `xfail(strict)` tripwires); (4) add cause→effect aggregations (`by_detection_loss_reason`, loss-reason × workcenter-group crosstab, downstream_trend, amplification KPI with divide-by-zero semantics); (5) surface fields via routes; (6) apply contract deltas + mechanical follow-up; (7) build Sankey/Heatmap/KPI/detail-column frontend. Acceptance = AC-1..AC-8 (see `change-classification.md` §Inferred Acceptance Criteria).

## Execution Scope

### In Scope
- Forward lineage stage spool writer + SEED_ID denormalization (design.md §Key Decisions: SEED_ID anchor, write-time denormalization).
- Lineage-correct forward attribution re-keying (AC-4); failing test written first.
- DuckDB `get_summary(direction="forward")`; retire in-memory forward summary; flip 2 xfail(strict) tests (AC-5, AC-6).
- New aggregation builders + amplification KPI divide-by-zero (AC-1, AC-2, AC-3, AC-7).
- Route surfacing of new fields + detail `detection_loss_reason` column.
- Contract deltas (`agent-log/contract-reviewer-deltas.md`) + mechanical follow-up (openapi ×2, response-sample capture, validators).
- Frontend Sankey hero + Heatmap toggle + amplification KPI card + detail column (AC-8); i18n all-locale sync; `.theme-mid-section-defect` scoping; Top-N truncation.
- `_TRACE_QUERY_ID_SCHEMA_VERSION` bump (parquet-schema change) + rollback `rm` runbook note.
- IF a new `register_job_type()` lands: same-PR update of `tests/test_job_registry.py` count + `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py`.

### Out of Scope (non-goals — do NOT do these)
- Control-cohort / lift / baseline analysis. AC-3 trend is trend-only (design.md §Summary; test-plan §Out of Scope).
- Enlarged Oracle fetch (scope 3b dropped); no enlarged-fetch stress.
- New env var / feature flag. DuckDB-forward is a direct replace (change-classification §Clarifications). If a cutover flag is introduced, STOP — env becomes a required contract (`env.schema.json` enum+default) + `tier-floor-override`.
- Removing the in-memory `build_trace_aggregation_from_events` builder. Keep it for one release as the cutover-revert path (ci-gates.md §Rollback Policy #2); removal is a follow-up PR.
- Re-adding any `xfail(strict=True)` marker (ci-gates.md §Rollback #3).
- Seed-root anchor / WAFER traversal forward (design.md §Key Decisions: rejected).
- Opportunistic refactor of backward-direction code paths (additive only).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend spool writer | Add forward lineage stage spool writer (mirror `_write_msd_lineage_stage_spool` ~1133) emitting `(SEED_ID, DESCENDANT_ID)` + self-edge from `children_map`; degrade to self-edge-only when `children_map` empty / `genealogy_status='error'`. Denormalize SEED_ID onto event rows at write time. | backend-engineer |
| IP-2 | spool orchestration | Wire the forward lineage writer into `execute_trace_events_job` (trace_job_service.py ~810). If a `register_job_type()` is added, update `tests/test_job_registry.py` count + `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py` same PR. | backend-engineer |
| IP-3 | parquet schema | Bump `_TRACE_QUERY_ID_SCHEMA_VERSION` (trace_job_service.py:1713) same commit as the SEED_ID column add; add `rm -f tmp/query_spool/msd-events/*_lineage.parquet` to rollback runbook. | backend-engineer |
| IP-4 | attribution (AC-4, TDD) | FIRST write `test_attribute_forward_defects_drops_split_descendant_FAILING`, confirm it fails on current code; THEN re-key descendant rejects/WIP to SEED_ID via lineage spool in `_attribute_forward_defects` (2639-2722), replacing `cid in defect_cids`. | backend-engineer |
| IP-5 | aggregations | Add `by_detection_loss_reason`, loss-reason × workcenter-group crosstab (sparse, zero-cells omitted), `downstream_trend`, amplification KPI builders. Amplification = downstream_rate ÷ detection_rate; detection_rate=0 → `null`; downstream=0 & detection>0 → `0.0` (design §Key Decisions; business MSD-07). Top-N=10 + "其他" per axis (MSD-06). | backend-engineer |
| IP-6 | DuckDB forward summary (AC-5, AC-6) | Implement `get_summary(direction="forward")` (msd_duckdb_runtime.py:374, replace forward `return None` at :415) using events single-pass GROUP BY on denormalized SEED_ID (no per-query lineage JOIN). Retire in-memory forward summary path. THEN remove 2 `xfail(strict=True)` markers (test-plan §Test Update Contract). | backend-engineer |
| IP-7 | routes | Surface new aggregation fields + detail `detection_loss_reason` column via `core/response.py` (mid_section_defect_routes.py). | backend-engineer |
| IP-8 | contracts | Apply all deltas in `agent-log/contract-reviewer-deltas.md` (§1–§7) verbatim incl. version bumps + CHANGELOG; then mechanical follow-up §below. | backend-engineer |
| IP-9 | frontend (AC-8) | Sankey hero (front reason→downstream station, `@click` on `<VChart>` cross-filter) + Heatmap toggle + amplification KPI card (display "—" when null) + DetailTable `detection_loss_reason` column. Register SankeyChart/HeatmapChart/VisualMapComponent; `.theme-mid-section-defect` scoping; i18n sync all locales; Top-N truncation. | frontend-engineer |
| IP-10 | heavy tests | Stress (spool concurrency + DuckDB forward under load) + soak; resilience (spool-miss Oracle fallback, RQ mid-orchestration failure); Playwright + visual bundle. | stress-soak-engineer, e2e-resilience-engineer, test-strategist |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | §Key Decisions (SEED_ID anchor; write-time denormalization; amplification divide-by-zero; Top-N; in-memory retirement) | implementation constraints — authoritative, do not deviate |
| design.md | §Migration / Rollback | `_SCHEMA_VERSION` bump + parquet rm; cutover-revert path |
| design.md | §Open Risks | empty `children_map` self-edge degrade; line-anchor drift; amplification denominator scope-match |
| change-classification.md | §Inferred Acceptance Criteria (AC-1..AC-8) | acceptance definitions |
| test-plan.md | AC→Test Mapping table | tests to write/run per AC |
| test-plan.md | §Notes (AC-4 TDD order); §Test Update Contract (xfail removal) | TDD sequence + tripwire flip |
| ci-gates.md | Required Gates table; §Workflow Changes (openapi-sync both files); §Rollback Policy | verification commands + rollback tripwires |
| agent-log/contract-reviewer-deltas.md | §1–§7 + §Mechanical follow-up | exact contract edits + post-edit commands |
| contracts/data/data-shape-contract.md | §3.23 (lineage spool), §3.24 (aggregation payloads) | spool/aggregation shapes (authored by IP-8) |
| contracts/business/business-rules.md | MSD-06/07/08 (Top-N, amplification, lineage attribution) | business semantics (authored by IP-8) |
| contracts/css/css-contract.md | Rule 4.2/4.3/4.4, Rule 6.x | Sankey/Heatmap scoping + Teleport tooltip wrap |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/services/mid_section_defect_service.py | edit | new lineage writer (mirror ~1133); `_attribute_forward_defects` re-key (2639-2722); aggregation builders; reuse `SPOOL_NAMESPACE`, `_STAGE_LINEAGE`. Re-confirm anchors before edit (drift risk). |
| src/mes_dashboard/services/msd_duckdb_runtime.py | edit | `get_summary` forward branch (replace `return None` :415); single-pass GROUP BY on denormalized SEED_ID; retire in-memory forward. `_STAGE_LINEAGE`="lineage" already at :35. |
| src/mes_dashboard/services/trace_job_service.py | edit | wire forward lineage writer into `execute_trace_events_job` (:810); bump `_TRACE_QUERY_ID_SCHEMA_VERSION` (:1713); optional `register_job_type()`. |
| src/mes_dashboard/services/msd_lineage_job_service.py, msd_seed_job_service.py, event_fetcher.py, lineage_engine.py | edit (as needed) | only if orchestration requires; stay additive. |
| src/mes_dashboard/routes/mid_section_defect_routes.py | edit | surface new fields + detail `detection_loss_reason` via `core/response.py`. |
| src/mes_dashboard/sql/mid_section_defect/, sql/lineage/ | add/edit | new crosstab/trend/amplification SQL if extracted. |
| tests/test_mid_section_defect_service.py | edit | AC-1/2/3/4/7 unit + data-boundary tests. |
| tests/test_mid_section_defect_engine.py | add | `test_forward_lineage_spool_self_edge_included` (AC-4). |
| tests/test_unified_spool_integration.py | edit | remove 2 `xfail(strict=True)` markers (AC-6); add `test_forward_get_summary_duckdb_path_end_to_end` (AC-5). |
| tests/integration/test_material_trace_rq_async.py | edit | `test_forward_lineage_spool_write_read_roundtrip`. |
| tests/test_job_registry.py, tests/test_query_cost_policy.py | edit (conditional) | ONLY if `register_job_type()` added: bump count + `_APPROVED_CALLERS`. |
| tests/contract/samples/ | regen | `/analysis?direction=forward` + `/analysis/detail?direction=forward` Tier-B samples; `git checkout` unrelated churn, stage only the 2. |
| tests/e2e/test_mid_section_defect_e2e.py | edit | spool-miss Oracle fallback + RQ-failure-mid-orchestration resilience. |
| tests/stress/test_mid_section_defect_stress.py | edit | concurrent forward writes + DuckDB forward under load. |
| contracts/api/api-contract.md, api-inventory.md, openapi.json (+contracts/openapi.json mirror) | edit/regen | deltas §1,§2 + openapi export ×2. |
| contracts/data/data-shape-contract.md, business/business-rules.md, css/css-contract.md, css/css-inventory.md, CHANGELOG.md | edit | deltas §3,§4,§5,§6,§7. |
| frontend/src/mid-section-defect/ | add/edit | App.vue, KpiCards, DetailTable, new Sankey + Heatmap components, i18n locale files (all). |
| frontend/tests/playwright/mid-section-defect.spec.ts | edit | AC-8 specs (Sankey click, heatmap toggle, KPI, detail column). |

## Contract Updates
Apply `agent-log/contract-reviewer-deltas.md` verbatim — do not re-derive. Summary pointers only:
- API: api-contract §4 split `/analysis` + `/analysis/detail`; add `MsdForwardAnalysisResponse` + `MsdForwardDetailResponse` Tier-B schemas; api-inventory note (delta §1, §2). Bump api 1.33.0 / inventory 1.3.0.
- CSS/UI: css-contract `msd-forward-cause-effect` block (Sankey/Heatmap under `.theme-mid-section-defect`, Teleport tooltip wrap, `@click` not `.on()`); css-inventory row note (delta §5, §6). Bump css 1.11.0 / css-inventory 1.2.8.
- Env: none (no new var/flag).
- Data shape: data-shape §3.23 lineage spool + §3.24 aggregation payloads (delta §3). Bump data 1.29.0.
- Business logic: MSD-06/07/08 + 3 decision-table rows (delta §4). Bump business 1.34.0.
- CI/CD: openapi-sync.yml already extended (ci-gates §Workflow Changes); no new gate. CHANGELOG.md gets all 5 entries (delta §7).

Mechanical follow-up (IP-8, after markdown applied — from delta §Mechanical follow-up):
1. `cdd-kit openapi export --out contracts/openapi.json`
2. `cdd-kit openapi export --out contracts/api/openapi.json`
3. Capture response samples → `tests/contract/samples/` for `/analysis?direction=forward` + `/analysis/detail?direction=forward` (Tier-B, `dataPath: "data"`, all new fields + non-null `detection_loss_reason`).
4. `git checkout tests/contract/samples/` to drop unrelated churn; stage only the 2 changed samples.
5. `pip install jsonschema && cdd-kit validate --contracts` → 0 errors.
6. `cdd-kit validate --versions` → all bumped contracts present in CHANGELOG.
7. `npm run css:check` after frontend CSS.

## Test Execution Plan
Bounded ladder (required floor): run `cdd-kit test select msd-forward-cause-effect`, then `cdd-kit test run msd-forward-cause-effect --phase collect`, `--phase targeted`, `--phase changed-area`. Add `--phase contract` (response-sample/openapi edits) and `--phase quality` (css:check) per their triggers. Full ladder in test-plan.md / `references/sdd-tdd-policy.md`. Before push, run the full pytest suite locally (stale assertions in other files pass the bounded gate but fail CI `unit-and-integration-tests`).

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_mid_section_defect_service.py::test_by_detection_loss_reason_aggregation | aggregation by LOSSREASONNAME present |
| AC-1 | tests/test_mid_section_defect_service.py::test_by_detection_loss_reason_top_n_truncation | remainder folds to "其他" |
| AC-2 | tests/test_mid_section_defect_service.py::test_loss_reason_workcenter_crosstab_builder | reason × workcenter-group cells (count+rate) |
| AC-2 | tests/test_mid_section_defect_service.py::test_crosstab_top_n_folds_remainder_to_other | per-axis Top-N remainder collapsed |
| AC-3 | tests/test_mid_section_defect_service.py::test_downstream_reject_trend_no_control_cohort | trend present, NO baseline cohort field |
| AC-4 | tests/test_mid_section_defect_service.py::test_attribute_forward_defects_drops_split_descendant_FAILING | FAILS on current code (write first) |
| AC-4 | tests/test_mid_section_defect_service.py::test_attribute_forward_defects_lineage_rekeying_passes | descendant rejects re-keyed to SEED_ID |
| AC-4 | tests/test_mid_section_defect_engine.py::test_forward_lineage_spool_self_edge_included | self-edge `(seed,seed)` present |
| AC-5 | tests/test_unified_spool_integration.py::test_forward_get_summary_duckdb_path_end_to_end | DuckDB forward summary matches contract |
| AC-5 | tests/integration/test_material_trace_rq_async.py::test_forward_lineage_spool_write_read_roundtrip | spool write→read roundtrip |
| AC-6 | tests/test_unified_spool_integration.py::TestMsdChain::test_summary_from_spool | green, marker removed |
| AC-6 | tests/test_unified_spool_integration.py::TestMsdChain::test_full_chain_summary_detail_export_consistency | green, marker removed |
| AC-7 | tests/test_mid_section_defect_service.py::test_amplification_kpi_detection_rate_zero_emits_null | detection_rate=0 → null |
| AC-7 | tests/test_mid_section_defect_service.py::test_amplification_kpi_downstream_rate_zero_emits_zero_float | downstream=0,detection>0 → 0.0 |
| AC-7 | tests/test_mid_section_defect_service.py::test_amplification_kpi_both_rates_nonzero_correct_ratio | correct ratio |
| AC-8 | frontend/tests/playwright/mid-section-defect.spec.ts (Sankey click; KPI not-dash; detail column; heatmap toggle) | UI interactions pass |
| AC-1–AC-5 | tests/contract/samples/ (forward analysis + detail regen) + `cdd-kit validate --contracts && cdd-kit openapi export --check` ×2 | samples + openapi in sync |
| AC-4+AC-5 | tests/e2e/test_mid_section_defect_e2e.py::test_forward_spool_miss_falls_back_to_oracle | resilience fallback |
| AC-5 | tests/e2e/test_mid_section_defect_e2e.py::test_rq_worker_failure_mid_orchestration_returns_error_not_500 | error not 500 |
| AC-4+AC-5 | tests/stress/test_mid_section_defect_stress.py::test_spool_concurrent_forward_writes_no_collision | no collision |
| AC-5 | tests/stress/test_mid_section_defect_stress.py::test_duckdb_forward_summary_under_load | stable under load |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Honor design.md §Key Decisions exactly — SEED_ID = detection defect-lot (NOT seed root); SEED_ID denormalized at write time (NOT query-time JOIN); amplification null/"—" on detection_rate=0; Top-N=10+"其他" per axis. Deviation requires routing back to spec-architect, not a local choice.
- Re-confirm line anchors against current source before editing (design.md §Open Risks; code-map 2026-06-30 confirms `_attribute_forward_defects` 2639-2722, lineage writer 1133-1203, forward `return None` at msd_duckdb_runtime.py:415, `_TRACE_QUERY_ID_SCHEMA_VERSION` at trace_job_service.py:1713).
- Spool/DuckDB paths must work in host AND Docker — use `QUERY_SPOOL_DIR`-relative paths, no absolute/`__file__`-root paths.
- i18n: any new user-visible text must be synced across ALL locale files (CLAUDE.md hard rule #5).
- CSS scoped under `.theme-mid-section-defect`; tokens only; `css:check` must pass.
- `git checkout tests/contract/samples/` to revert unrelated sample churn; stage only the 2 changed samples.
- Run full pytest locally before push; bounded gate misses stale cross-file assertions.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks
- Line-anchor drift: anchors re-confirmed against code-map 2026-06-30 + live grep; still re-verify in-editor before each edit (Phase 1/2 merge churn).
- New `register_job_type()` (if added) requires same-PR `tests/test_job_registry.py` count + `_APPROVED_CALLERS` (tests/test_query_cost_policy.py) updates + stress/soak entry — easy to miss; CI `unit-and-integration-tests` catches the count drift loudly.
- `_TRACE_QUERY_ID_SCHEMA_VERSION` bump invalidates all existing trace spools (hash changes) — intended for the parquet-schema change but means first post-deploy queries re-run Oracle; pair with the rollback `rm` runbook note.
- Empty `children_map` / `genealogy_status='error'` must degrade to self-edge-only so `get_summary(forward)` never returns None silently (design §Open Risks).
- Amplification denominator (detection_reject_rate) must be computed over the SAME loss-reason/SEED_ID scope as the numerator or the ratio misleads (data-shape §3.24.4; design §Open Risks).
- In-memory `build_trace_aggregation_from_events` must remain for one release as the cutover-revert path; do not delete this PR.
- Do not re-add `xfail(strict=True)` on partial rollback — use plain `xfail` + a task (ci-gates §Rollback #3).

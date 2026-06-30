---
change-id: msd-forward-cause-effect
schema-version: 0.1.0
last-changed: 2026-06-30
---

# Design: msd-forward-cause-effect

## Summary

Phase 3 brings MSD forward (front-detection → downstream effect) analysis to parity with backward's DuckDB-backed depth and closes a correctness hole. Today forward fetches downstream lineage (`children_map`) to *fetch* descendant events but then *drops* them at attribution because `_attribute_forward_defects` only keeps `cid in defect_cids`; any lot that splits/merges/renames downstream loses its rejects. Forward also writes no lineage spool, so `get_summary(direction="forward")` returns None and falls back to in-memory pandas. This change adds a forward lineage stage spool that re-keys every descendant back to its seed detection lot, rewrites attribution to follow lineage, moves the forward summary onto DuckDB (retiring the in-memory path and flipping 2 `xfail(strict)` tripwires), and adds cause→effect aggregations (front loss-reason × downstream workcenter cross-tab, downstream trend, amplification KPI) feeding a Sankey/heatmap/KPI frontend. No control-cohort/lift (backward has none either; explicitly out of scope).

## Affected Components

| component | file path(s) | nature of change |
|---|---|---|
| Forward attribution engine | `src/mes_dashboard/services/mid_section_defect_service.py` (`_attribute_forward_defects` ~2639) | re-key descendant rejects/WIP to SEED_ID via lineage instead of `cid in defect_set`; new `by_detection_loss_reason`, detection-reason × workcenter cross-tab, downstream trend, amplification builders |
| Forward lineage spool writer | `src/mes_dashboard/services/mid_section_defect_service.py` (new writer mirroring `_write_msd_lineage_stage_spool` ~1133) | write `(SEED_ID, DESCENDANT_ID, +self-edge)` rows from `children_map`; reuse `SPOOL_NAMESPACE="msd-events"`, `_STAGE_LINEAGE` |
| Spool orchestration | `src/mes_dashboard/services/trace_job_service.py`, `msd_lineage_job_service.py` | call the forward lineage writer during `execute_trace_events_job`; possible `register_job_type()` for a forward lineage job |
| DuckDB forward runtime | `src/mes_dashboard/services/msd_duckdb_runtime.py` (`get_summary` forward branch ~411) | replace `return None` with DuckDB summary built from events JOIN lineage; new cross-tab/trend/amplification SQL under `sql/mid_section_defect/` |
| Routes | `src/mes_dashboard/routes/mid_section_defect_routes.py` | surface new aggregation fields + detail "detection loss reason" column via `core/response.py` |
| Frontend | `frontend/src/mid-section-defect/` (App.vue, KpiCards, DetailTable, new Sankey + Heatmap) | Sankey hero (reason→station, click cross-filter), heatmap toggle, amplification KPI card, detail column; `.theme-mid-section-defect`, vue-echarts `@click` on `<VChart>`, i18n sync |
| Migration touch-points | `tests/test_job_registry.py`, `tests/test_query_cost_policy.py` (`_APPROVED_CALLERS`) | update job-count + approved-caller list IF a new `register_job_type()` lands |

Field/schema specifics are owned by the contracts (see references below), not restated here.

## Key Decisions

- **SEED_ID anchor = the detection defect-lot (the WB lot that got NSOP/NSOL), not the seed root.** The cause→effect question is "this front reject reason caused this downstream effect"; the detection lot is where `LOSSREASONNAME`/`REJECTQTY` and `TRACKINQTY` live (detection spool) and is already the BFS root of `children_map` in `_collect_forward_tracked_cids`. Anchoring on a wafer root would smear several detection lots into one node and break the reason→station attribution and amplification denominator. — *Rejected: seed-root anchor* (loses per-reason resolution; forward has no need to traverse to WAFER, per non-goals).

- **Spool schema is minimal `(SEED_ID, DESCENDANT_ID)` with a self-edge `(seed, seed)` included.** Mirrors backward's `_write_msd_lineage_stage_spool` self-link rationale: the seed's own intermediate-station events are stored under its own CONTAINERID and must be picked up by the JOIN. Backward's `ANCESTOR_*`/`SEED_ROOT_NAME` columns are not needed forward (no root rollup). Exact column list/types are owned by `contracts/data/data-shape-contract.md`.

- **Denormalize SEED_ID onto event rows at spool-write time (events keyed under the finer SEED_ID), NOT a query-time events→lineage JOIN.** Per CLAUDE.md cache-spool learning "stage spools under finer keys should be saved pre-filtered": the events spool rows carry only the descendant's own CONTAINERID with no back-pointer to the seed (verified gap), so write the SEED_ID column when the writer already holds `children_map`. This keeps the DuckDB summary a single-pass GROUP BY and avoids a per-query lineage JOIN on every read. — *Rejected: query-time JOIN* (re-pays lineage cost on every summary/detail read; the seed→descendant map is only cheaply available at write time inside the worker).

- **Amplification KPI = downstream_reject_rate ÷ detection_reject_rate, a within-flagged-cohort front→downstream ratio (NOT flagged-vs-clean lift).** Divide-by-zero: when `detection_reject_rate = 0` the ratio is undefined → emit `null` and display "—" (N/A), never 0 or ∞. When downstream rate = 0 (detection > 0) the ratio is a real `0.0` (effect fully absorbed). business-rules must state this is a within-cohort ratio so it is not misread as a control-cohort lift. — *Rejected: emitting ∞/clamping to a sentinel number* (pollutes sort/scale and misleads).

- **Sankey/heatmap Top-N truncation reuses the existing `TOP_N=10` + "其他" idiom from `_build_forward_charts`.** Sankey: keep the top-N detection loss-reason source nodes and top-N downstream workcenter target nodes by reject qty, fold the remainder of each axis into a single "其他" node; drop self-zero links. Heatmap: same per-axis Top-N, remainder row/column collapsed to "其他". Keeps node/cell count bounded and readable; one rule, already test-covered shape. — *Rejected: per-link global Top-N* (produces orphan nodes with no incident links).

- **Retire the in-memory forward summary path; `get_summary(direction="forward")` runs via DuckDB.** Removes the dual-path divergence the `return None` fallback caused and is the precondition for flipping the 2 `xfail(strict)` forward-summary spool tests (AC-6). — *Rejected: keep in-memory as a parallel path* (perpetuates split-brain summary logic; the strict-xfail tripwires exist precisely to force the cutover).

An ADR is warranted for the SEED_ID-anchor + write-time-denormalization decision (a non-obvious, hard-to-reverse data-model/key-anchor choice). See `docs/adr/0014-msd-forward-lineage-seed-anchor.md` (proposed).

## Migration / Rollback

The forward lineage spool is a new parquet stage under the existing `msd-events` namespace (`_STAGE_LINEAGE`); adding the `SEED_ID` column to that stage is a parquet-schema change, so bump `_SCHEMA_VERSION` in `msd_duckdb_runtime.py` in the same commit (CLAUDE.md cache-spool rule) and add an `rm` of stale `msd-events/*_lineage.parquet` to the rollback runbook. Spool/DuckDB paths stay relative (`QUERY_SPOOL_DIR`) for host+Docker parity — no absolute paths.

DuckDB-forward cutover: the assumption is a direct replace with no new env flag (per change-classification). If a cutover flag is introduced, env becomes a Required Contract (add to `env.schema.json` with enum+default) and a `tier-floor-override` covers the flag-off window. Rollback of the cutover without a flag = revert the `get_summary` forward branch to `return None`, which restores the in-memory `build_trace_aggregation_from_events` path that still exists until removed; sequence removal of the in-memory builder AFTER the DuckDB path is proven so this revert stays available for one release.

xfail tripwire: removing the 2 `xfail(strict=True)` markers is an explicit task (AC-6). Because `strict=True`, if the DuckDB path is incomplete the tests fail loudly rather than silently xpassing; do not remove markers until the forward DuckDB summary lands.

## Open Risks

- `children_map` may be empty when forward lineage resolution errors (`genealogy_status='error'`); the writer must degrade to self-edges-only so attribution still works for un-split lots and the summary is not silently empty.
- New `register_job_type()` (if added) requires same-PR updates to `tests/test_job_registry.py` count and `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py`, plus a stress/soak entry (concurrency-critical spool surface, per classification).
- `.cdd/code-map.yml` was used for symbol ranges; if it has drifted since the Phase 1/2 merge the line anchors above may be stale — implementer should re-confirm `_attribute_forward_defects` and `_write_msd_lineage_stage_spool` offsets.
- Amplification denominator depends on detection_reject_rate being computed over the same loss-reason filter as the numerator; a filter mismatch would produce a misleading ratio — contract-reviewer to pin the field definition.

## Referenced Contracts (owned by contract-reviewer)

- API: `contracts/api/api-contract.md`, `contracts/api/api-inventory.md`, `contracts/api/openapi.json` (+ mirror) — new forward aggregation fields, detail column.
- Data: `contracts/data/data-shape-contract.md` — forward lineage spool schema, re-keyed aggregations, cross-tab/trend/amplification payloads.
- Business: `contracts/business/business-rules.md` — lineage-based forward attribution, amplification within-cohort semantics + divide-by-zero, Top-N rule.
- CSS: `contracts/css/css-contract.md`, `contracts/css/css-inventory.md` — Sankey/Heatmap under `.theme-mid-section-defect`.

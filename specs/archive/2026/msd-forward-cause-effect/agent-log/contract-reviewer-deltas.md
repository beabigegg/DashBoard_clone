# Contract Deltas — msd-forward-cause-effect (authoritative; apply during implementation)

Status: **changes-required, not yet applied**. backend-engineer applies these to `contracts/` in the same PR as the code, then runs the mechanical follow-up steps. contract-reviewer re-reviews at task 5.3.

## Version bumps (frontmatter `schema-version` + `last-changed: 2026-06-30`)
| contract | from → to |
|---|---|
| contracts/api/api-contract.md | 1.32.0 → **1.33.0** |
| contracts/api/api-inventory.md | 1.2.9 → **1.3.0** |
| contracts/data/data-shape-contract.md | 1.28.0 → **1.29.0** |
| contracts/business/business-rules.md | 1.33.0 → **1.34.0** |
| contracts/css/css-contract.md | 1.10.0 → **1.11.0** |
| contracts/css/css-inventory.md | 1.2.7 → **1.2.8** |

All version entries ALSO go to `contracts/CHANGELOG.md` (the only place `validate --versions` checks).

## 1. contracts/api/api-contract.md
- Endpoint table (§4): split the MSD analysis row → `/analysis` (forward adds `by_detection_loss_reason`, `loss_reason_workcenter_crosstab`, `downstream_trend`, `amplification`; schema `MsdForwardAnalysisResponse`) and `/analysis/detail` (schema `MsdForwardDetailResponse`, gains `detection_loss_reason`).
- `## Schemas`: add Tier-B `MsdForwardAnalysisResponse` and `MsdForwardDetailResponse`. Key fields:
  - `by_detection_loss_reason[]`: `{loss_reason:str, reject_qty:int, reject_rate:number[0..1]}`
  - `loss_reason_workcenter_crosstab`: `{loss_reasons:str[], workcenter_groups:str[], cells[]:{loss_reason, workcenter_group, reject_qty:int, reject_rate:number}}` (sparse; zero-count cells omitted)
  - `downstream_trend[]`: `{date:"YYYY-MM-DD", reject_qty:int, reject_rate:number}`
  - `amplification`: `number | null` — null when detection_reject_rate=0 (display "—"); 0.0 when downstream=0 & detection>0; within-cohort ratio, NOT lift.
  - detail row gains `detection_loss_reason: string | null`.
- `## Compatibility Notes` + `## CHANGELOG` (api 1.33.0) entries per reviewer output. All additive for backward direction.

## 2. contracts/api/api-inventory.md
- Update `mid_section_defect_routes.py` cell under `## standard-json` (append the forward-fields note). Add `## Compatibility Notes` 2026-06-30 entry. No endpoint added/removed.

## 3. contracts/data/data-shape-contract.md (add §3.23 + §3.24)
- **§3.23 MSD Forward Lineage Stage Spool**: parquet `tmp/query_spool/msd-events/<trace_query_id>_lineage.parquet`. Columns `SEED_ID VARCHAR` (detection defect-lot CONTAINERID; BFS root of children_map), `DESCENDANT_ID VARCHAR`. Self-edge `(SEED_ID, SEED_ID)` always emitted. SEED_ID denormalized onto event rows at WRITE time (not query-time JOIN). Degraded-lineage: empty children_map → self-edge only, get_summary(forward) must NOT return None. Schema change → bump `_SCHEMA_VERSION` + `rm -f tmp/query_spool/msd-events/*_lineage.parquet` on deploy+rollback. No duplicate (SEED_ID,DESCENDANT_ID) rows.
- **§3.24 Aggregation payloads**: §3.24.1 by_detection_loss_reason, §3.24.2 crosstab, §3.24.3 downstream_trend, §3.24.4 amplification (denominator rule: detection_reject_rate = ΣREJECTQTY/ΣTRACKINQTY over detection lots in scope; downstream_reject_rate over DESCENDANT_ID containers in lineage spool, same scope).
- CHANGELOG `[data 1.29.0]`.

## 4. contracts/business/business-rules.md (add MSD-06/07/08 + 3 decision-table rows)
- **MSD-06** Forward Top-N: TOP_N=10 + "其他" per axis (detection-reason axis AND downstream-workcenter axis independently); Sankey drops self-zero links; TOP_N is a constant, not a query param.
- **MSD-07** Amplification = downstream_rate ÷ detection_rate over SAME SEED_ID flagged cohort; within-cohort ratio NOT flagged-vs-clean lift; detection_rate=0 → null ("—", never ∞/sentinel); downstream=0 & detection>0 → 0.0.
- **MSD-08** Forward lineage attribution: `_attribute_forward_defects` re-keys descendant rejects to SEED_ID via lineage spool JOIN (replaces `cid in defect_cids`); split/merge/rename included; genealogy_status='error' → self-edge-only graceful degrade; in-memory forward summary path retired, get_summary(forward) always via DuckDB.
- Decision-table rows: detection_rate=0→null; downstream=0&detection>0→0.0; empty children_map→self-edge-only.
- CHANGELOG `[business 1.34.0]`.

## 5. contracts/css/css-contract.md
- Add `msd-forward-cause-effect (2026-06-30)` block: Sankey/Heatmap CSS scoped under `.theme-mid-section-defect` (Rule 4.2/4.3); Teleport tooltip wrap (4.4); ECharts colors as named constants (Rule 6.x / 2.4 exempt); `@click` on `<VChart>` not imperative `.on()`; LoadingOverlay 三層 for chart loading.
- CHANGELOG `[css 1.11.0]`.

## 6. contracts/css/css-inventory.md
- Update `mid-section-defect/style.css` row note (Sankey/Heatmap styles). If chart CSS lives in `<style scoped>` → no new inventory row; if a separate `.css` source file is extracted → add a row. CHANGELOG `[css-inventory 1.2.8]`.

## 7. contracts/CHANGELOG.md
- Prepend the 5 version entries (api 1.33.0, data 1.29.0, business 1.34.0, css 1.11.0, css-inventory 1.2.8) per reviewer output.

## Mechanical follow-up (backend-engineer, after contract markdown applied)
1. `cdd-kit openapi export --out contracts/openapi.json`
2. `cdd-kit openapi export --out contracts/api/openapi.json`  (BOTH — openapi-sync gate checks both)
3. Capture response samples → `tests/contract/samples/` for `/analysis?direction=forward` and `/analysis/detail?direction=forward` (Tier-B, `dataPath: "data"`, include all new fields + a non-null detection_loss_reason).
4. `git checkout tests/contract/samples/` to drop unrelated sample churn, then stage only the 2 new/changed samples.
5. `pip install jsonschema` then `cdd-kit validate --contracts` → 0 errors.
6. `cdd-kit validate --versions` → all bumped contracts have CHANGELOG entries.
7. `npm run css:check` after frontend CSS.

## Notes
- API-surface additive; in-memory forward retirement is implementation-internal (flips 2 xfail(strict) — remove markers same PR, AC-6).
- `_SCHEMA_VERSION` bump is REQUIRED same-commit.
- New lineage spool job `register_job_type()` → update `tests/test_job_registry.py` count + `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py`.

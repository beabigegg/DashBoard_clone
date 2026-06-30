# Archive — msd-forward-cause-effect

## Change Summary
Added forward (順向) cause→effect analysis to the mid-section-defect page: from a detection
station (e.g. WB) and its scrap reasons, trace the defective lots' descendants downstream and
show how front-stage scrap reasons relate to downstream scrap reasons. Implemented over the
existing staged trace pipeline (seed-resolve → lineage → events) with a denormalised forward
lineage stage spool keyed by SEED_ID. After live validation the forward charts were redesigned
around engineer-actionable value, and several data-correctness bugs surfaced and were fixed.

## Final Behavior
- `GET /api/mid-section-defect/analysis?direction=forward` returns detection KPIs, a
  `by_front_downstream_reason_matrix` (前段報廢原因 × 下游報廢原因 關聯, cohort-membership,
  row-normalized heat-table), `by_detection_loss_reason` (now with per-reason input_qty/lot_count),
  `by_detection_machine`, `daily_trend`, and `amplification`.
- Low-value forward views removed (Sankey flow, heatmap, by_downstream_station/machine/loss_reason).
- Detection input qty = `MAX(TRACKINQTY)` over the upload session (PH-06), not the last partial.
- Detection station order is derived from the detection workcenter (robust to station label),
  fixing zeroed forward attribution/matrix/trend when the label mapped to 999.
- LOT 明細 CSV export now matches the on-screen table for both directions (forward previously
  dumped the raw events spool).
- Backward upstream attribution defect_qty no longer inflated by the lineage×events JOIN fan-out
  (a single machine could exceed the cohort total).

## Final Contracts Updated
- `contracts/data/data-shape-contract.md`: §3.23 forward lineage stage spool; §3.24.1–§3.24.5
  (by_detection_loss_reason enrichment, crosstab, downstream_trend, amplification, reason matrix).
- `contracts/business/business-rules.md`: MSD-06 (Top-N), MSD-07 (amplification), MSD-08 (lineage
  attribution), MSD-09 (reason correlation matrix), MSD-10 (detection input = session MAX).
- `contracts/api/api-contract.md` + openapi: MsdForwardAnalysisResponse / MsdForwardDetailResponse.
- `contracts/css/css-contract.md` + css-inventory: theme-scoped matrix/heatmap styles.

## Final Tests Added / Updated
- `tests/test_mid_section_defect_service.py`: TestFrontDownstreamReasonMatrix,
  TestDetectionInputPartialAggregation, by_detection_loss_reason enrichment, CSV column alignment.
- `tests/test_unified_spool_integration.py`: matrix presence + station_order-derivation regression
  + export↔detail parity.
- `tests/test_msd_duckdb_parity.py`: export parity (both directions).
- `tests/test_msd_duckdb_runtime.py`: TestBackwardAttributionNoFanout (fan-out regression).
- `frontend/tests/components/ForwardReasonMatrix.test.js` + updated playwright/legacy specs.

## Final CI/CD Gates
Per `ci-gates.md`: Tier-1 required gates (backend/frontend/openapi-sync/contract validators) +
nightly real-infra + weekly soak + manual stress. `cdd-kit gate` green.

## Production Reality Findings
- Live testing exposed bugs not caught by mocks: the partial-trackin under-count (>100% rates),
  station_order collapsing to 999 (zeroed downstream), amplification KPI never displaying (path
  mismatch), and the forward CSV dumping raw events. All fixed and re-verified against live Oracle.
- The forward "amplification" is frequently <1 (downstream rate ≤ detection rate = attenuation,
  not amplification) — a real domain finding, not a bug.

## Lessons Promoted to Standards
- Product/system rules promoted **inline during implementation** (committed `4332ac84`):
  MSD-09 + MSD-10 in `contracts/business/business-rules.md`; §3.24.1/§3.24.5 in
  `contracts/data/data-shape-contract.md`. Evidence: `agent-log/contract-reviewer.yml`,
  `agent-log/bug-fix-engineer.yml`, commits `f59dd462`/`55f0ba22`/`4332ac84`.
- Operating lesson (parallel CCR session can entangle shared contract files at commit time) saved
  to session memory `feedback_parallel_session_commit_entanglement` rather than CLAUDE.md.

## Follow-up Work
- MSD-11 business rule documenting the backward fan-out dedup invariant (single dimension ≤ cohort
  total) is deferred until the parallel `eap-alarm-coarse-filter` change commits, to avoid a
  `business-rules.md` version-number collision (both target 1.36). The fix itself shipped in
  commit `5e0ea59a` with the `TestBackwardAttributionNoFanout` regression.

## Cold Data Warning
This archive is historical evidence. Current requirements live in `contracts/` and active project
guidance.

# Design: downtime-analysis-page

## Summary

Adds a new `/downtime-analysis` page that mirrors the resource-history Flask + DuckDB-spool + Vue3 architecture. Backend introduces `downtime_analysis_routes.py`, `downtime_analysis_service.py`, `sql/downtime_analysis/*.sql`, and a new `downtime_analysis_cache.py` spool module (independent namespace). The service consumes `DWH.DW_MES_RESOURCESTATUS_SHIFT` rows where `OLDSTATUSNAME IN ('UDT','SDT','EGT')`, merges cross-shift fragments into logical events, joins `DWH.DW_MES_JOB` via a JOBID-primary + RESOURCEID-time-overlap fallback bridge, and exposes summary / big-category / top-reasons / equipment-detail / event-detail views. Frontend is a new feature app at `frontend/src/downtime-analysis/` registered through portal-shell's lazy native module loader, scoped under `.theme-downtime-analysis`. Reuses resource-history's filter cache (workcenter / family / package-group / resource), `query_spool_store`, and `ProcessLevelCache` infrastructure. No existing behavior changes.

## Affected Components

| component | file path(s) | nature of change |
|---|---|---|
| backend route | `src/mes_dashboard/routes/downtime_analysis_routes.py` | NEW Blueprint |
| backend service | `src/mes_dashboard/services/downtime_analysis_service.py` | NEW |
| spool/cache | `src/mes_dashboard/services/downtime_analysis_cache.py` | NEW (namespace `downtime_analysis_*`) |
| SQL pack | `src/mes_dashboard/sql/downtime_analysis/{base_events,job_bridge,big_category,top_reasons,equipment_detail,event_detail}.sql` | NEW |
| app factory | `src/mes_dashboard/app.py` | additive blueprint registration |
| nav registry | `data/page_status.json` | add `/downtime-analysis` page entry |
| modernization | `docs/migration/full-modernization-architecture-blueprint/{asset_readiness_manifest,route_scope_matrix,route_contracts}.json` | additive entries |
| frontend app | `frontend/src/downtime-analysis/` | NEW Vue3 feature app |
| portal-shell | `frontend/src/portal-shell/{nativeModuleRegistry,routeContracts,router,sidebarState}.js` | additive route + lazy-load entry |
| vite entry | `frontend/index.html`, `frontend/vite.config.ts` | additive entry |
| tailwind base | `frontend/src/styles/tailwind.css` | n/a (theme rules live in feature CSS) |
| contracts | `contracts/{api/api-contract,api/api-inventory,business/business-rules,data/data-shape-contract,css/css-inventory,CHANGELOG}.md` | additive |
| hardening test | `tests/test_modernization_policy_hardening.py` | extend with downtime-analysis assertion |

## Decision 1: Cross-shift event merge key

**Problem.** `DW_MES_RESOURCESTATUS_SHIFT` cuts every status event at shift boundaries (07:30 / 19:30 Asia/Taipei), so a single physical downtime spans N rows where N = number of shift boundaries crossed + 1. Each fragment carries identical `OLDSTATUSNAME` / `OLDREASONNAME` but distinct `LASTSTATUSCHANGEDATE` / `OLDLASTSTATUSCHANGEDATE`. The same incident class as `prod-history-detail-partial-merge`: a too-narrow key over-merges and silently loses rows; a too-wide key fails to merge real fragments.

**Formal key.** Logical-event identity = `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME, run_seed_start)` where `run_seed_start` is the earliest `OLDLASTSTATUSCHANGEDATE` in the contiguous run. The run is built by sorting fragments for a `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)` triple by `OLDLASTSTATUSCHANGEDATE` ASC, then walking the list and starting a new run whenever the gap between the prior fragment's `LASTSTATUSCHANGEDATE` and the current fragment's `OLDLASTSTATUSCHANGEDATE` exceeds 60 seconds. Aggregations: `hours = SUM(HOURS)`, `event_start = MIN(OLDLASTSTATUSCHANGEDATE)`, `event_end = MAX(LASTSTATUSCHANGEDATE)`, `fragment_count = COUNT(*)`.

**Contiguity rule.** 60-second tolerance accommodates clock skew between MES insertion of consecutive shift-boundary rows. Any gap > 60s indicates a real state transition (operator brought equipment up then down again on the same reason) and must remain a distinct event.

**Fixture example.** Resource `R-001`, status `UDT`, reason `EE Repair`, real downtime 2026-05-27 18:00 → 2026-05-28 08:00 (14h, spans two shift boundaries). SHIFT table rows: (a) 18:00→19:30 = 1.5h, (b) 19:30→07:30 = 12h, (c) 07:30→08:00 = 0.5h. After merge: 1 event, `event_start=18:00`, `event_end=08:00`, `hours=14`, `fragment_count=3`. Test asserts the post-merge row count is exactly 1 and total hours is 14. Without contiguity check, a second `UDT/EE Repair` event at 09:00 on the same resource would silently fold into the first.

**Mitigations.** Pin the key in `business-rules.md` as DA-02. Unit test fixture must include (a) a 3-fragment cross-shift event, (b) two distinct same-reason events on the same day separated by > 60s gap, (c) overlapping events on different resources. Mirror the `tests/test_production_history_sql_runtime.py::test_partial_merge_same_trackin_time_different_trackin_qty` pattern.

## Decision 2: JOBID bridge algorithm

**Path A (direct).** When `SHIFT.JOBID IS NOT NULL`, join `JOB ON JOB.JOBID = SHIFT.JOBID`. `match_source = 'jobid'`.

**Path B (overlap fallback).** When `SHIFT.JOBID IS NULL`, candidate JOBs satisfy `JOB.RESOURCEID = SHIFT.HISTORYID AND SHIFT.event_start < JOB.COMPLETEDATE AND SHIFT.event_end > JOB.CREATEDATE` (using the merged event window from Decision 1, not the raw fragment window). `match_source = 'overlap'`.

**Tiebreak (multiple overlap candidates).** Choose the JOB with the largest temporal overlap with the merged event window: `LEAST(JOB.COMPLETEDATE, event_end) - GREATEST(JOB.CREATEDATE, event_start)`. Ties broken by `JOB.CREATEDATE` ASC (earlier wins), then `JOB.JOBID` ASC for determinism. Emit `match_ambiguous = true` when a non-winning candidate's overlap is ≥ 80% of the winner's; UI shows a small icon and tooltip listing alternates.

**No-match contract.** Row is still emitted. JOB-derived fields (`symptom`, `cause_detail`, `repair_action`, `handler`, `wait_hours`, `repair_hours`) are `null`. Frontend formatter renders `null` as `—` (em dash). `match_source = 'none'`. AC-5 explicitly accepts this. Document in DA-05.

**Match source enum.** `'jobid' | 'overlap' | 'none'`. Always present (non-nullable string). Each detail-row response includes this field so the UI can render a badge per row and the analyst can audit Path-A vs Path-B coverage.

**IT backfill plan.** When IT restores `SHIFT.JOBID` population for the 2025-09..2026-now backlog, all cached spools will silently still serve Path-B matches even though Path-A is now available. Invalidation uses a `bridge_version` integer in `src/mes_dashboard/config/constants.py` (`DOWNTIME_BRIDGE_VERSION`, default `1`). The spool cache key includes this constant; bumping it (PR + redeploy) invalidates all `downtime_analysis_*` spool entries without touching `resource_dataset_*`. Operational runbook: confirm IT backfill complete → bump `DOWNTIME_BRIDGE_VERSION` → deploy → optional `rm tmp/query_spool/downtime_analysis/*.parquet` to reclaim disk immediately (otherwise stale parquets expire at TTL).

## Decision 3: Spool / cache namespace

**Chosen: Option A — new `downtime_analysis_*` namespace.** Two independent Redis namespaces (`downtime_analysis_dataset`, `downtime_analysis_events`) plus a dedicated spool directory `tmp/query_spool/downtime_analysis/`. Rationale: (1) IT JOBID backfill must purge downtime-analysis spool without affecting resource-history's 24h historical-TTL spools; (2) downtime-analysis aggregates `OLDREASONNAME` and `JOB.*` columns that resource_dataset does not carry, so column schemas would diverge and a shared namespace would require a strictly-additive schema discipline across two services that change at different cadences; (3) TTL policy differs — downtime events become immutable once `JOB.COMPLETEDATE` passes, whereas `resource_dataset` keys on `(start_date, end_date, filters)` only.

See `docs/adr/0002-downtime-analysis-spool-namespace.md`.

## Navigation placement

`drawer_id = "drawer-2"` (歷史報表). Co-locates with `/resource-history` and `/hold-history` which share the "look back at past performance" mental model. Page entry in `data/page_status.json` with `order: 6` (after resource-history at order 5). Also add to `asset_readiness_manifest.json`, `route_scope_matrix.json`, and `route_contracts.json` — omission of any of the three crashes gunicorn or leaks an orphan sidebar entry (see CLAUDE.md modernization-policy notes).

## Big-category taxonomy (DA-04 source of truth)

Authoritative mapping; business-rules.md DA-04 references this table by path. Strip `OLDREASONNAME` trailing CHAR spaces before lookup. Unknown reasons map to `其他/未分類`.

| category | OLDREASONNAME values |
|---|---|
| 維修 | `EE Repair`, `EAP Minor stoppage` |
| 保養 | `EE_PM`, `MF_PM`, `PD_PM` |
| 換型換線 | `Change Type`, `Change Package`, `Re Layout`, `Change Marking Code`, `Change Model` |
| 換刀清模 | `Change Tool/Consumables`, `Clean Mold` |
| 檢查 | `Prod_QC_Inspection`, `Prod_PD_inspection`, `TMTT_*` (prefix match) |
| 待料待指示 | `Wait For Instructions`, `No Operator`, `No Raw Material` |
| 工程 | every event where `OLDSTATUSNAME = 'EGT'` regardless of reason |
| 其他/未分類 | residual; includes `*_NULL`, blanks, and any unmapped reason |

Mapping lives in `src/mes_dashboard/services/downtime_analysis_service.py::_BIG_CATEGORY_MAP` (frozendict) plus a `_match_prefix_categories` list for `TMTT_*`. Unit-tested membership per category and explicit fallback-to-`其他/未分類` assertion.

## Rejected alternatives

- **Reject Decision 1 alt: 4-tuple key `(HISTORYID, OLDSTATUSNAME, OLDLASTSTATUSCHANGEDATE)`.** Drops `OLDREASONNAME`; would merge `UDT/EE Repair` with a subsequent `UDT/EAP Minor stoppage` sharing a start timestamp.
- **Reject Decision 1 alt: window function `LAG`-based session id without 60s contiguity check.** Cannot distinguish "still down, crossed shift" from "came up then went down again on same reason" — would over-merge.
- **Reject Decision 2 alt: drop rows where no JOB matches.** Violates AC-5; user explicitly wants to see un-bridged UDT events to chase the IT-side data gap.
- **Reject Decision 2 alt: take the most-recent overlapping JOB by `CREATEDATE DESC`.** Picks a job that started near event end, which is the wrong incident when an equipment had two repair tickets opened during one long downtime.
- **Reject Decision 3 alt: extend `resource_dataset_*` namespace.** Bumping `DOWNTIME_BRIDGE_VERSION` would invalidate resource-history's 24h historical spools — a costly Oracle re-warm — for an unrelated bridge change. Couples two services with different release cadences.

## Migration / Rollback

Initial deploy: no parquet cleanup required (new namespace, new directory `tmp/query_spool/downtime_analysis/` created on first write). Additive blueprint, additive page_status entry, additive modernization JSON entries, additive contract entries — no existing route, response shape, or cache key changes. Rollback = revert PR + delete `tmp/query_spool/downtime_analysis/`.

Post-deploy IT JOBID backfill (when IT confirms): bump `DOWNTIME_BRIDGE_VERSION` integer constant, deploy, optionally `rm tmp/query_spool/downtime_analysis/*.parquet` to free disk before TTL expiry. This is the only documented parquet-purge path; document explicitly in `ci-gates.md §Rollback Policy` per the prod-history-detail-raw-rows precedent. No DDL.

Backward compatibility: all new endpoints under `/api/downtime-analysis/*`; no existing endpoint signatures change. Frontend bundle is additive; no existing feature app's CSS is touched (theme scope `.theme-downtime-analysis` enforced by `npm run css:check` Rule 6).

## Open Risks

- **JOBID coverage gap (~50% UDT, ~14% SDT) is product-visible.** AC-5 accepts this; QA report documents it as approved-with-risk. If IT cannot backfill, the page ships with a persistent banner noting un-bridged event ratio.
- **Tiebreak ambiguity in Path B.** The 80% threshold for `match_ambiguous` is judgmental; revisit after first month of production data.
- **`TMTT_*` prefix matching** depends on Oracle returning reasons without trailing CHAR padding interfering with `startswith`. Service must `strip()` before prefix check (resource-status-package-group precedent).
- **Cross-shift merge correctness under DST or timezone changes.** Taiwan does not observe DST so low risk; fixture should still include a shift boundary that crosses midnight UTC to validate the midnight-UTC DATE handling.

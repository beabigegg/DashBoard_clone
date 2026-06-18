---
change-id: eap-alarm-analysis
schema-version: 0.1.0
last-changed: 2026-06-18
---

# Design: eap-alarm-analysis

## Summary

EAP ALARM Analysis adds a new top-level "EAP" navigation category backed by an additive RQ-async + DuckDB spool-read pipeline (the canonical reject-history/resource-history pattern). A coarse filter (date range + EQP-type multi-select) triggers an RQ job on a dedicated `eap-alarm` queue; the worker runs one Oracle query that JOINs `DWH.EAP_EVENT` to its EAV sidecar `DWH.EAP_EVENT_DETAIL`, decodes AlarmCategory codes, and writes a 10-column parquet into the new `eap_alarm` spool namespace (`tmp/query_spool/eap_alarm/`). The Oracle query MUST be bounded by a `LAST_UPDATE_TIME BETWEEN` predicate (EA-03) to stay on the index and avoid a full-table scan over a ~385K-rows/day table. Once the spool exists, every fine filter (AlarmText fuzzy multi-select, decoded AlarmCategory multi-select, Equipment ID multi-select) and every view (summary cards, Pareto, stacked trend, expandable detail) is computed DuckDB-only — no Oracle re-query (EA-02/EA-04). The coarse/fine boundary is the core architectural decision: Oracle is the slow once-per-coarse-key path; DuckDB is the fast (<100ms) per-interaction path.

## Affected Components

| component | file path(s) | nature of change |
|---|---|---|
| EAP routes | `src/mes_dashboard/routes/eap_alarm_routes.py` (new) | 7 endpoints: spool trigger, spool status, filter-options, summary, pareto, trend, detail |
| EAP service | `src/mes_dashboard/services/eap_alarm_service.py` (new) | spool-key hashing (EA-01), LAST_UPDATE_TIME-guarded SQL builder (EA-03), EQP-type allowlist (EA-07), DuckDB view compute for all 5 derived shapes |
| EAP cache/spool meta | `src/mes_dashboard/services/eap_alarm_cache.py` (new) | `_SCHEMA_VERSION` (EA-06), TTL, parquet path + spool metadata, AlarmCategory decode map (EA-05) |
| EAP worker | `src/mes_dashboard/workers/eap_alarm_worker.py` (new) | RQ worker fn: Oracle EVENT⋈DETAIL JOIN, AlarmCategory decode, parquet write; `register_job_type` at import |
| Spool namespace gate | `src/mes_dashboard/routes/spool_routes.py` (modify) | add `eap_alarm` to `_ALLOWED_NAMESPACES` + parametrized test in same PR |
| App factory | `src/mes_dashboard/app.py` (modify) | register EAP Blueprint; wire `eap-alarm` worker queue/env |
| Navigation shell | `frontend/src/portal-shell/` (modify) | new "EAP" top-level category + guard/route entry |
| EAP frontend app | `frontend/src/eap-alarm/` (new) | Vue SPA: coarse filter form, fine-filter composable (`_lastCommitted` re-sync), Pareto/trend/detail under `.theme-eap-alarm` |
| Deploy unit | `deploy/mes-dashboard-eap-alarm-worker.service` (new) | systemd unit mirroring reject-worker (conda-run `rq worker`, MemoryHigh/Max, ReadWritePaths tmp/logs) |
| Modernization manifests | `docs/migration/page_status.json`, `asset_readiness_manifest.json`, `route_scope_matrix.json` (modify) | register new page in same PR (modernization policy) |
| Env contract | `contracts/env/env-contract.md` (modify) | new `EAP_WORKER_QUEUE` + spool namespace/concurrency vars |

## Key Decisions

- **Coarse spool key, DuckDB-only fine filters (EA-01/EA-02)**: spool key = `eap_alarm:{date_from}:{date_to}:{sha256(sorted(eqp_types))[:8]}`; AlarmText/category/eqp_id are never in the key. Rationale: at ~385K rows/day an Oracle re-query per fine-filter change would blow the latency budget, while DuckDB recompute over a <20MB parquet is <100ms. Rejected alternative: fine-grain key (each filter combo = new Oracle job) — explodes cache-entry count and re-introduces per-toggle Oracle latency, exactly the failure ADR-0005 corrected for resource-history.
- **JOIN EAP_EVENT_DETAIL at spool-load time (EA-04)**: the EAV DETAIL table (indexed by `SEQ_ID`) is JOINed during the single worker query; non-column params are folded into a `DETAIL_PARAMS` JSON string so row expansion reads the spool. Rejected alternative: lazy-load DETAIL on row expand — an N+1 Oracle query per expanded row at interactive time.
- **AlarmCategory decode at spool-load time (EA-05)**: integer codes are decoded to labels during parquet write (unknown code → "未知"), so `ALARM_CATEGORY` ships as a column and the frontend needs no lookup table. Rejected alternative: decode in Vue — duplicates the table and risks drift from business-rules.md.
- **Always-async, no sync fallback**: unlike hold-history/resource-history (date-range threshold + sync path), EAP ALARM is always RQ-async because an unchunked Oracle scan on this table exceeds timeout in any realistic window. Rejected alternative: sync path for 1-day queries — adds a second code path for no user benefit (1-day spool returns in <30s via RQ).
- **New ADR-0008 written**: the JOIN-with-DETAIL data shape + coarse/fine split is a non-obvious, reversal-sensitive boundary decision; recorded in `docs/adr/0008-eap-alarm-coarse-spool-detail-join.md` consistent with ADR-0001/0005.

## Migration / Rollback

Additive only — new Blueprint, new worker queue, new parquet namespace, new frontend app. Zero change to existing routes, services, or spool namespaces; existing parquet schemas are untouched.

Forward deploy: register `eap_alarm` in `_ALLOWED_NAMESPACES` (+ test), install `mes-dashboard-eap-alarm-worker.service`, register Blueprint in `app.py`, ship frontend + modernization manifests in the same PR.

Rollback: (1) `systemctl stop mes-dashboard-eap-alarm-worker.service`; (2) `rm -f tmp/query_spool/eap_alarm/*.parquet`; (3) remove Blueprint registration from `app.py`; (4) revert portal-shell nav change; (5) revert `docs/migration/` manifests (and manually delete the `page_status.json` page entry — it is never auto-removed on code deletion).

Spool schema change (any column add/remove/rename, EA-06): bump `_SCHEMA_VERSION` in `eap_alarm_cache.py` in the same commit AND add `rm -f tmp/query_spool/eap_alarm/*.parquet` to the rollback runbook — Redis pointers expire by TTL but disk parquet does not self-clean.

## Open Risks

- **Worker fork-safety**: confirm the new worker honors the gunicorn preload/fork discipline (ADR-0004); Oracle connections must be established post-fork in the RQ worker, not at import.
- **DETAIL_PARAMS cardinality**: if some EAP equipment emit many DETAIL params, the JSON string could bloat parquet beyond the <20MB/7-day target; size must be checked during stress evidence capture.
- **AlarmText fuzzy multi-select cost**: DuckDB `ILIKE`/contains over large distinct AlarmText sets is the most expensive fine-filter; verify it stays within the <100ms recompute budget at 385K rows.
- **`_ALLOWED_NAMESPACES` drift**: namespace registration and its parametrized test must land in the same PR as the first spool write, or spool reads 403 in CI.
- **code-map staleness**: new files (`eap_alarm_*`) will not appear in `.cdd/code-map.yml` until `cdd-kit code-map` is re-run post-implementation; downstream agents should refresh before grounding on it.

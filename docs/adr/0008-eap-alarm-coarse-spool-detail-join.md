# ADR 0008: EAP ALARM coarse spool key with DETAIL JOIN at load time

## Status
proposed

## Context
The EAP ALARM Analysis page queries `DWH.EAP_EVENT` (~385K rows/day, indexed on `LAST_UPDATE_TIME` and `EQUIPMENT_ID`) joined to its EAV sidecar `DWH.EAP_EVENT_DETAIL` (indexed on `SEQ_ID`). Users interact with two filter tiers: a mandatory coarse filter (date range + EQP-type multi-select) and three optional fine filters (AlarmText fuzzy multi-select, decoded AlarmCategory multi-select, Equipment ID multi-select). The page also expands detail rows to show ALARM DETAIL parameters. Two design questions are reversal-sensitive: (1) what goes into the spool cache key, and (2) when the EAV DETAIL data is materialized. This mirrors the failure mode corrected by ADR-0001 (material-consumption) and ADR-0005 (resource-history), where filter/granularity dimensions leaked into the spool key and re-introduced per-interaction Oracle queries.

## Decision
The spool key is coarse-only: `eap_alarm:{date_from}:{date_to}:{sha256(sorted(eqp_types))[:8]}` plus the `_SCHEMA_VERSION` (EA-01/EA-06). Fine filters and all views (summary, Pareto, stacked trend, paginated detail) are computed DuckDB-only over the parquet — never a new Oracle query (EA-02/EA-04). The Oracle worker query MUST carry a `LAST_UPDATE_TIME BETWEEN :from AND :to` predicate to stay index-driven (EA-03); unbounded queries are rejected with 400. `DWH.EAP_EVENT_DETAIL` is JOINed at spool-load time: known params become columns (ALARM_TEXT, ALARM_CATEGORY_CODE) and the remainder is folded into a `DETAIL_PARAMS` JSON column so row expansion reads the spool, not Oracle. AlarmCategory codes are decoded to labels (unknown → "未知") during parquet write. EAP ALARM is always RQ-async with no sync fallback.

## Consequences
- Fine-filter changes and view switches on a warm coarse key cost zero Oracle round-trips; detail expansion never triggers an N+1 Oracle query.
- Future engineers MUST NOT add AlarmText, AlarmCategory, or Equipment ID to the spool key — doing so multiplies cache entries and silently re-introduces per-toggle Oracle latency (the ADR-0005 regression).
- Future engineers MUST NOT switch DETAIL to lazy per-row loading — it re-introduces the N+1 problem this decision exists to prevent.
- Any parquet column add/remove/rename requires bumping `_SCHEMA_VERSION` and `rm -f tmp/query_spool/eap_alarm/*.parquet` on both deploy and rollback (disk parquet does not self-clean; Redis pointers expire by TTL).
- The DETAIL JOIN widens each spooled row; `DETAIL_PARAMS` JSON size must be monitored to keep the ~7-day parquet under the <20MB target.

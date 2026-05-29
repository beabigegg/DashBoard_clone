# ADR-0002: downtime-analysis uses an independent spool/cache namespace

**Status**: accepted
**Change**: downtime-analysis-page

## Context

The new `/downtime-analysis` page reads from `DWH.DW_MES_RESOURCESTATUS_SHIFT` and `DWH.DW_MES_JOB`, the same source tables that resource-history (`resource_dataset_*` namespace) already spools. There was a temptation to extend the existing namespace and share cached fragments. Two forces push back: (1) IT will eventually backfill `SHIFT.JOBID` for 2025-09..2026-now, requiring a forced invalidation of downtime-analysis spools that must not also evict resource-history's 24h historical-TTL spools; (2) the two services aggregate different columns (`OLDREASONNAME`, `JOB.*` for downtime vs. `PRD/SBY/UDT/SDT/EGT/NST` hour buckets for resource-history) and therefore want different parquet schemas.

## Decision

Create a new namespace `downtime_analysis_dataset` (event-level spool) and `downtime_analysis_events` (event-detail spool) under `tmp/query_spool/downtime_analysis/`. The spool cache key includes a `DOWNTIME_BRIDGE_VERSION` integer constant in `src/mes_dashboard/config/constants.py`; bumping that integer is the documented invalidation lever for the JOBID-backfill scenario.

## Consequences

- Bridge-logic changes (e.g., JOBID-backfill cutover) invalidate only downtime-analysis spools, not the 24h historical resource-history cache.
- Future engineers must not merge downtime-analysis SQL output into `resource_dataset_*` to "save a query" — the two namespaces intentionally diverge.
- One extra spool directory to monitor for disk usage; runbook lists `tmp/query_spool/downtime_analysis/` as an additional cleanup target.
- Schema evolution for downtime-analysis is decoupled from resource-history's schema-breaking-change discipline; each can release independently.

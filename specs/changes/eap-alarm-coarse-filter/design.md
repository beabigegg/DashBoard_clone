# Design: eap-alarm-coarse-filter

## Summary
Expands the EAP-alarm coarse spool filter from a fixed `(date + machines)` pair to
`(date + machines? + lot_ids? + product_dims?)`, where at least one of the three
non-date axes is required. All three new axes push their predicates down to the
Oracle `DWH.EAP_EVENT` worker query — `lot_ids` as a direct `LOT_ID IN (...)`, and
`product_dims` (pj_types / product_lines / pj_bops) as one `EXISTS` semi-join per
dim against `DWH.DW_MES_CONTAINER` on the indexed `CONTAINERNAME ↔ LOT_ID` join.
Every new axis becomes part of the spool-key canonical repr so a warm parquet is
only reused for an identical full filter set, and `_SCHEMA_VERSION` advances 2→3 so
all pre-existing v2 parquet auto-invalidates on first key-miss. This directly extends
ADR 0008 (coarse-only spool key, Oracle-index-driven worker query) without reversing
any of its invariants: fine filters and views remain DuckDB-only over the parquet.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| spool-key builder | `src/mes_dashboard/services/eap_alarm_cache.py` | extend `make_eap_alarm_spool_key()` to hash all 5 dims; bump `_SCHEMA_VERSION` 2→3 |
| param validation | `src/mes_dashboard/services/eap_alarm_service.py` | `validate_eap_alarm_params()` → at-least-one-of-three rule; eqp_types enum only when supplied |
| Oracle worker query | `src/mes_dashboard/workers/eap_alarm_worker.py` | add `LOT_ID IN (...)` binds + per-dim `EXISTS` clauses (AND-semantics) under existing `LAST_UPDATE_TIME` predicate |
| route layer | `src/mes_dashboard/routes/eap_alarm_routes.py` | parse new body fields; machines optional; new `GET /api/eap-alarm/product-filter-options` |
| product-dim options | `src/mes_dashboard/services/container_filter_cache.py` | reuse existing `get_filter_options()` (read-only consumer; no new query path) |
| frontend filter | `frontend/src/eap-alarm/` | LOT_ID textarea + TYPE/PACKAGE/BOP MultiSelects; `buildCoarseParams`; at-least-one error copy + i18n |
| contracts | data-shape §3.17, business-rules EA-01/08/09/10, api-contract + openapi | request fields, spool-key dims, EXISTS mapping, options payload (already drafted) |

## Key Decisions

- **D-1 Spool-key hash covers all 5 dims**: the canonical repr is
  `sorted(eqp_types)+sorted(lot_ids)+sorted(pj_types)+sorted(product_lines)+sorted(pj_bops)`,
  each list serialized with a fixed separator and an empty list rendered as the empty
  string so distinct dims can never collide into the same 8-char digest. One coarse
  key per full filter set preserves ADR-0008's "warm key → zero Oracle round-trip"
  guarantee. → Rejected: a separate hash per axis — a single spool result must map to
  one key regardless of which axes produced it, and per-axis hashes fragment that.

- **D-2 product-filter-options reuses container_filter_cache**: the new
  `GET /api/eap-alarm/product-filter-options` wraps the already-warm
  `container_filter_cache.get_filter_options()` (24h Redis TTL, shared with
  production-history). No request-time Oracle. Cold cache returns empty arrays, never
  500 — mirroring the fail-open posture of the existing filter-options surfaces.
  → Rejected: a dedicated endpoint querying Oracle directly — duplicates a dataset the
  cache already serves and adds a redundant Oracle path with its own warmup cost.

- **D-3 EXISTS semi-join, not JOIN**: each product dim becomes a separate
  `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND
  NVL(TRIM(c.<col>),'(NA)') IN (...))`. EXISTS is a semi-join: a LOT_ID matching many
  container rows still yields one EAP_EVENT row, so no row explosion / no double-count.
  Multiple dims AND together as independent EXISTS clauses. → Rejected: `LEFT JOIN +
  DISTINCT` — DISTINCT forces a sort step and the contract (EA-10, §3.17) already
  asserts no row explosion, which EXISTS satisfies without the sort.

- **D-4 At-least-one-of-three validated at the route, pre-key**: before computing the
  spool key, the route rejects requests where all of {eqp_types (after enum check),
  lot_ids (after whitespace-strip), product_dims} are absent/empty → 400
  `VALIDATION_ERROR` (EA-08). eqp_types enum validation still runs whenever eqp_types is
  supplied; it is no longer an unconditional requirement. Validating pre-key prevents an
  empty-filter request from minting an unbounded spool key. lot_ids are whitespace-
  stripped, deduped, and capped at 200 (EA-09); overflow is a 400, not a silent trim.

- **D-5 `_SCHEMA_VERSION` 2→3 in the same commit**: the bump rides in the same commit
  as the key/column change. Old v2 parquet is auto-invalidated by key-miss (the version
  is part of the key) — no manual purge needed on deploy. This honours ADR-0008's rule
  that any spool schema change bumps the version. → Rejected: a manual deploy-time `rm`
  as the primary invalidation — version-in-key invalidation is self-healing and safe
  under concurrent multi-worker deploys; the `rm` remains only as the rollback lever.

## Migration / Rollback
No data migration or backfill. On deploy, the `_SCHEMA_VERSION = 3` bump makes every
new spool key miss all v2 parquet, which then ages out by TTL; new queries write v3
parquet. Request compatibility is backward-additive: existing clients that always send
`machines` keep working unchanged (machines simply becomes one of three accepted axes).
Rollback is reverting the commit (restoring `_SCHEMA_VERSION = 2`) plus
`rm -f tmp/query_spool/eap_alarm/*.parquet` to clear any v3 files orphaned by the
version downgrade — disk parquet does not self-clean on rollback (ADR-0008 consequence;
Redis pointers expire by TTL). The reused `container_filter_cache` path has no rollback
footprint of its own.

## Open Risks
- ADR-0008 is `proposed`, not `accepted`, and predates these axes. Its decision text
  still says "spool key is coarse-only: `sha256(sorted(eqp_types))`". This change keeps
  the coarse-only principle but widens the key to 5 dims and adds the EXISTS semi-join —
  a reversal-sensitive extension. ADR-0008 should be amended (Decision + Consequences:
  enumerate all 5 key dims; document EXISTS-not-JOIN as a standing rule future engineers
  must not silently flip to JOIN) so the spool-key surface stays single-source. Flagged
  for the owner to amend rather than written here, since this design extends an existing
  ADR rather than opening a new boundary.
- `DW_MES_CONTAINER.CONTAINERNAME` is Oracle CHAR — trailing-space padded. The contract
  specifies `TRIM` on both sides; key-build and Oracle bind must strip consistently or a
  warm key built from a stripped lot_id will mismatch a padded container value. Covered
  by EA-09 and the data-boundary test, but it is the most likely correctness foot-gun.
- product_dims options depend on `container_filter_cache` being warm. On a cold cache the
  FilterBar MultiSelects render empty, which can read as "no products exist" rather than
  "options not loaded yet". UI copy/empty-state should distinguish the two (ui-ux-reviewer).

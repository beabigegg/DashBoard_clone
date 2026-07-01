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
| param validation | `src/mes_dashboard/services/eap_alarm_service.py` | `validate_eap_alarm_params()` → at-least-one-of-three rule; **(D-7)** drop `_VALID_EQP_TYPES` closed-enum — accept any non-empty stripped string (same shape as `lot_ids`) |
| Oracle worker query | `src/mes_dashboard/workers/eap_alarm_worker.py` | add `LOT_ID IN (...)` binds + per-dim `EXISTS` clauses (AND-semantics) under existing `LAST_UPDATE_TIME` predicate; **(D-6)** `_build_equipment_filter([])` returns `1=1` no-op instead of empty `IN ()` |
| coarse filter bar | `frontend/src/eap-alarm/FilterBar.vue` | adds cascade/product controls **and (D-8)** submit-time expansion: family-selected-but-no-machine expands `machines` to all `machineOptions` names of the filtered family before emit |
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

--- (post-ship corrections — bug + data-model fix found before archive) ---

- **D-6 Empty `eqp_types` yields a `1=1` no-op predicate, not empty `IN ()`**:
  `_build_equipment_filter` is spliced *unconditionally* as `AND {equipment_filter}` into
  both `_EAP_EVENT_SQL_TEMPLATE` and `_DETAIL_SQL_TEMPLATE` (worker L59/L71), unlike
  `_build_lot_ids_filter`/`_build_product_dims_exists` which return `""` and are only
  appended when non-empty. With an empty list it emitted `AND e.EQUIPMENT_ID IN ()` →
  ORA-00936 (confirmed in production for the EA-08-legal combo `eqp_types=[]` +
  `product_lines=['SOT-223']`). Fix: the empty branch returns the always-true predicate
  `1=1` so the unconditional splice stays valid and the row set is left unrestricted by
  equipment. → Rejected: making the splice conditional (mirror lot/product's `""`-then-
  append pattern) — a larger edit to two SQL templates plus the params/splice site for a
  single-branch defect; `1=1` is the minimal, self-documenting fix and keeps the template
  shape (`AND {equipment_filter}`) stable. → Also rejected: raising a 400 when eqp_types
  is empty — EA-08 explicitly permits eqp_types to be the empty axis, so rejecting it
  would contradict the at-least-one-of-three contract.

- **D-7 Drop the `_VALID_EQP_TYPES` closed enum (EA-07); accept any non-empty stripped
  string**: the 10-code enum (`GDBA…GPTA`) was dead the day it shipped. `_build_equipment_filter`
  matches `e.EQUIPMENT_ID IN (...)` by *exact* string, but real `DWH.EAP_EVENT.EQUIPMENT_ID`
  values are `<4-char-prefix>-<instance>` (e.g. `GWBK-0241`) — a bare `GWBK` matches zero
  rows even when it passes EA-07. Equipment identifiers are plant-wide and churn over time,
  so a hardcoded enum can neither match reality nor stay current. Replacement rule: validate
  `eqp_types` exactly like `lot_ids` — reject non-string/blank entries, keep every non-empty
  whitespace-stripped value; no membership check. `_build_equipment_filter`'s exact-match
  logic is confirmed correct against the live sample and is unchanged apart from D-6.
  → Rejected: fixing the enum to store full machine IDs — the valid set is thousands of
  live-changing rows sourced from `DW_MES_RESOURCE.RESOURCENAME`; enumerating it in code is
  unmaintainable and would drift on every tool add/retire. → Rejected: switching the worker
  to prefix/`LIKE 'GWBK-%'` matching so bare 4-char codes work — that silently changes filter
  semantics (prefix vs exact machine), and the frontend already selects full machine names
  from the plant-wide cascade, so exact match is the correct and existing contract.

- **D-8 Family-without-machine expands client-side to the full filtered machine list**:
  the `型號`/`機台` cascade in `FilterBar.vue` is sourced from the plant-wide resource model
  (`/api/resource/status/options` → `resourceOptions.resources` with `family`/`name`), never
  from the removed enum. `cascade.families` is local-only and is never sent to the backend;
  the family label (`GWBK`) is not a valid `EQUIPMENT_ID` and must not be submitted. Semantics,
  all AND-combined: (a) family + specific machines → send exactly those machine names (existing
  exact match, unchanged); (b) family + no machine → `handleSubmit` expands `machines` to *all*
  `machineOptions.value` names of the filtered family (client-side, since that pool is already
  loaded) so "型號 = GWBK, 機台 = 全部" becomes an explicit `EQUIPMENT_ID IN (<all GWBK-\* names>)`;
  (c) product-dims only, no family/machine → empty `machines`, unrestricted by equipment via
  D-6's `1=1`, product bridge (EA-09/EA-10) unchanged. → Rejected: expanding the family→machine
  fan-out in the backend/worker — that would require the worker to re-query the resource model
  (a new Oracle/cache dependency on the async path) to resolve a family the client already holds
  in memory; keeping expansion at submit time reuses loaded data and needs zero new backend
  dependency. → Rejected: sending the family label and prefix-matching in SQL — same
  semantics-drift objection as D-7; the contract stays exact-match on full machine names.

## Migration / Rollback
No data migration or backfill. On deploy, the `_SCHEMA_VERSION = 3` bump makes every
new spool key miss all v2 parquet, which then ages out by TTL; new queries write v3
parquet. Request compatibility is backward-additive: existing clients that always send
`machines` keep working unchanged (machines simply becomes one of three accepted axes).
Rollback is reverting the commit (restoring `_SCHEMA_VERSION = 2`) plus
`rm -f tmp/query_spool/eap_alarm/*.parquet` to clear any v3 files orphaned by the
version downgrade — disk parquet does not self-clean on rollback (ADR-0008 consequence;
Redis pointers expire by TTL). The reused `container_filter_cache` path has no rollback
footprint of its own. The post-ship D-6/D-7/D-8 corrections add no schema or spool-key
*dimension* change (EA-07 only loosens which `eqp_types` values are accepted into the
existing dim; the key repr is unchanged), so they carry no additional migration or spool
cleanup — reverting the D-6/D-7/D-8 commit fully restores prior behaviour on its own.

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
- **(D-7 consequence) Field-name/semantics drift**: the request field is still named
  `eqp_types` but after D-7 it holds arbitrary full equipment-ID strings (`GWBK-0241`), not
  4-char *type* codes. Recommendation: keep the field name `eqp_types` — renaming is a
  breaking API/contract change (route body, openapi, spool-key repr in `make_eap_alarm_spool_key`,
  frontend, tests) for zero functional gain, and additive/backward-compat discipline favours
  a stable name. The misnomer should be documented in EA-07's contract text and a one-line
  code comment at `_VALID_EQP_TYPES`'s removal site rather than fixed by a rename. Contract
  wording is contract-reviewer's call in the next step.
- **(D-8 boundary) Client-side family expansion can send a large `machines` list**. A family
  with hundreds of tools expands to a correspondingly large `EQUIPMENT_ID IN (...)`; the
  worker already chunks past the 999-bind Oracle limit (`_build_equipment_filter` OR-of-INs
  branch), so this is bounded, but the expanded list also enlarges the spool-key repr and
  therefore the cache-key cardinality — two users selecting the same family both hit the same
  key only if the family's machine roster is identical at submit time. Roster drift between
  submits produces distinct keys (correct but slightly less cache reuse). No action required;
  noted so it is not mistaken for a bug later.
- **(D-6/D-7 test coverage)** Both defects were dead/broken paths that shipped green: the
  empty-`eqp_types` ORA-00936 and the never-matching enum. The regression net must include a
  data-boundary case asserting empty `eqp_types` + product-dims-only produces `1=1` (not
  `IN ()`) and a case asserting a full machine-ID string survives validation — flagged for
  test-strategist, not resolved here.

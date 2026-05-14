---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# Design — First-tier cache filters for Production History

## Decision summary

| id | decision | rationale |
|---|---|---|
| D1 | Cross-filter = cached 4-tuple DISTINCT set + in-memory filter (Option B) | Oracle-free per interaction; payload ≤ 2.4 MB; SOT |
| D2 | Wildcard = single `*` (any position incl. infix); non-`*` chars ≥ 2 total; ≤ 100 patterns/field; SQL-meta rejected | User-chosen looser grammar 2026-05-14 (overrides initial ≥4-char infix rule); matches `material-trace` UX |
| D3 | Cache payload carries `schema_version: 2`; mismatch → drop + rebuild | Silent rollback without `redis-cli DEL` |
| D4 | Reuse `resource_history_duckdb_cache._try_lock` pattern at `tmp/container_filter_cache.loading` | Battle-tested 90 s poll bound |
| D5 | Oracle hardening = 2-char total anchor; infix `'%X%'` allowed (≥ 2 chars); no ROWNUM cap v1 | User-chosen looser grammar 2026-05-14; chunked TRACKINTIMESTAMP window already bounds scope |
| D6 | **Remove** (not hide) MFGORDERNAME/CONTAINERNAME/FIRSTNAME from second-tier | Single source kills dual-state bugs |
| D7 | New `GET /api/production-history/filter-options?selected=<json>` | Separate Oracle-cached vs spool-derived chip endpoints |

---

## D1 — Cross-filter strategy (Option B)

Cardinality: PJ_TYPE O(10), Package O(100), BOP O(500), Function O(1k); co-occurrence tuples
O(5-20k) × ~120 bytes ≈ **≤ 2.4 MB JSON** (5× safety factor still ≤ 12 MB, within Redis
practical limit). In-memory filter is 1-pass scan + 4 set-unions, < 5 ms warm.

Rejected alternatives:
- **Option A (live SQL/keystroke).** DBA load + latency jitter unacceptable for a picker.
- **Option C (4 flat lists + filtered subquery).** Still needs Oracle co-occurrence join to
  narrow BOP by Package — pays Oracle cost without caching benefit. Strictly worse than B.

### Cache layout v2 (`container_filter_cache:data`)

```json
{
  "schema_version": 2,
  "tuples": [["A", "PKG-1", "BOP-1", "FN-1"], ...],
  "indices": {
    "pj_types": ["A", "B", ...],
    "packages": ["PKG-1", ...],
    "bops": ["BOP-1", ...],
    "pj_functions": ["FN-1", ...]
  },
  "updated_at": "2026-05-14T..."
}
```

`indices` is a denormalised convenience for the empty-selection case (AC-1).

---

## D2 — Wildcard grammar

| user input | normalized | bound SQL fragment |
|---|---|---|
| `MA2025` | exact | included in `IN (...)` batch |
| `MA2025*` | prefix | `col LIKE :p ESCAPE '\'` with `:p="MA2025%"` |
| `*2025` | suffix | `col LIKE :p ESCAPE '\'` with `:p="%2025"` |
| `MA*2025` | infix | `col LIKE :p ESCAPE '\'` with `:p="MA%2025"` |
| `*A*`, `*M*` | infix with short anchor (allowed when total non-`*` chars ≥ 2) | `col LIKE :p ESCAPE '\'` with `:p="%A%"` etc. |
| `*`, `M*`, `*X`, `MA**`, `***` | rejected (pure `*`, single-char total, or multi-`*`) | 400 |
| `'`, `;`, `--`, `/*`, `*/`, `\x00`, control chars | rejected | 400 |

Pipeline in `core/request_validation.py::parse_wildcard_tokens(field, raw)`: split on
newline/comma/whitespace → trim → reject on meta-char regex `[\'\;\x00-\x1f]|--|/\*|\*/` → reject
if `*` count ∉ {0,1} → reject if total non-`*` char count < 2 → escape `%`/`_` → translate `*` → `%` →
dedup → cap 100/field. Idempotent (AC-5): `parse(parse(x)) == parse(x)`. SQL emit mirrors
`material_trace_service.py:85-117` (`_add_exact_or_pattern_condition`); lift to shared
`sql/wildcards.py` or duplicate — see U2.

**Note on infix Oracle load**: per user decision 2026-05-14, infix wildcards with short anchor
(e.g., `*A*`) are accepted. This trades Oracle index-friendliness for user flexibility. The
chunked `TRACKINTIMESTAMP` window predicate remains the primary scope cap. Monitor Oracle
latency for infix-heavy queries; revisit ROWNUM cap or per-field opt-out if production load
proves problematic.

---

## D3 — Cache schema versioning

Payload key `schema_version: int`, current value `2` (was implicit `1`). Check in
`container_filter_cache._read_from_redis`: mismatch → log INFO, return None, force Oracle path;
never deserialise as old shape. Writer always emits `2`. Rollback = bump to `3` in a follow-up
to invalidate without `redis-cli DEL`. New convention in this repo — document in ci-gates.md
§Rollback; promote to CLAUDE.md on archive.

---

## D4 — Multi-worker startup lock

Reuse `resource_history_duckdb_cache._try_lock`/`_release_lock` verbatim
(`resource_history_duckdb_cache.py:44-65`): lock at `tmp/container_filter_cache.loading`,
acquire via `os.open(..., O_CREAT|O_EXCL|O_WRONLY)`, losers poll Redis L2 every 5 s × 18
iterations (90 s total), release in `finally`. Stale-sentinel residual risk matches the
resource-history precedent; runbook documents `rm`. mtime-based reaper deferred (U4).

---

## D5 — Oracle LIKE hardening

| pattern shape | accepted? |
|---|---|
| `'X%'` prefix (anchor ≥ 2 chars) | yes — index-rangeable |
| `'%X'` suffix (≥ 2 chars) | yes — bounded by IN-set cap |
| `'%X%'` infix (anchor ≥ 2 chars total) | yes — per user decision 2026-05-14 |
| `'%X%'` with total chars < 2 (e.g., `*A*`) | no |
| pure `'%'` | no |

Safety belts: (1) max 100 patterns/field (D2); (2) ROWNUM cap **not added v1** — the main
query's chunked `TRACKINTIMESTAMP` window predicate is the primary scope cap. (3) Infix
wildcards may bypass Oracle indexes — surface in monitoring; ROWNUM cap reserved for v1.5
if production load shows degradation. Bind path is `:bind` with `LIKE :bind ESCAPE '\'`
everywhere — no string interpolation (matches `material_trace_service.py:114`).

---

## D6 — Second-tier UI

`MFGORDERNAME`, `CONTAINERNAME`, `FIRSTNAME`, `Package`, `BOP` chips → **removed** (not hidden);
they are now first-tier. `WorkCenter 群組` and `Equipment` remain second-tier (still spool-derived).
Conditional hiding rejected: it creates a dual-state bug — user types `MA*` in the first-tier
wildcard textarea while a literal `MA2025X` chip is still selected from a prior query; removing
the chip closes the question.

---

## D7 — API surface

| route | method | purpose | payload |
|---|---|---|---|
| `/api/production-history/filter-options` (new) | GET | Cross-filter cached options | `?selected=<json>` (URL-encoded) |
| `/api/production-history/options` (existing) | POST | Spool chips (WorkCenter / Equipment) | unchanged |
| `/api/production-history` (existing) | POST | Main query | extended with `pj_functions[]`, `mfg_orders[]`, `lot_ids[]` (wildcard), `wafer_lots[]` (wildcard) |

`selected` is JSON: `{"pj_types":[], "packages":[], "bops":[], "pj_functions":[]}`. Unknown
keys ignored; values not in cache silently dropped (fail-open picker).

Response (standard `success_response`):

```json
{
  "status": "ok",
  "data": {"pj_types":[...], "packages":[...], "bops":[...], "pj_functions":[...]},
  "meta": {"updated_at": "...", "schema_version": 2}
}
```

GET chosen because pure-read + idempotent; URL budget ~6 KB at full saturation (4 × 50 × 30
bytes) fits within 8 KB conservative limit.

---

## Rollback plan

- Cache: bump `schema_version` → `3`; next deploy's L2 read mismatches, drops, rebuilds.
- Backend / frontend: additive changes — revert is mechanical (no SQL structure change).
- Lock file: post-rollback runbook step — `rm tmp/container_filter_cache.loading`.

## Open items (deferred)

- U1 (contract-reviewer): `PRODUCTION_HISTORY_WILDCARD_MAX_PATTERNS` — env contract or constant?
- U2 (backend-engineer): lift wildcard SQL emitter to `sql/wildcards.py` or duplicate?
- U3 (dependency-security-reviewer): does the meta-char regex cover Oracle `q'[...]'` and `||`?
- U4 (backend-engineer): mtime-based stale-sentinel reaper for the lock file, or accept
  current resource-history behavior?

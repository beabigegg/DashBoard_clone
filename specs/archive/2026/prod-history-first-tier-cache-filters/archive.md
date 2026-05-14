# Archive — prod-history-first-tier-cache-filters

## Change Summary

Tier 1 (high-risk) change promoting 7 Production History filters to
first-tier status with a cached cross-filter mechanism and wildcard
multi-line input. Adds a new `GET /api/production-history/filter-options`
endpoint backed by a v2 container-filter cache (4-tuple DISTINCT + file-based
multi-worker lock), 6 additive main-query params, and a shared wildcard
parser/emitter (`src/mes_dashboard/sql/wildcards.py`) with meta-character
rejection. Frontend adds 4 MultiSelects + 3 wildcard textareas + a
second-tier supplementary filter strip.

## Final Behavior

- Empty selection returns full distinct sets from cache with no Oracle
  round-trip; selecting any field symmetrically narrows the other three.
- Wildcard textareas accept multi-line paste; parsing is idempotent; meta
  characters are rejected and patterns are parameter-bound (no SQL string
  interpolation).
- Container-filter cache is v2 (4-tuple payload); a `schema_version` mismatch
  triggers a rebuild. Multi-worker startup uses a file-based exclusive lock so
  exactly one worker rebuilds; lock-holder crash releases the lock.
- Main query accepts 6 new optional params; Type-only callers are
  back-compatible.

## Final Contracts Updated

- `contracts/api/api-contract.md` 1.2.2 → 1.3.0 — new filter-options endpoint
  + 6 additive main-query params.
- `contracts/api/api-inventory.md` 1.1.2 → 1.1.3.
- `contracts/data/data-shape-contract.md` 1.1.0 → 1.2.0 — §2.7 filter-options
  response + §2.8 cache payload v2.
- `contracts/business/business-rules.md` 1.2.0 → 1.3.0 — PHF-01..PHF-06.
- `contracts/ci/ci-gate-contract.md` 1.3.11 → 1.3.12 — fuzz scope expansion +
  multi-worker test + schema_version rollback primitive.
- `contracts/CHANGELOG.md` — matching entries dated 2026-05-14.

## Final Tests Added / Updated

- Backend full sweep 3470 (28 new), 0 failed; route fuzz 372 (214 new);
  property 55 (52 new); integration multi-worker + Redis chaos (3 new +
  lock-crash) PASS under `--run-integration-real`.
- Frontend vitest 316 (14 new); legacy node --test 251 (7 new).
- 5 new Playwright specs / 10 tests (cross-filter, wildcard paste, multi-line
  input, lock-holder-crash resilience).

## Final CI/CD Gates

No new workflow files; existing gates absorb new tests. ci-contract 1.3.12
documents fuzz scope expansion, the multi-worker test, and the
`schema_version` rollback primitive. ci-gates.md Rollback Policy notes the
v2→v1 cache payload schema break requires post-deploy parquet/cache cleanup.
CI green on commit `4427c83` (user-confirmed 2026-05-14).

## Production Reality Findings

- **Open items resolved:** U1 (max-patterns) → hard-coded constant (100/field)
  in v1, not env-driven; U2 → shared emitter lifted to
  `src/mes_dashboard/sql/wildcards.py` as a single audit chokepoint; U3
  (Oracle hostile sequences) → cleared, `q'[...]`/`/*…*/` caught by meta
  regex, `||` and identifier-shaped sequences are bind-only; U4 (stale-sentinel
  reaper) → deferred per `resource-history-perf` precedent, runbook documents
  manual `rm`.
- **Known accepted gap (R1):** a single 10 KB wildcard token is currently
  accepted (bounded by `MAX_JSON_BODY_BYTES`); pinned by
  `test_main_query_oversized_wildcard_input_single_huge_token_accepted` so a
  future per-token cap deliberately breaks the test and forces a contract
  update.
- **Manual staging gates:** AC-1 filter-options p95 ≤ 100 ms warm and AC-6
  multi-worker lock under 4 gunicorn workers were QA-flagged as
  blocking-cdd-close. The release captain (user) authorized close on
  2026-05-14 with CI green; empirical staging measurement is carried into
  Follow-up Work as a monitoring item rather than a pre-close blocker.

## Lessons Promoted to Standards

None promoted at close. All durable product/system behavior was promoted
**during /cdd-new** across the 5 bumped contracts (api, api-inventory,
data-shape, business, ci-gate). The relevant operational rules — cache
namespace match and multi-worker startup lock — were already in `CLAUDE.md`
(Cache Architecture Notes) from the `resource-history-perf` change; this
change applied that precedent rather than discovering a new rule. No
additional process or guidance lesson emerged from the evidence.

## Follow-up Work

- **Staging monitoring (carried from QA manual gates):** confirm AC-1
  filter-options p95 ≤ 100 ms warm and AC-6 single-Oracle-round-trip lock
  under 4 gunicorn workers; empty-cache cold-start < 60 s; optional 1000-LOT
  pasted-query latency probe.
- **`material_trace_service` migration** to shared `sql/wildcards.py` — it
  still uses the older inline pattern without PHF-06 meta-char rejection;
  security follow-up to consolidate the audit chokepoint.
- **R1 per-token length cap** — track 10 KB single-token acceptance as known
  behavior; flip the pinned fuzz test to the 400-cap form when a cap lands.
- **schema_version 2 → 3 rollback drill** in the next deploy runbook so the
  rollback primitive is exercised in staging before production reliance.
- **i18n backfill** for production-history (and hold-history, reject-history,
  etc.) once project-wide i18n adoption begins.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`).

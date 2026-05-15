---
change-id: query-tool-partial-trackout
closed: 2026-05-15
status: archived
---

# Archive: query-tool-partial-trackout

## Change Summary

Extended the partial-trackout 4-tuple aggregation and strict guard (first implemented for production-history in `prod-history-detail-partial-merge`) to the query-tool module's three SQL files: `lot_history.sql`, `equipment_lots.sql`, and `adjacent_lots.sql`. The Oracle SQL dedup via `ROW_NUMBER() … WHERE rn = 1` was removed so Oracle returns raw per-partial rows; Python's new `aggregate_partial_trackouts()` in `query_tool_sql_runtime.py` groups by key tuple, applies `MAX(TRACKINQTY)` / `SUM(TRACKOUTQTY)` / `MAX(TRACKOUTTIMESTAMP)`, and falls back to raw rows on non-key column divergence (strict guard). A `partial_count` field is added to every row.

## Final Behavior

- **lot_history / equipment_lots**: grouped by 4-tuple `(CONTAINERID, EQUIPMENTID, SPECNAME, TRACKINTIMESTAMP)`; partials with consistent non-key columns are merged into one row; divergent groups fall back to raw rows each with `partial_count=1`.
- **adjacent_lots**: grouped by 3-tuple `(CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP)`; inner `dedup_rn` removed from `raw_lots` CTE; outer `ranked_lots` ROW_NUMBER for `RELATIVE_POSITION` arithmetic preserved untouched.
- **Implicit frontend effect**: query-tool timeline displays fewer rows when a lot has multiple partials under the same `TRACKINTIMESTAMP`; no frontend code change was needed because the frontend renders whatever API rows it receives.
- **TRACKOUTQTY=0 rows are valid**: confirmed via Oracle query — a lot can track in, then close with 0 output (e.g., equipment abort). The aggregation correctly preserves these as `partial_count=1` with `SUM(TRACKOUTQTY)=0`.

## Final Contracts Updated

| contract | version before | version after | key addition |
|---|---|---|---|
| `contracts/business/business-rules.md` | 1.6.1 | 1.7.0 | PH-06/PH-07 scope extended to query-tool; QT-05 (aggregation key per SQL file); QT-06 (strict guard non-key column lists) |
| `contracts/data/data-shape-contract.md` | 1.4.1 | 1.5.0 | §3.6 query-tool row shape with `partial_count` |
| `contracts/api/api-contract.md` | 1.5.1 | 1.6.0 | §10 additive `partial_count` compatibility note |

## Final Tests Added / Updated

| file | status | notes |
|---|---|---|
| `tests/test_query_tool_partial_trackout.py` | created | 38 tests across 13 classes; SQL structure, aggregation, strict-guard, decrementing-TRACKINQTY, API response shape, contract file presence |
| `tests/test_query_tool_sql_runtime.py` | extended | `TestTryComputePageFromSpool::test_partial_count_present_in_returned_data` |
| `tests/test_query_tool_pagination_contract.py` | updated | tolerate new `partial_count` field in row shape assertion |

All tests are Tier 0/1 (no Oracle connection required); decrementing-TRACKINQTY fixtures use arithmetic pattern per CLAUDE.md discipline.

## Final CI/CD Gates

| gate | result |
|---|---|
| Local `pytest` (3944 passed, 121 skipped) | PASS |
| `cdd-kit gate` | PASS |
| CI `unit-and-integration-tests` (backend-tests.yml) | PASS |
| `contract-and-fast-tests` (contract-driven-gates.yml) | PASS |

No new workflow files required. Nightly-integration is informational only; no `integration_real` query-tool tests exist.

## Production Reality Findings

- **TRACKOUTQTY=0 with valid TRACKOUTTIMESTAMP is real Oracle data**: lot `GA26040006-A00-034` at `TRACKINTIMESTAMP=2026-04-08 05:57:26` has `TRACKOUTQTY=0` because the equipment session was aborted after trackin; the lot re-ran on a different machine at 18:18:42 (proper 2-partial session with decrementing TRACKINQTY). The aggregation handled this correctly (`partial_count=1`, value preserved).
- **adjacent_lots.sql two-layer ROW_NUMBER**: the SQL has an inner `dedup_rn` (3-tuple) inside `raw_lots` and an outer `rn` in `ranked_lots` for `RELATIVE_POSITION`. Only the inner was relevant to partial-trackout dedup; the outer must be preserved or neighbor ordering breaks.
- **Timeline implicit change**: post-deploy, query-tool timeline shows fewer entries for lots with real partial trackouts. This is the correct intended behavior (mirrors production-history), but was not explicitly called out in the change classification's frontend section (4.2 was skipped). No user complaints expected — the merged row represents one machine session.

## Lessons Promoted to Standards

| lesson | target | evidence |
|---|---|---|
| Query-tool has no persistent spool — skip parquet cleanup in rollbacks | CLAUDE.md §Cache Architecture Notes | `ci-gates.md §Rollback Policy` |

Rejected (do-not-promote):
- adjacent_lots two-layer ROW_NUMBER: structural constraint already in QT-05/QT-06; inner dedup_rn no longer exists post-change; no standing guidance value.
- Timeline implicit row-count reduction: already expressed by QT-05 GROUP BY semantics in `business-rules.md`; not a silent or subtle failure mode.

## Follow-up Work

- Frontend `partial_count` tooltip: if engineers want users to see "N partial trackouts" on hover in the timeline, a follow-on frontend change is needed. Out of scope for this change.
- Oracle real-infra integration tests for query-tool: none exist yet; the nightly gate already covers them if added.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).

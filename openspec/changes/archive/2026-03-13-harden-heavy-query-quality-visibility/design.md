## Context

The project already has strong heavy-query resilience patterns in several report domains:

- chunked query execution
- spool storage
- DuckDB/cache-sql view computation
- partial/truncated metadata contracts

However, completeness signaling is not yet path-consistent across all high-volume user flows. Two practical gaps remain:

1. Query-tool single-item detail paths (`container_id`) can drop `quality_meta` while batch paths preserve it.
2. MSD UI warning behavior is still centered on genealogy failure messaging and does not consistently surface non-complete `quality_meta` states to users.

This is primarily a contract and routing consistency problem, not a database or infrastructure problem.

## Goals / Non-Goals

**Goals:**

- Make completeness metadata (`quality_meta`) path-consistent for EventFetcher-backed query-tool detail APIs.
- Ensure UI warning behavior is consistent for non-complete results in query-tool and MSD.
- Establish a migration contract so MSD uses staged completeness metadata as the canonical user-facing signal.
- Preserve existing OOM protections (chunking/spool/DuckDB) and ensure fallback paths do not hide completeness state.
- Add regression tests that lock parity between normal and fallback paths.

**Non-Goals:**

- Replacing EventFetcher with DuckDB for query-tool lineage/detail domains in this change.
- Removing legacy MSD endpoints immediately.
- Changing DB schema or Oracle SQL models.
- Reworking report business formulas unrelated to completeness signaling.

## Decisions

### 1. Unify query-tool detail response contract across single and batch paths

Decision:
- Single-item query-tool detail functions SHALL return `quality_meta` with the same schema used by batch mode.
- Route-layer behavior remains unchanged (`success_response` envelope), but payload completeness fields become mode-agnostic.

Why:
- Current single/batch divergence is the direct cause of silent non-complete-state loss in normal user flows.

Alternative considered:
- Force all single-item requests to internally call batch endpoints only.
- Rejected for now because it changes call structure and risk surface more than necessary; contract-level normalization is lower risk.

### 2. Use staged trace `quality_meta` as canonical MSD completeness signal

Decision:
- MSD UI SHALL display a visible warning banner when staged events return `quality_meta.status` in `{partial, truncated, failed}`.
- Genealogy warning remains, but does not replace completeness warning.

Why:
- MSD already consumes staged trace data for aggregation; completeness should be shown from the same source of truth.

Alternative considered:
- Keep genealogy-only warning.
- Rejected because genealogy status does not cover domain truncation/partial event fetch outcomes.

### 3. Keep legacy MSD routes as compatibility path, but define migration role clearly

Decision:
- Legacy `/api/mid-section-defect/analysis` stays compatibility-only in this phase.
- UI contract and tests SHALL be based on staged trace events completeness semantics.

Why:
- Avoids risky hard cutover while still preventing silent incompleteness in active UX path.

Alternative considered:
- Immediate endpoint deprecation/removal.
- Rejected due to operational and rollback risk.

### 4. Enforce fallback parity at contract level

Decision:
- When fallback paths are used (cache-sql disabled/error, async/sync switch, cached response replay), completeness metadata semantics SHALL remain equivalent.
- Non-complete status must never be dropped by fallback normalization code.

Why:
- The highest residual risk is metadata loss during path transitions, not during primary happy-path query execution.

Alternative considered:
- Trust existing fallback logic without explicit parity tests.
- Rejected because regressions in this area are silent and user-visible only indirectly.

### 5. Treat parity tests as release gates for this change

Decision:
- Add backend + frontend regression tests covering:
  - query-tool single vs batch `quality_meta` parity
  - MSD quality warning rendering from staged events
  - fallback-path metadata preservation

Why:
- Prevents future drift from refactors in route/service orchestration.

Alternative considered:
- Manual verification only.
- Rejected because this class of issue is subtle and easy to reintroduce.

## Risks / Trade-offs

- [Warning fatigue if too many banners] -> Use clear severity and concise copy; only show for non-`complete` states.
- [Legacy/staged coexistence confusion] -> Document canonical path and add explicit migration requirement + tests.
- [False confidence from partial metadata] -> Keep diagnostics fields (`reasons`, `failed_domains`, `failed_ranges`, `max_rows`) in UI payload mapping.
- [Cross-module implementation spread] -> Scope this change to contract/warning parity, not broad algorithm refactor.

## Migration Plan

1. Contract normalization:
   - Add `quality_meta` parity to query-tool single-item detail service responses.
2. UI completeness visibility:
   - Render non-complete warning in MSD from staged events aggregation metadata.
   - Keep existing genealogy warning as an independent signal.
3. Compatibility hardening:
   - Clarify legacy MSD route status in spec and tests.
4. Regression safety net:
   - Add test coverage for single/batch parity and staged/fallback metadata parity.

Rollback:
- Revert UI warning rendering and service payload additions without DB/data rollback.
- Legacy route behavior remains available, so rollback is low-risk operationally.

## Open Questions

- Should MSD surface separate banners for `partial` vs `truncated`, or one unified incompleteness banner with details drawer?
- Should query-tool include optional response headers mirroring `quality_meta.status` for faster edge diagnostics?
- In a later phase, should query-tool detail domains migrate to a spool/DuckDB supplemental view model, or keep EventFetcher as canonical?

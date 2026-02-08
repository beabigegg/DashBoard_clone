## Context

The migration delivered feature parity, but efficiency work remains: backend query paths still do broad copies and whole-frame recomputation even when only slices are needed. At the same time, business constraints explicitly require full-table caching for `resource` and `wip` because those datasets are intentionally small and frequently reused. This design optimizes around that constraint rather than removing it.

## Goals / Non-Goals

**Goals:**
- Keep `resource` and `wip` full-table caches intact.
- Reduce memory amplification from redundant cache representations.
- Replace repeated full merge/rebuild paths with incremental/indexed query plans where applicable.
- Increase reuse of browser-side compute modules for chart/table/filter/KPI derivations.
- Add measurable telemetry to verify latency and memory improvements.

**Non-Goals:**
- Rewriting all reporting endpoints to client-only mode.
- Removing Redis or existing layered cache strategy.
- Changing user-visible filter semantics or report outputs.

## Decisions

1. **Constrained cache strategy**
   - Decision: retain full-table snapshots for `resource` and `wip`; optimize surrounding representations and derivation paths.
   - Rationale: business-approved data-size profile and low complexity for frequent lookups.

2. **Incremental + indexed path for heavy derived datasets**
   - Decision: add watermark/version-aware incremental refresh and per-column indexes for high-cardinality filters.
   - Rationale: avoids repeated full recompute and lowers request tail latency.

3. **Canonical in-process structure**
   - Decision: keep one canonical structure per cache domain and derive alternate views on demand.
   - Rationale: reduces 2x/3x memory amplification from parallel representations.

4. **Frontend compute module expansion**
   - Decision: extract reusable browser compute helpers for matrix/table/KPI transformations used across report pages.
   - Rationale: shifts deterministic shaping work off backend and improves component reuse in Vite architecture.

5. **Benchmark-driven acceptance**
   - Decision: add repeatable benchmark fixtures and telemetry thresholds as merge gates.
   - Rationale: prevent subjective "performance improved" claims without measurable proof.

## Risks / Trade-offs

- **[Risk] Incremental sync correctness drift** → **Mitigation:** version checksum validation and periodic full reconciliation jobs.
- **[Risk] Browser compute can increase client CPU on low-end devices** → **Mitigation:** bounded dataset chunking and fallback server aggregation path.
- **[Risk] Refactor introduces subtle field-contract regressions** → **Mitigation:** keep export/header contract tests and fixture comparisons.
- **[Risk] Telemetry overhead** → **Mitigation:** low-cost counters/histograms with sampling where needed.

## Context

The reject history page displays a single Pareto chart with a dropdown to switch between 6 dimensions (reason, package, type, workflow, workcenter, equipment). Users lose cross-dimensional context when switching. The cached dataset in `reject_dataset_cache.py` already supports all 6 dimensions via `compute_dimension_pareto()` and the `_DIM_TO_DF_COLUMN` mapping. The goal is to show all 6 simultaneously in a 3×2 grid with cross-filter linkage.

Current architecture:
- **Backend**: `compute_dimension_pareto()` computes one dimension at a time from a cached Pandas DataFrame (in-memory, populated by the primary Oracle query and keyed by `query_id`). All Pareto computation is performed on this cached DataFrame — no additional Oracle queries are made.
- **Frontend**: `App.vue` holds `paretoDimension` (single ref), `selectedParetoValues` (single array), and `paretoDisplayScope`. Client-side reason Pareto is computed via `allParetoItems` computed property from `analyticsRawItems`. Other dimensions call `fetchDimensionPareto()` which hits `GET /api/reject-history/reason-pareto?dimension=X`.

## Goals / Non-Goals

**Goals:**
- Display all 6 Pareto dimensions simultaneously in a 3-column responsive grid
- Cross-filter linkage: clicking items in dimension X filters all OTHER dimensions (exclude-self)
- Detail table reflects ALL dimension selections (AND logic)
- Single batch API call for all 6 dimensions (avoid 6 round-trips)
- Unify all Pareto computation on backend (remove client-side reason Pareto)

**Non-Goals:**
- No changes to the primary query SQL or data model
- No changes to the cache infrastructure or TTL
- No new Oracle fallback paths (batch-pareto is cache-only)
- No drag-and-drop or reorderable grid layout

## Decisions

### 1. Single batch API vs 6 separate calls
**Decision**: Single `GET /api/reject-history/batch-pareto` endpoint returning all 6 dimensions.
**Rationale**: Cross-filter requires all dimensions to see each other's selections. A single call eliminates 6 round-trips and guarantees consistency across all 6 results. The cached DataFrame is shared in-memory so iterating 6 dimensions is negligible overhead.

### 2. Cross-filter logic: exclude-self pattern
**Decision**: When computing dimension X's Pareto, apply selections from all OTHER dimensions but NOT X's own.
**Rationale**: If X's own selections were applied, the Pareto would only show selected items — defeating the purpose of showing the full distribution. Exclude-self lets users see "given these TYPE and WORKFLOW selections, what is the REASON distribution?"

### 3. Remove client-side reason Pareto
**Decision**: Remove the `allParetoItems` computed property that builds reason Pareto client-side from `analyticsRawItems`. All 6 dimensions (including reason) computed by backend `compute_batch_pareto()`.
**Rationale**: Unifies computation path. The backend already has the logic; duplicating it client-side for one dimension creates divergence risk and doesn't support cross-filtering.

### 4. Retain TOP20/ALL display scope toggle
**Decision**: Keep the TOP20/全部顯示 toggle for applicable dimensions (TYPE, WORKFLOW, 機台). Apply uniformly across all 6 charts via a global control (not per-chart selectors).
**Rationale**: Even after 80% cumulative filtering, dimensions like TYPE, WORKFLOW, and 機台 can still produce many items. The TOP20 truncation remains valuable for readability in the compact grid layout. Moving to a single global toggle (instead of per-chart selectors) reduces UI clutter while preserving the functionality.

### 5. ParetoGrid wrapper vs inline loop
**Decision**: New `ParetoGrid.vue` component wrapping 6 `ParetoSection.vue` instances.
**Rationale**: Separates grid layout concerns from individual chart rendering. `ParetoSection.vue` is simplified to a pure display component. `ParetoGrid.vue` handles the dimension iteration and event delegation.

### 6. Multi-dimension selection URL encoding
**Decision**: Use `sel_reason`, `sel_package`, `sel_type`, `sel_workflow`, `sel_workcenter`, `sel_equipment` as separate array params (replacing single `pareto_dimension` + `pareto_values`).
**Rationale**: Each dimension has independent selections. Encoding them as separate params is explicit, debuggable, and backward-compatible (old URLs with `pareto_dimension` simply won't have `sel_*` params).

### 7. Multi-dimension detail/export filter
**Decision**: Extend `_apply_pareto_selection_filter()` to accept a `pareto_selections: dict` and apply all dimensions cumulatively (AND logic). Keep backward compat with single `pareto_dimension`/`pareto_values` for the existing single-dimension endpoints until they are removed.
**Rationale**: Detail table and CSV export need to filter by all 6 dimensions simultaneously. AND logic is the natural interpretation: "show rows matching these reasons AND these types AND these workflows."

## Risks / Trade-offs

- **6 charts on screen may feel crowded on smaller screens** → Responsive breakpoints: 3-col desktop, 2-col tablet, 1-col mobile. Chart height reduced from 340px to ~240px.
- **Batch pareto payload is larger (6× single)** → Still small (6 arrays of ≤20 items each). Negligible compared to the primary query.
- **Per-chart scope toggles removed in favor of global toggle** → Individual TOP20/ALL selectors inside each chart would clutter the compact grid. A single global TOP20/ALL control in supplementary filters provides the same functionality with cleaner UX.
- **Cross-filter causes re-fetch on every click** → Mitigated by cache-only computation (no Oracle queries). Typical response time < 50ms.

## Context

The query-tool ("批次追蹤工具") is the primary batch tracing page used by production engineers to trace LOT lineage, inspect production history, and query equipment records. The current implementation is a monolithic `App.vue` (343L) + `useQueryToolData.js` (448L) with custom CSS, no component decomposition, and flat `<ul>` lineage display.

The backend is fully ready:
- `/api/query-tool/resolve` — LOT/Serial/WO resolution (max 50/50/10 inputs)
- `/api/trace/lineage` — LineageEngine genealogy (ancestors + merges, rate limit 10/60s)
- `/api/query-tool/lot-history` — production history with workcenter filter
- `/api/query-tool/lot-associations` — materials/rejects/holds/splits/jobs
- `/api/query-tool/equipment-period` — 5 query types (status_hours, lots, materials, rejects, jobs)
- `/api/query-tool/export-csv` — 11 export types

All backend endpoints remain unchanged. This is a pure frontend rewrite.

Existing design patterns from other modernized pages:
- Tailwind tokens: `brand-500`, `surface-card`, `stroke-soft`, `state-*`, `rounded-card`, `shadow-panel`
- Shared components: `SectionCard`, `FilterToolbar`, `StatusBadge`, `PaginationControl`, `TraceProgressBar`
- Shared composables: `useAutoRefresh`, `usePaginationState`, `useQueryState`, `useTraceProgress`
- Font: Noto Sans TC / Microsoft JhengHei, body 13px

## Goals / Non-Goals

**Goals:**
- Complete frontend rewrite of query-tool with Tailwind + component architecture
- Tab-based layout: LOT tracing / Equipment query as independent tabs
- Lineage decomposition tree with auto-fire + concurrency control + growth animation
- Production timeline (Gantt-style) for both LOT history and equipment activity
- Left-right master-detail for LOT tab (tree left, detail right)
- Per-sub-tab CSV export
- URL state persistence for tab, filters, and selected lot

**Non-Goals:**
- No backend API changes
- No new npm dependencies (timeline is SVG/CSS, no chart library)
- No changes to other pages (mid-section-defect uses its own TraceProgressBar integration)
- No real-time/WebSocket features
- No pagination on lineage or association tables (datasets are bounded by single-lot scope)

## Decisions

### D1: Tab-based separation of LOT and Equipment

LOT tracing and equipment query are completely unrelated workflows. Users never need both simultaneously.

**Decision**: Two top-level tabs with independent state. Tab state tracked via URL `?tab=lot|equipment`.

**Alternative considered**: Keep as single scrollable page → rejected because the page becomes too long and users lose context scrolling between sections.

### D2: Lineage tree as left navigation panel

The lineage decomposition tree serves dual purpose: it IS the lot list AND the genealogy visualization.

**Decision**: After resolve, root nodes (resolved lots) appear in the left panel. Each root can expand to show ancestors. Clicking any node (root or ancestor) selects it and loads detail in the right panel.

**Rationale**: Eliminates the need for a separate "lot list" component. The tree naturally represents the resolve results + their relationships.

**Layout**: Left panel ~300px fixed width, right panel fills remaining space. Below 1024px, stack vertically.

### D3: Auto-fire lineage with concurrency limiter

After resolve, lineage is the primary value — users want to see the genealogy immediately.

**Decision**: Auto-fire `POST /api/trace/lineage` for each resolved lot with `concurrency=3`. Results render progressively as they arrive, animating tree growth.

**Concurrency calculation**: Rate limit is 10/60s. With concurrency=3 and avg ~1.5s per call, we'll sustain ~2 calls/s, comfortably below the limit. For 50 lots, all lineage completes in ~25s with continuous tree growth.

**Alternative considered**: On-demand only (click to expand) → rejected because the user explicitly wants to see the full picture immediately. The auto-fire + animation creates an engaging "tree growing" experience.

**Cache**: Per-lot lineage cached in a reactive Map. Cache cleared on new resolve.

### D4: Progressive tree growth animation

**Decision**: Use Vue `<TransitionGroup>` with CSS transforms:
- Root nodes: `opacity 0→1` (fade-in on resolve)
- Branch nodes: `translateX(-16px)→0` + `opacity 0→1` (slide-in from left)
- Sibling stagger: 30-50ms delay between consecutive siblings
- Level 2+ nodes animate when their parent's lineage data arrives (same animation)

**Implementation**: `LineageNode.vue` is a recursive component. Each node wraps its children in `<TransitionGroup>`. When the reactive lineage cache updates for a lot, Vue reactivity triggers child insertion, which triggers the enter transition.

### D5: TimelineChart as shared SVG component

Both LOT production timeline and equipment timeline need the same Gantt-style visualization.

**Decision**: Create a `TimelineChart.vue` component that accepts:
```
Props:
  tracks: Array<{ id, label, layers: Array<{ bars: Array<{start, end, type}> }> }>
  events: Array<{ trackId, time, type, label, detail }>
  timeRange: { start: Date, end: Date }
  colorMap: Record<string, string>
```

**Rendering**: Pure SVG with:
- Sticky left labels (CSS `position: sticky`)
- Horizontal time axis with auto-scaled ticks (hours or days)
- Multi-layer bars per track (background layer + foreground layer)
- Event markers as SVG icons (diamond shape) with hover tooltips
- Horizontal scroll container for wide timelines

**No external deps**: SVG + CSS only. Time calculations use native Date. No D3, no ECharts.

### D6: LOT Timeline data mapping

LOT production history records have TRACKINTIMESTAMP and TRACKOUTTIMESTAMP per station.

**Decision**: Map lot-history rows to TimelineChart tracks:
- Each unique WORKCENTERNAME = one track
- Each row = one bar (track-in to track-out, colored by workcenter group)
- Hold events from lot-holds = event markers
- Workcenter filter shows/hides tracks

### D7: Equipment Timeline multi-source composition

Equipment timeline overlays three data sources on a single track per equipment.

**Decision**: Fetch `status_hours`, `lots`, and `jobs` data, then compose:
- Layer 0 (background): Status bars (PRD=green, SBY=amber, UDT=red, SDT=blue-gray)
- Layer 1 (foreground): Lot processing bars (track-in to track-out)
- Events: Maintenance job markers (JOBID + CAUSECODENAME as label)

**Note**: This requires 3 API calls per equipment tab query. They can fire in parallel since they're independent.

### D8: Composable architecture

Split the monolithic `useQueryToolData.js` (448L) into focused composables:

| Composable | Responsibility | State |
|-----------|---------------|-------|
| `useLotResolve` | Input parsing, resolve API, URL state for resolve params | `resolvedLots`, `notFound`, `loading.resolving` |
| `useLotLineage` | Lineage auto-fire, concurrency limiter, tree expand/collapse state, cache | `lineageMap`, `expandedNodes`, `loadingSet` |
| `useLotDetail` | Per-lot history + associations, sub-tab active state, sub-tab cache | `activeSubTab`, `historyRows`, `associationRows`, caches |
| `useEquipmentQuery` | Equipment list, date range, 4 query types, sub-tab state | `equipment.*`, `activeSubTab`, query results |

Each composable manages its own loading/error state. No global error banner — errors display contextually within each section.

### D9: Delete legacy files

- `frontend/src/query-tool/main.js` → rewrite to minimal Vite entry (3-5 lines: import App, createApp, mount)
- `frontend/src/query-tool/style.css` → delete entirely, all styling via Tailwind

## Risks / Trade-offs

**[100+ lots from work order → tree overwhelm]** → The lineage tree with 100+ root nodes could be visually overwhelming. Mitigation: Virtual scroll or "show first 20, load more" pattern for the tree panel if needed. Start without it and evaluate.

**[Lineage auto-fire rate limit pressure]** → With 50 lots and concurrency=3, we'll make ~50 requests within ~25s. Rate limit is 10/60s which means we'd hit the limit at lot #10. Mitigation: The concurrency limiter must respect 429 responses and back off. If rate limited, pause and retry after `Retry-After` header. Alternatively, batch multiple container_ids per lineage call (backend already supports arrays).

**[Timeline SVG performance with large datasets]** → Equipment timeline spanning 90 days with 20 equipment could generate thousands of SVG elements. Mitigation: Aggregate status bars at coarse granularity for wide ranges, detailed view for narrow ranges. Start with naive rendering and optimize if needed.

**[Left panel width on narrow screens]** → 300px fixed width may be too wide on 1024-1280px screens. Mitigation: Make the left panel collapsible/resizable, or use a narrower default (240px) with a expand-on-hover pattern.

## Resolved Questions

- **Q1 (Resolved)**: Lineage API calls SHALL be per-lot independent (not batched). This preserves the progressive tree growth animation — each API response triggers a visual branch expansion. With concurrency=3 and 429 backoff, this stays within rate limits while providing engaging UX.
- **Q2 (Resolved)**: Equipment timeline SHALL use the `DW_MES_RESOURCESTATUS_SHIFT` aggregate table (8h shift granularity). This avoids querying raw status change events which are voluminous and not readily available via existing API. The 8h blocks are sufficient for timeline overview; users needing finer granularity can inspect the lots/jobs sub-tabs for exact timestamps.

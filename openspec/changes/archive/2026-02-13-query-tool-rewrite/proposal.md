## Why

The query-tool page ("批次追蹤工具") is the last major page still running as a monolithic Vue SFC with custom CSS. Its 343-line App.vue and 448-line useQueryToolData composable pack all three unrelated features (LOT tracing, LOT detail, equipment period query) into one vertical scroll with no component decomposition. Lineage visualization is a flat `<ul><li>` list, production history is a static table with no timeline view, and there is no progressive loading animation despite the staged trace API being available. The page needs a complete frontend rewrite to match the Tailwind + component-based architecture used by all other modernized pages, while significantly improving the tracing UX.

## What Changes

- **Complete rewrite** of `frontend/src/query-tool/` — new component tree, composables, and Tailwind-only styling (no style.css)
- **Tab-based layout**: Split LOT tracing and equipment query into independent top-level tabs
- **Lineage decomposition tree**: Replace flat ancestor list with an interactive tree that "grows" progressively as lineage API calls return (limited concurrency, animated node insertion)
- **Left-right master-detail layout**: Lineage tree as left navigation panel, LOT detail (sub-tabs) on right
- **Production timeline** (shared `TimelineChart.vue`): Gantt-style visualization for both LOT production history (stations over time) and equipment activity (lots + maintenance + status)
- **Equipment tab redesign**: Replace 5 generic query types with 4 focused sub-tabs — production lots, maintenance records (with cause/repair/symptom codes), scrap records, and equipment timeline
- **Auto-fire lineage with concurrency control**: After resolve, lineage API calls fire automatically with concurrency=3, tree grows as results arrive
- **Per-sub-tab CSV export**: Each detail sub-tab has its own export button instead of one shared context-aware export
- **Delete legacy `main.js`**: The 448-line vanilla JS module in query-tool is dead code superseded by the Vue SFC

## Capabilities

### New Capabilities
- `query-tool-lot-trace`: LOT tracing tab — query bar, lineage decomposition tree with progressive growth animation, left-right master-detail layout, LOT detail sub-tabs (history with workcenter filter + timeline, materials, rejects, holds, splits, jobs), per-tab CSV export
- `query-tool-equipment`: Equipment query tab — equipment/date selection, 4 sub-tabs (production lots, maintenance records, scrap records, equipment timeline), per-tab CSV export
- `timeline-chart`: Shared Gantt-style timeline visualization component — horizontal time axis, configurable tracks with colored bars, event markers, tooltips, used by both LOT and equipment views

### Modified Capabilities
- `progressive-trace-ux`: Lineage tree now auto-fires with concurrency-limited parallel requests and animated progressive rendering (expanding the on-demand spec to support auto-fire mode)

## Impact

- **Frontend**: Complete rewrite of `frontend/src/query-tool/` (App.vue, composables, new component tree of ~15 files)
- **Backend**: Zero changes — all existing `/api/query-tool/*` and `/api/trace/*` endpoints remain unchanged
- **Shared UI**: New `TimelineChart.vue` component may live in `shared-ui/` or query-tool local components
- **Dead code**: `frontend/src/query-tool/main.js` (448L) and `frontend/src/query-tool/style.css` deleted
- **Dependencies**: No new npm packages — timeline rendered with SVG/CSS, tree with recursive Vue components + TransitionGroup

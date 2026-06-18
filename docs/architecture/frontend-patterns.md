# Frontend Architecture Patterns

Promoted learnings from project history — TypeScript, Vue component, date formatting, and accessibility gotchas.

## TypeScript Migration Status

**Migration is complete** across all feature apps. All `core/`, `shared-composables/`, `shared-ui/`, and feature apps use TypeScript.

Intentional JS exceptions (do NOT convert):
- `portal-shell/` non-entry modules — no type coverage needed for the thin shell layer
- `workers/duckdb-worker.js` — stays JS
- `main.js` entry points — `index.html` references `./main.js`; Vite resolves `main.ts` at build time; renaming breaks the HTML reference

## Node Version Requirement

**Node ≥22.6 is required.** `environment.yml` pins `nodejs>=22.6` for `node --experimental-strip-types` support in parity tests. Do not loosen this constraint.

SFC-paired tests: `frontend/vitest.config.js` `include` already lists `src/**/*.test.ts`. Tests placed next to SFCs are covered — no config change needed when adding new SFC-paired tests.

ECharts callback parameters (`params` in formatter/tooltip) lack precise types — annotate with `// TODO: type echarts callback` rather than `any`.

## Vue-ECharts Click Events

**Bind click events via `@click` on `<VChart>`, NOT imperative `echartsInstance.on('click')`.**

The `vue-echarts` wrapper forwards all native ECharts events as Vue events carrying `params.name`/`params.data`. `@click` in the template:
- Requires no `onMounted`/`onUnmounted` cleanup
- The wrapper disposes the instance on unmount, eliminating leak risk

Rejected alternatives:
- `chart.on(...)` — requires manual lifecycle boilerplate the wrapper already handles
- ECharts `select` mode — couples visual state to ECharts internals rather than the composable

Evidence: `resource-status-cross-filter` — design.md D4.

## MultiSelect.vue — Shared by 12 Apps

`frontend/src/shared-ui/components/MultiSelect.vue` is shared by: hold-overview, job-query, mid-section-defect, production-history, query-tool, reject-history, resource-history, resource-shared, resource-status, wip-detail, wip-overview, yield-alert-center.

**Any change to its emit/prop surface must be additive** (optional events/props that unmounted consumers ignore). Before modifying any `frontend/src/shared-ui/components/` file, grep all consumer apps for usage.

Evidence: `fix-prod-history-multiselect-filter` — added `dropdown-close` as optional event so untouched consumers were no-ops.

## Snapshot-Diff Filter Composables

**Re-sync `_lastCommitted[field]` after every successful `fetchFilterOptions`.** Any composable that uses a private `_lastCommitted[field]` snapshot to skip no-op refresh must refresh that snapshot from `selection[field]` after server-driven prune, because the prune mutates `selection` without user action. Skipping this makes the next dropdown close emit a spurious cross-filter request.

Pattern: `frontend/src/production-history/composables/useFirstTierFilters.ts`

Evidence: `fix-prod-history-multiselect-filter` — `_pruneSelection` interaction with `commitSelection` diff.

## Multi-View Staleness Counters (fetchAllViews fan-out)

**Use a per-endpoint staleness dict, not a shared counter, in composables that fan out to multiple endpoints.**

A shared `stale` integer incremented once per `triggerFetch()` and decremented by any endpoint response causes a race: when the fastest endpoint responds first, it decrements the shared counter to 0 and clears the "in-flight" flag — all slower endpoints then complete silently without updating state, leaving summary/pareto/trend showing stale zeros.

Correct pattern (from `frontend/src/eap-alarm/composables/useEapAlarmViews.js`):

```js
// ❌ shared counter — any endpoint can clear the others
let stale = 0
stale++
await Promise.all([fetchSummary(stale), fetchPareto(stale), fetchTrend(stale)])

// ✅ per-endpoint counters — each endpoint tracks its own staleness
const staleCounters = reactive({ summary: 0, pareto: 0, trend: 0 })
staleCounters.summary++; const s = staleCounters.summary
// inside fetchSummary: if (staleCounters.summary !== s) return
```

Evidence: `eap-alarm-analysis` — summary cards showed 0 because shared counter was zeroed by the fastest endpoint.

## Oracle DATE Midnight UTC — TZ-Safe Formatting

**Oracle DATE columns serialised as midnight UTC (`T00:00:00`) must NOT be passed to `new Date()` in a non-UTC locale.**

Safe pattern:
```js
// Inspect raw H/M/S digits via regex first
const m = dateStr.match(/T(\d{2}):(\d{2}):(\d{2})/)
if (m && m[1] === '00' && m[2] === '00' && m[3] === '00') {
  // Extract y/m/d directly — avoids ±8h TZ shift (UTC+8 turns midnight into 08:00:00)
  return dateStr.slice(0, 10)
}
// Only call new Date() when raw time is non-zero
return new Date(dateStr).toLocaleString()
```

Pattern: `frontend/src/material-consumption/components/DetailTable.vue::formatTxnDate`

Applies to every frontend formatter for Oracle DATE columns across all feature apps.

Evidence: `material-part-consumption` — `txn_date` displayed 08:00:00 for all records until the raw-string check was added.

## WAI-ARIA Combobox Focus Return

**Combobox close paths must return focus to the trigger.** When adding Escape / outside-click / programmatic close to any popup-style component (MultiSelect, dropdown, dialog), the close handler must:

```js
nextTick(() => triggerEl.focus())
```

Without this, keyboard users lose focus context entirely.

Pattern: `frontend/src/shared-ui/components/MultiSelect.vue::closeDropdown()`

Evidence: `fix-prod-history-multiselect-filter` — ui-ux-reviewer flagged missing focus return after adding Escape support; fixed inline before merge.

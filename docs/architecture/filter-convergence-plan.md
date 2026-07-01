# Filter-Logic Convergence Plan (Phase F-2)

> Produced: 2026-06-30 — query-arch convergence, Phase F-2.
> Status: assessment + migration recipe. Per-app migrations are follow-up PRs
> gated on manual QA (filter behaviour cannot be fully verified by unit tests).

## Why this is a plan, not a bulk migration

The frontend has **two** filter architectures: 10 feature apps drive filters
through the shared `shared-composables/useFilterOrchestrator.ts`, while the rest
hand-roll their own filter composables. A wholesale rewrite of every bespoke app
in one change is neither safe nor correct — several apps are bespoke for good
reasons (snapshot-diff, input-type-driven, heavy cross-filter coupled to a DuckDB
runtime). This document categorises every non-orchestrator app, gives a concrete
migration recipe, and recommends a batched order so each migration ships as its
own QA-able PR.

## What `useFilterOrchestrator` already supports

`useFilterOrchestrator(config)` is config-driven (see `useFilterOrchestrator.ts`):

- `fields: Record<string, FieldDefinition>` — each field has a `trigger`:
  `'immediate'` (update → commit → fetch) or `'draft-apply'` (stage in `draft`,
  commit on `applyDraft()`).
- `dependencies: FieldDependency[]` — when a parent field changes, run
  `'reload-options'` / `'clear'` / `'reset'` on a target field. **`reload-options`
  is cross-filter narrowing** (re-fetch a child's options from a parent's value).
- `pagination` + `resetPaginationIfNeeded` — reset page on filter change.
- `urlSync` — optional URL state sync.
- `onFetch` / `onPrimaryQuery` callbacks for the actual data calls.

So flat filters AND basic cross-filter narrowing are already expressible. What it
does **not** model: snapshot-diff "skip no-op refresh" tracking, and input-type
dispatch (one input box that routes to different query shapes).

## Categorisation of the bespoke apps

| App | Filter mechanism | cross-filter | snapshot-diff | Verdict |
|---|---|---|---|---|
| **job-query** | flat filters inside `useJobQueryData.ts`; client-side pagination | no | no | ✅ **Clean candidate** |
| **db-scheduling** | single MultiSelect; reuses WIP cache (ADR-0013) | no | no | ✅ **Clean candidate** (small) |
| **material-consumption** | `useConsumptionQuery.ts`; some option narrowing | light | no | 🟡 **Medium** — migrate after the clean ones |
| **production-history** | `useFirstTierFilters.ts` — cross-filter + `_lastCommitted` snapshot-diff | yes | yes | 🟠 **Needs snapshot-diff support first** |
| **eap-alarm** | `useEapAlarmFilter.js` — snapshot-diff (`_lastCommitted`) + fine-filter re-query | yes | yes | ⛔ **Keep bespoke** (canonical snapshot-diff) |
| **downtime-analysis** | `useFilterState.ts` (106L) + 7 cross-filter sites coupled to `useDowntimeDuckDB.ts` (1111L) | heavy | yes | ⛔ **Keep bespoke** (DuckDB-runtime coupling) |
| **query-tool** | input-type-driven; 6 composables (`useLotDetail`, `useEquipmentQuery`, …) | yes | no | ⛔ **Keep bespoke** (not a filter-grid model) |
| **anomaly-overview**, **qc-gate**, **material-trace** | no MultiSelect / no filter grid | n/a | n/a | ➖ **N/A** — no filter surface to converge |

(Data verified by surveying `MultiSelect` usage, `filter-options`/`cross`, and
`_lastCommitted`/`snapshot` references per app on 2026-06-30.)

## Migration recipe (bespoke → `useFilterOrchestrator`)

Reference adopters to copy from: `reject-history`, `wip-overview` (both already
on the orchestrator). For a clean flat-filter app:

1. **Inventory the fields.** List every filter the app reads (name, default,
   single vs multi-select).
2. **Build `fields`.** One `FieldDefinition` per field. Use `trigger: 'immediate'`
   for selects that should fetch on change; `trigger: 'draft-apply'` for a date
   range or text box committed via an "apply" button.
3. **Map cross-filter to `dependencies`.** For each "selecting A narrows B", add
   `{ field: 'A', target: 'B', action: 'reload-options' }`; use `'clear'`/`'reset'`
   when the child selection should also be cleared.
4. **Wire callbacks.** `onFetch` → the view fetch; `onPrimaryQuery` → the
   primary/full re-query used when draft-apply fields change.
5. **Pagination + URL.** Pass `pagination` so page resets on filter change; opt
   into `urlSync` only if the app already persisted filters in the URL.
6. **Delete the bespoke composable** once the App.vue consumes the orchestrator.
7. **QA.** Manually verify: each filter fetches; cross-filter narrows the child;
   page resets; no stale results on rapid changes (pair with `useViewStaleness`
   from F-1 for multi-view apps).

**Snapshot-diff gap (blocks production-history / eap-alarm).** Apps that skip a
no-op refresh via a `_lastCommitted` snapshot need an orchestrator feature that
does not exist yet: a per-field "committed snapshot" the orchestrator re-syncs
after every option reload (see `frontend-patterns.md §Snapshot-Diff Filter
Composables`). Add that to `useFilterOrchestrator` **first** (its own PR, with
unit tests), then migrate those apps. Until then they stay bespoke.

## Recommended batched rollout (one PR per batch)

1. **Batch 1 — clean candidates:** `job-query`, `db-scheduling`. Lowest risk;
   establishes the migration as proven for flat filters.
2. **Batch 2 — medium:** `material-consumption` (light option narrowing).
3. **Batch 3 — orchestrator feature work:** add snapshot-diff support to
   `useFilterOrchestrator` (+ unit tests), then migrate `production-history`.
4. **Keep bespoke (do not migrate):** `eap-alarm`, `downtime-analysis`,
   `query-tool` — document the reason inline so future readers don't "fix" them.
5. **N/A:** `anomaly-overview`, `qc-gate`, `material-trace` — no filter grid.

Each batch is a separate PR with manual QA of the affected page(s); none should
be bundled, because filter regressions are user-visible and not fully caught by
unit tests.

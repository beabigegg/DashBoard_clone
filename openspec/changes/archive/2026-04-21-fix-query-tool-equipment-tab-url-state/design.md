## Context

The Query Tool equipment tab already persists its state into the URL, but the
page does not fully hydrate that state back into the tab UI after a hard reload.
The current regression is narrow in scope but user-visible: `tab=equipment` and
the associated date params remain in the address bar, while the visible active
tab and `aria-current="page"` state do not reflect those params.

This is a frontend-only change centered on the Query Tool page's URL-state
restore flow. It affects route initialization, tab-state hydration, and the
accessibility semantics derived from active tab state. It does not require API
changes.

## Goals / Non-Goals

**Goals:**
- Restore the equipment tab and its sub-state from URL params on initial page
  load and hard reload.
- Ensure `aria-current` is driven by reactive state, not click-only DOM logic.
- Remove the `test.fixme` guard in the existing Playwright regression once the
  restoration flow is correct.

**Non-Goals:**
- Redesign Query Tool navigation or tab UX.
- Change backend route behavior or URL parameter names.
- Rework unrelated lot-trace or export flows.

## Decisions

### Restore tab state from a single URL-hydration path

The page SHALL use a single initialization path that reads URL params and
hydrates active tab and sub-tab state. This avoids splitting behavior between
click handlers, `onMounted`, and ad hoc watchers.

Alternative considered:
- Re-trigger the DOM click handler after mount.
  Rejected because it couples state restoration to UI event timing and can leave
  `aria-current` or dependent state out of sync.

### Derive accessibility state from the same reactive source of truth

The tab button's `aria-current="page"` SHALL be computed from the same reactive
active-tab value used for rendering. This ensures reload, back/forward, and
direct links all produce the same semantics.

Alternative considered:
- Keep `aria-current` mutation in click handlers only.
  Rejected because reload does not pass through that path.

### Restore URL-driven sub-state in the same transaction as the top-level tab

Equipment sub-tabs and date filters SHALL be restored as part of the same
hydration step as the top-level `tab=equipment` state, so the page never enters
an intermediate "URL says equipment, UI still on default tab" state.

Alternative considered:
- Restore top-level tab first, then lazily restore sub-state later.
  Rejected because it increases flicker and race conditions during mount.

## Risks / Trade-offs

- [Hydration order mismatch] If the page restores sub-state before the tab body
  is mounted, controls may not render correctly. → Mitigation: normalize URL
  params first, then apply state in the component lifecycle stage where the tab
  tree is available.
- [State divergence] If the page still has multiple tab-state write paths,
  reload may be fixed while in-app navigation remains inconsistent. →
  Mitigation: funnel tab writes through one helper and use it for both click and
  hydration flows.
- [Regression in other Query Tool tabs] Shared state plumbing may affect lot or
  lot-equipment tabs. → Mitigation: keep the change scoped to state restoration
  and rerun existing Query Tool URL-state coverage.

## Migration Plan

1. Identify the component/composable that owns Query Tool tab state.
2. Introduce a single URL-to-state hydration helper for initial load and route
   updates.
3. Bind tab button active semantics to reactive state.
4. Remove `test.fixme` from the Playwright regression once the flow is stable.
5. Run focused frontend tests for Query Tool URL state.

Rollback: revert the hydration helper and restore the previous `fixme` if the
change destabilizes unrelated Query Tool tabs.

## Open Questions

- Whether lot-equipment sub-tab restoration should be fixed in the same change
  if it shares the same root cause.
- Whether invalid/unknown `tab` params should silently fall back to the default
  tab or actively normalize the URL.

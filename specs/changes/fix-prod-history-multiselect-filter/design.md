---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Design: fix-prod-history-multiselect-filter

## 1. Dropdown-close event on MultiSelect

- **Event name**: `dropdown-close` (additive, verb-state). Chosen over `close` (collision risk with panel `@close` already used in wip-detail, resource-status, portal-shell, tables, mid-section-defect) and over `v-model:open` (would require all 9 consumers to opt in to the new model). Grep across `frontend/src/` confirms no existing consumer emits or listens to `dropdown-close` today.
- **Payload**: `string[]` — a defensive copy of `props.modelValue` cast to string, taken at the moment `isOpen` flips `true → false`. Justification: emitting the final committed selection lets the parent run a diff without reaching back into composable state; the cost is a single array spread. Parent currently reads from `firstTier.selection[field]` (already mutated by `update:modelValue`), so the payload is redundant for production-history but useful for unit tests and future consumers that don't keep a parallel buffer.
- **Trigger surface (single source of truth: `watch(isOpen)`)**:
  - Outside-click: `handleOutsideClick` ([MultiSelect.vue:108-111](../../../frontend/src/shared-ui/components/MultiSelect.vue#L108-L111)) sets `isOpen = false`.
  - 「關閉」footer button: `closeDropdown()` ([MultiSelect.vue:70-72](../../../frontend/src/shared-ui/components/MultiSelect.vue#L70-L72), called at line 175) sets `isOpen = false`.
  - Toggle when already open: `toggleDropdown()` ([MultiSelect.vue:74-77](../../../frontend/src/shared-ui/components/MultiSelect.vue#L74-L77)) flips `isOpen`.
  - **Escape**: NOT currently handled. Adding `@keydown.esc.stop="closeDropdown"` on the dropdown root (line ~145, `.multi-select-dropdown`) so Escape inside the popup drives the same `isOpen = false` path. Test-plan AC-2 explicitly parametrizes over Escape.
  - **Blur / focus-leave**: not separately handled today. Outside-click already covers click-driven focus-leave. Pure keyboard tab-out is rare for this component (popup contains its own focus trap on the search input); we accept the gap and document it.
  - All four paths converge on `isOpen = false`. The `watch(isOpen, (now, prev) => { if (prev && !now) emit('dropdown-close', [...props.modelValue].map(String)); })` is the single emit site.
- **Back-compat**: additive. The 8 other consumer apps (wip-detail, wip-overview, hold-overview, reject-history, resource-history, resource-status, query-tool, mid-section-defect, yield-alert-center) never list `dropdown-close`, so the emit is dropped on the floor. `update:modelValue` continues to fire on every toggle exactly as before.

## 2. Buffer/commit split in useFirstTierFilters

- `setSelection(field, values)` (line 210): **buffer-only**. Mutates `selection[field]`, clears `prunedFields` if needed, returns. Does NOT call `_scheduleRefresh()`. Signature unchanged for back-compat.
- New `commitSelection(field: CachedFilterField)`: no `values` arg — reads from `selection[field]` (already buffered). Compares against private `_lastCommitted[field]` snapshot (closure-private map, initialised to `[]` per field at composable construction). Equality via length + index-wise `===` (selection values are normalized strings). On equality: no-op (AC-4). On change: update `_lastCommitted[field] = [...selection[field]]`, call `_scheduleRefresh()`.
- **Why snapshot in the composable, not the parent**: keeps the parent stateless and lets the same composable serve callers that don't know when the dropdown opens. Also survives v-if remounts of the MultiSelect.
- **Prune interaction**: `_pruneSelection` (line 254) mutates `selection[field]` when the server narrows options. After every successful `fetchFilterOptions`, refresh `_lastCommitted` from `selection` so a subsequent close with no user change is still a no-op.
- **200 ms debounce in `_scheduleRefresh`**: **keep**. Rationale: cheap safety net if two MultiSelects close back-to-back (e.g., user tabs through filters with keyboard). Removal would require additional regression evidence and is out of scope.

## 3. App.vue wiring

The 4 existing `@update:model-value="firstTier.setSelection('<field>', $event)"` lines stay (now buffer-only). Add `@dropdown-close="firstTier.commitSelection('<field>')"` on each of the 4 MultiSelects ([App.vue:320-365](../../../frontend/src/production-history/App.vue#L320-L365)). `commitSelection` takes no `$event` because the truthful state already lives in `firstTier.selection`.

## 4. Migration / Rollback

UI-only change. Forward: `cd frontend && npm run build`. Rollback: `git revert <merge-sha> && cd frontend && npm run build` + gunicorn reload. No DB / parquet / cache namespace touched.

## 5. Rejected alternatives

- **Apply button**: rejected per CR §Constraints (「不新增 Apply 按鈕」).
- **Bump existing 200 ms debounce to 3 s**: rejected — UX hack; would still fire while user is still considering options (i.e. mouse stationary > 3 s reading labels).
- **`v-model:open` on MultiSelect**: rejected — forces every existing consumer to either bind it or accept undefined behaviour; not additive.
- **Emit-on-blur with no diff**: rejected — would fire spurious cross-filter calls on every dropdown open/close cycle even when the user touched nothing.

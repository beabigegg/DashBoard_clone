## Post-Review Fixes

### High: Cache replay silent-hide regression (`_ensure_events_quality_meta`)

**Root cause:** `_ensure_events_quality_meta` used `if payload.get("quality_meta")` to decide whether to re-merge from domain metas. A stale cached payload with `top=complete, domain=partial` would return `complete`, hiding the non-complete warning in MSD.

**Fix:** Changed priority: when `domain_quality_meta` is non-empty, always re-derive top-level from domain metas via `merge_quality_metas`. The cached top-level is only used as a fallback when no domain metas are available.

**Regression test added:** `test_cached_events_replay_domain_partial_overrides_stale_complete_top_level` in `test_trace_routes.py`.

### Medium: MSD frontend test coverage (task 5.3)

Added `frontend/tests/msd-completeness-warning.test.js` with 6 tests covering:
- `partial`/`truncated`/`failed` statuses trigger warning
- `complete` and null/empty suppress warning
- Warning suppressed while loading or before first query
- Correct Chinese warning text per status
- Independence from genealogy warning (both can coexist)

### Medium: Release gate 6.1 scope clarification

Frontend gate applies to targeted test files runnable via `node --test`. The 4 pre-existing failures in `query-tool-composables.test.js` predate this change (verified via `git stash`). Gate-applicable passing tests: `node --test frontend/tests/msd-completeness-warning.test.js` (6/6) and `node --test frontend/tests/query-tool-composables.test.js` new tests (2 added pass).

---

## Release Checklist

- [x] Single-item query-tool history response includes `quality_meta` and `pagination` (parity with batch mode)
- [x] Single-item query-tool association responses (materials/rejects/holds) include `quality_meta` and `pagination`
- [x] Route handlers pass `page`/`per_page` to single-item service functions
- [x] MSD App.vue surfaces staged events `quality_meta` non-complete warning independently of genealogy warning
- [x] Trace events cached-replay path preserves non-complete `quality_meta` (guarded by `_ensure_events_quality_meta`)
- [x] Backend parity tests: single vs batch `quality_meta` presence verified in `test_query_tool_routes.py`
- [x] Backend cache replay test: `test_cached_events_replay_preserves_non_complete_quality_meta` in `test_trace_routes.py`
- [x] Frontend composable tests: single-item quality_meta capture verified for history and associations

### Route-mode parity confirmation
Both single-item (`container_id`) and batch (`container_ids`) paths for `lot-history` and `lot-associations` now return equivalent `quality_meta` and `pagination` keys. The frontend composable reads `inner?.quality_meta || null` in both code paths, so warning visibility is mode-agnostic.

## Before/After Evidence

### Before

Single-item service functions discarded `quality_meta`:
```python
# BEFORE — quality_meta silently dropped
events_by_cid, _quality_meta = _fetch_domain_records([container_id], "history")
return {
    'data': data,
    'total': len(data),
    'container_id': container_id,
    # no quality_meta key
}
```

Frontend composable read `inner?.quality_meta || null` but received `null` for all single-item requests, so `qualityMeta.history` was always `null` → no warning ever shown in single-LOT mode.

MSD App.vue had no completeness warning block driven by staged events `quality_meta` — only a genealogy-error warning.

### After

Single-item service functions propagate `quality_meta`:
```python
# AFTER — quality_meta preserved and returned
events_by_cid, quality_meta = _fetch_domain_records([container_id], "history")
return {
    'data': data,
    'total': len(rows),
    'pagination': pagination,
    'quality_meta': quality_meta,  # ← now included
    'container_id': container_id,
}
```

MSD App.vue now shows an independent completeness warning banner:
```html
<div v-if="hasCompletenessWarning" class="warning-banner">
  {{ completenessWarningText }}
</div>
```
driven by `trace.stage_results.events?.quality_meta` — independently of genealogy status.

Non-complete states (`partial`, `truncated`, `failed`) are now visible to users in:
1. Query-tool single-LOT history/associations view
2. MSD analysis page from staged trace events

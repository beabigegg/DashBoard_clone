# `tmtt-defect` Rewrite Exemplar

## Scope

- Route: `/tmtt-defect`
- Goal: establish the first canonical legacy rewrite pattern with:
  - Vue SFC composition
  - shared UI layer reuse
  - Tailwind token layer coexistence
  - no iframe / no wrapper dependency

## Implemented Structure

- Entry: `frontend/src/tmtt-defect/main.js`
- Page container: `frontend/src/tmtt-defect/App.vue`
- Data state/composable: `frontend/src/tmtt-defect/composables/useTmttDefectData.js`
- Reusable page components:
  - `frontend/src/tmtt-defect/components/TmttKpiCards.vue`
  - `frontend/src/tmtt-defect/components/TmttChartCard.vue`
  - `frontend/src/tmtt-defect/components/TmttDetailTable.vue`
- Shared UI usage:
  - `frontend/src/shared-ui/components/FilterToolbar.vue`
  - `frontend/src/shared-ui/components/SectionCard.vue`
  - `frontend/src/shared-ui/components/StatusBadge.vue`
- Backend template mount shell: `src/mes_dashboard/templates/tmtt_defect.html`

## Behavioral Parity

The rewrite keeps current route and API contracts:

- Query API: `GET /api/tmtt-defect/analysis`
- Export API: `GET /api/tmtt-defect/export`
- Sort/filter/detail behavior preserved on result table

Smoke coverage references:

- `TMTT-SMOKE-01` ~ `TMTT-SMOKE-06` in `legacy_rewrite_smoke_checklists.md`

## Verification Snapshot

- `npm --prefix frontend run build` passed
- `pytest -q tests/test_template_integration.py tests/test_portal_shell_routes.py tests/test_cutover_gates.py tests/test_app_factory.py` passed

This page is the baseline implementation that remaining legacy rewrites follow.

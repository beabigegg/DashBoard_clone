# Change Request

## Original Request

Migrate `frontend/src/qc-gate/` feature app (QC-GATE 狀態) from JavaScript to TypeScript. This is Phase 3 item #17 of the project-wide TS migration plan. Affected surface: frontend/src/qc-gate/ (main.js, App.vue, composables/useQcGateData.js, components/LotTable.vue, components/QcGateChart.vue). Desired behavior: rename .js files to .ts, add `<script setup lang="ts">` with typed props/emits/refs to all SFCs, annotate echarts callback with TODO comment. No runtime behavior change. Success criterion: npm run type-check passes with zero errors and src/qc-gate/**/* in tsconfig.json include; npm run test, npm run build, npm run css:check remain green.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority

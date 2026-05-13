# Change Request

## Original Request

Migrate wip-overview, wip-detail, hold-overview, hold-detail from JavaScript to TypeScript (rename main.js→main.ts and all .vue script sections to lang="ts"). Pure Tier 3 TypeScript migration — no API, CSS, or business logic changes. Affected surface: frontend/src/wip-overview/, frontend/src/wip-detail/, frontend/src/hold-overview/, frontend/src/hold-detail/. Desired behavior: all four feature apps pass vue-tsc --noEmit with zero errors. Success criterion: npm run type-check exits 0, npm run css:check exits 0, all existing Vitest tests pass, no runtime behavior change.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority

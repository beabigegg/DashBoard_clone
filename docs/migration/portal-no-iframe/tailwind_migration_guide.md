# Tailwind Migration Guide (Portal No-iframe)

## Purpose

Move distributed page CSS toward a token-driven Tailwind system without breaking existing portal behavior.

## Step-by-step

1. Keep existing route/page behavior unchanged.
2. Replace repeated layout wrappers with Tailwind utilities first (`grid`, `flex`, spacing, radius, shadows).
3. Replace repeated visual primitives with shared component classes from `@layer components`.
4. Move hard-coded colors/spacing to tokens in `tailwind.config.js` and `tailwind.css`.
5. Remove obsolete page-local CSS only after visual parity is verified.

## Recommended migration order

1. Shell and shared navigation blocks
2. Filter bars and KPI card rows
3. Shared table containers and pagination controls
4. Page-specific edge states and empty/error banners

## Parity checks per batch

- Drawer visibility and route links stay unchanged.
- Existing URL/query semantics remain compatible.
- No new runtime style conflicts in non-admin/admin views.

## Do / Don’t

- Do: prefer composable utility classes and shared Vue components.
- Do: keep style changes scoped to one route family per batch.
- Don’t: introduce new long inline `<style>` blocks in templates.
- Don’t: mix unrelated refactors with migration styling tasks.

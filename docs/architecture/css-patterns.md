# CSS Architecture Patterns

Promoted learnings from project history — portal-shell CSS scoping and build pipeline gotchas.

## All Feature CSS Must Be Scoped Under .theme-<name>

**Portal-shell (`nativeModuleRegistry.js`) loads each feature's CSS bundle once via dynamic `import()` and caches it permanently in `<head>`.** Unscoped rules (e.g., `.card`, `.pareto-chart-wrap`) from any bundle bleed into every subsequent page because no bundle is ever unloaded.

Always prefix every rule with the feature's root class:
```css
/* Correct */
.theme-hold-history .card { ... }

/* Wrong — bleeds globally */
.card { ... }
```

Specificity `0-2-0` beats unscoped `0-1-0` regardless of injection order.

**Enforced by `npm run css:check` Rule 6** (`frontend/scripts/css-governance-check.js`); CI fails the build on any unscoped top-level rule in a feature `style.css`.

Evidence: `hold-history-detail-flat-table` — unscoped `.pareto-chart-wrap { height: 360px }` in hold-history CSS overrode hold-overview's chart height on page switch. A follow-up audit found 290+ unscoped rules across 7 features.

## CSS Source Fixes Require npm run build

**The app serves from `src/mes_dashboard/static/dist/` (Flask static), not the Vite dev server.** After editing any `frontend/src/*/style.css`, run:

```bash
cd frontend && npm run build
```

New builds generate hashed filenames (e.g., `style5.css`) rather than named files (e.g., `hold-history.css`) — stale named files in `dist/` are orphaned and not referenced by the new bundles.

## CSS rules 4.4 and 4.5

These rules are documented in `contracts/css/css-contract.md`:

- **Rule 4.4** — `<Teleport to="body">` moves the DOM node outside the feature root. Wrap the teleported content in a thin `<div class="theme-<feature>">`. Do NOT combine both classes on the same element.
- **Rule 4.5** — `resource-shared/styles.css` `:is()` groups must include every portal-shell page theme (95 occurrences). Use `sed` batch replacement when adding a new page.

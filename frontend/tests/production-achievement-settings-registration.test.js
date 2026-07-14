/**
 * production-achievement-settings-registration.test.js — registry parity
 * for the new standalone /production-achievement-settings route
 * (production-achievement-overhaul, IP-9).
 *
 * Implementation-plan.md requires registering the route in 7 locations
 * total: 6 static registries asserted here, plus 1 code-path check
 * (navigationState.js's STANDALONE_DRILLDOWN_ROUTES, exercised via
 * buildDynamicNavigationState() in
 * frontend/tests/legacy/portal-shell-navigation.test.js — "no drawer entry
 * (D4)" test — which this file complements, not duplicates).
 *
 * `vite.config.ts`'s INPUT_MAP is asserted via a raw source-text scan rather
 * than importing the module: the file's default export is a `defineConfig()`
 * FUNCTION wrapping Vite's own `resolve(__dirname, ...)` path-building logic,
 * which is meant to run inside Vite's own config loader (special __dirname
 * handling), not as a plain imported module in a test — a text scan avoids
 * depending on that runtime and just proves the literal registry entry
 * exists in source, which is all this parity check needs.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

import { getRouteContract } from '../src/portal-shell/routeContracts.js';
import { getNativeModuleLoader } from '../src/portal-shell/nativeModuleRegistry.js';
import pageStatus from '../../data/page_status.json';
import routeScopeMatrix from '../../docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json';
import assetReadinessManifest from '../../docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json';

const ROUTE = '/production-achievement-settings';
const __dirname = dirname(fileURLToPath(import.meta.url));

function readViteConfigSource() {
  return readFileSync(resolve(__dirname, '../vite.config.ts'), 'utf-8');
}

describe('production-achievement-settings — 6-registry parity (7 locations total, see portal-shell-navigation.test.js for the 7th)', () => {
  it('1/7: vite.config.ts INPUT_MAP has a "production-achievement-settings" entry pointing at its own index.html', () => {
    const source = readViteConfigSource();
    expect(source).toMatch(/['"]production-achievement-settings['"]\s*:\s*resolve\(__dirname,\s*['"]src\/production-achievement-settings\/index\.html['"]\)/);
  });

  it('2/7: routeContracts.js has a ROUTE_CONTRACTS entry with renderMode "native" and a released_or_admin visibility policy', () => {
    const contract = getRouteContract(ROUTE);
    expect(contract).not.toBeNull();
    expect(contract.route).toBe(ROUTE);
    expect(contract.renderMode).toBe('native');
    expect(contract.visibilityPolicy).toBe('released_or_admin');
    expect(contract.scope).toBe('in-scope');
    expect(contract.canonicalShellPath).toBe(`/portal-shell${ROUTE}`);
  });

  it('4/7: nativeModuleRegistry.js registers a loader for the route (code-path, not just a config value)', () => {
    const loader = getNativeModuleLoader(ROUTE);
    expect(typeof loader).toBe('function');
  });

  it('5/7: data/page_status.json has an explicit status entry for the route', () => {
    expect(pageStatus.statuses).toHaveProperty(ROUTE);
    expect(['released', 'dev']).toContain(pageStatus.statuses[ROUTE]);
  });

  it('6/7: route_scope_matrix.json lists the route as in_scope', () => {
    const entry = routeScopeMatrix.in_scope.find((r) => r.route === ROUTE);
    expect(entry).toBeDefined();
    expect(entry.category).toBe('report');
  });

  it('7/7: asset_readiness_manifest.json requires exactly one built asset for the route', () => {
    const assets = assetReadinessManifest.in_scope_required_assets[ROUTE];
    expect(assets).toBeDefined();
    expect(assets).toEqual(['production-achievement-settings.js']);
  });

  it('all registries agree on the SAME route string (no typo drift between files)', () => {
    const contract = getRouteContract(ROUTE);
    const scopeEntry = routeScopeMatrix.in_scope.find((r) => r.route === ROUTE);
    expect(contract.route).toBe(scopeEntry.route);
    expect(Object.keys(pageStatus.statuses)).toContain(scopeEntry.route);
    expect(Object.keys(assetReadinessManifest.in_scope_required_assets)).toContain(scopeEntry.route);
  });
});

/**
 * dashboard-home-registration.test.js — registry parity for the new `/`
 * landing-page route.
 *
 * Unlike a normal feature page, `/` intentionally does NOT get entries in
 * routeContracts.js / page_status.json / route_scope_matrix.json /
 * asset_readiness_manifest.json — router.js hardcodes `/` as a statically
 * pre-registered route (not synced via buildDynamicNavigationState()), and
 * its Flask view (portal_index()) is an unconditional redirect to
 * /portal-shell that never touches the modernization-policy gates those
 * registries feed.
 *
 * vite.config.ts's INPUT_MAP and router.js's route table are asserted via
 * raw source-text scans rather than importing the modules — same rationale
 * as production-achievement-settings-registration.test.js (vite.config.ts's
 * default export is a defineConfig() function meant to run inside Vite's
 * own loader; router.js has import-time side effects — restoreUrlState() —
 * that make a live import awkward in a unit test).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

import { getNativeModuleLoader } from '../src/portal-shell/nativeModuleRegistry.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relPath) {
  return readFileSync(resolve(__dirname, relPath), 'utf-8');
}

describe('dashboard-home — "/" landing-page registration', () => {
  it('vite.config.ts INPUT_MAP has a "dashboard-home" entry pointing at its own index.html', () => {
    const source = readSource('../vite.config.ts');
    expect(source).toMatch(
      /['"]dashboard-home['"]\s*:\s*resolve\(__dirname,\s*['"]src\/dashboard-home\/index\.html['"]\)/
    );
  });

  it('nativeModuleRegistry.js registers a loader for "/" (code-path, not just a config value)', () => {
    const loader = getNativeModuleLoader('/');
    expect(typeof loader).toBe('function');
  });

  it('router.js routes "/" through NativeRouteView, not the static ShellHomeView placeholder', () => {
    const source = readSource('../src/portal-shell/router.js');
    const rootRouteMatch = source.match(/path:\s*['"]\/['"][\s\S]*?component:\s*(\w+)/);
    expect(rootRouteMatch).not.toBeNull();
    expect(rootRouteMatch[1]).toBe('NativeRouteView');
  });

  it('router.js still keeps ShellHomeView as the catch-all fallback for unmatched paths', () => {
    const source = readSource('../src/portal-shell/router.js');
    const fallbackMatch = source.match(/name:\s*['"]shell-fallback['"][\s\S]*?component:\s*(\w+)/);
    expect(fallbackMatch).not.toBeNull();
    expect(fallbackMatch[1]).toBe('ShellHomeView');
  });

  it('portal-shell App.vue no longer auto-redirects "/" away to the first drawer page', () => {
    const source = readSource('../src/portal-shell/App.vue');
    expect(source).not.toMatch(/isPortalShellRootPath/);
  });
});

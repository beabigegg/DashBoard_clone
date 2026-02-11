import test from 'node:test';
import assert from 'node:assert/strict';

import { toRuntimeRoute } from '../src/core/shell-navigation.js';
import { getNativeModuleLoader } from '../src/portal-shell/nativeModuleRegistry.js';
import { buildDynamicNavigationState } from '../src/portal-shell/navigationState.js';
import { getRouteContract } from '../src/portal-shell/routeContracts.js';

const WAVE_A_ROUTES = Object.freeze([
  '/wip-overview',
  '/wip-detail',
  '/hold-overview',
  '/hold-detail',
  '/hold-history',
  '/resource',
  '/resource-history',
  '/qc-gate',
  '/tmtt-defect',
]);

const WAVE_B_NATIVE_ROUTES = Object.freeze([
  '/job-query',
  '/excel-query',
  '/query-tool',
]);

test('Wave A contracts resolve to native mode with native module loaders', () => {
  WAVE_A_ROUTES.forEach((routePath) => {
    const contract = getRouteContract(routePath);
    assert.ok(contract, `missing contract: ${routePath}`);
    assert.equal(contract.renderMode, 'native', `route mode mismatch: ${routePath}`);
    assert.equal(typeof getNativeModuleLoader(routePath), 'function', `missing native loader: ${routePath}`);
  });
});

test('Wave B contracts resolve to native mode with native module loaders after rewrite', () => {
  WAVE_B_NATIVE_ROUTES.forEach((routePath) => {
    const contract = getRouteContract(routePath);
    assert.ok(contract, `missing contract: ${routePath}`);
    assert.equal(contract.renderMode, 'native', `route mode mismatch: ${routePath}`);
    assert.equal(typeof getNativeModuleLoader(routePath), 'function', `missing native loader: ${routePath}`);
  });
});

test('Wave A routes register as native routes from navigation payload', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: WAVE_A_ROUTES.map((route, index) => ({
          route,
          name: route,
          status: 'released',
          order: index + 1,
        })),
      },
    ],
    { isAdmin: false },
  );

  assert.equal(state.dynamicRoutes.length, WAVE_A_ROUTES.length);
  assert.deepEqual(state.diagnostics.missingContractRoutes, []);
  assert.deepEqual(
    state.dynamicRoutes.map((entry) => entry.renderMode),
    Array(WAVE_A_ROUTES.length).fill('native'),
  );
});

test('Wave A deep links preserve query string in shell runtime paths', () => {
  const sampleDeepLinks = [
    '/wip-overview?workorder=AA001&status=all',
    '/wip-detail?workcenter=WB12&lotid=L01',
    '/hold-overview?hold_type=quality&reason=QC',
    '/hold-detail?reason=QC&workcenter=WB12',
    '/hold-history?start_date=2026-02-01&end_date=2026-02-11&record_type=new,release',
    '/resource-history?start_date=2026-02-01&end_date=2026-02-11&granularity=day',
  ];

  sampleDeepLinks.forEach((routePath) => {
    assert.equal(
      toRuntimeRoute(routePath, { currentPathname: '/portal-shell/wip-overview' }),
      `/portal-shell${routePath}`,
    );
  });
});

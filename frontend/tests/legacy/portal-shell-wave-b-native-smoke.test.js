import test from 'node:test';
import assert from 'node:assert/strict';

import { buildDynamicNavigationState } from '../src/portal-shell/navigationState.js';
import { buildLaunchHref } from '../src/portal-shell/routeQuery.js';
import { getRouteContract } from '../src/portal-shell/routeContracts.js';

const WAVE_B_NATIVE_CASES = Object.freeze([
  {
    route: '/job-query',
    page: '設備維修查詢',
    query: {
      start_date: '2026-02-01',
      end_date: '2026-02-11',
      resource_ids: ['EQ-01', 'EQ-02'],
    },
    expectedParams: ['start_date=2026-02-01', 'end_date=2026-02-11', 'resource_ids=EQ-01', 'resource_ids=EQ-02'],
  },
  {
    route: '/query-tool',
    page: 'Query Tool',
    query: {
      input_type: 'lot_id',
      values: ['GA23100020-A00-001'],
    },
    expectedParams: ['input_type=lot_id', 'values=GA23100020-A00-001'],
  },
]);

test('Wave B routes use native mode after rewrite cutover', () => {
  WAVE_B_NATIVE_CASES.forEach(({ route }) => {
    const contract = getRouteContract(route);
    assert.ok(contract, `missing contract for ${route}`);
    assert.equal(contract.renderMode, 'native', `expected native mode for ${route}`);
    assert.equal(contract.rollbackStrategy, 'fallback_to_legacy_route');
  });
});

test('Wave B shell launch href keeps workflow query context', () => {
  WAVE_B_NATIVE_CASES.forEach(({ route, query, expectedParams }) => {
    const href = buildLaunchHref(route, query);
    assert.ok(href.startsWith(route), `unexpected href path for ${route}: ${href}`);
    expectedParams.forEach((token) => {
      assert.ok(href.includes(token), `missing query token ${token} in ${href}`);
    });
  });
});

test('Wave B routes are registered as native targets from navigation payload', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'native-tools',
        name: 'Native Tools',
        order: 1,
        pages: WAVE_B_NATIVE_CASES.map((entry, index) => ({
          route: entry.route,
          name: entry.page,
          status: 'released',
          order: index + 1,
        })),
      },
    ],
    { isAdmin: true },
  );

  assert.equal(state.dynamicRoutes.length, WAVE_B_NATIVE_CASES.length);
  state.dynamicRoutes.forEach((entry) => {
    assert.equal(entry.renderMode, 'native');
  });
});

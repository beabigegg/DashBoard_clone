import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDynamicNavigationState,
  normalizeNavigationDrawers,
} from '../src/portal-shell/navigationState.js';


test('normalizeNavigationDrawers enforces deterministic order and visibility', () => {
  const input = [
    {
      id: 'dev-tools',
      name: 'Dev',
      order: 3,
      admin_only: true,
      pages: [{ route: '/admin/pages', name: 'Admin Pages', status: 'dev', order: 2 }],
    },
    {
      id: 'reports',
      name: 'Reports',
      order: 1,
      admin_only: false,
      pages: [
        { route: '/wip-overview', name: 'WIP', status: 'released', order: 2 },
        { route: '/hold-overview', name: 'Hold', status: 'dev', order: 1 },
      ],
    },
  ];

  const nonAdmin = normalizeNavigationDrawers(input, { isAdmin: false });
  assert.deepEqual(nonAdmin.map((d) => d.id), ['reports']);
  assert.deepEqual(nonAdmin[0].pages.map((p) => p.route), ['/wip-overview']);

  const admin = normalizeNavigationDrawers(input, { isAdmin: true });
  assert.deepEqual(admin.map((d) => d.id), ['reports', 'dev-tools']);
  assert.deepEqual(admin[0].pages.map((p) => p.route), ['/hold-overview', '/wip-overview']);
});


test('buildDynamicNavigationState resolves render mode via route contract', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/wip-overview', name: 'WIP', status: 'released', order: 1 }],
      },
      {
        id: 'tools',
        name: 'Tools',
        order: 2,
        pages: [{ route: '/job-query', name: 'Job Query', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: true },
  );

  const renderModes = Object.fromEntries(
    state.dynamicRoutes.map((route) => [route.targetRoute, route.renderMode]),
  );
  assert.equal(renderModes['/wip-overview'], 'native');
  assert.equal(renderModes['/job-query'], 'native');
  assert.equal(state.diagnostics.missingContractRoutes.length, 0);
});


test('buildDynamicNavigationState tracks routes missing from contract and keeps native fallback mode', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/legacy-unknown', name: 'Legacy', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: false },
  );

  assert.deepEqual(state.diagnostics.missingContractRoutes, ['/legacy-unknown']);
  assert.equal(state.dynamicRoutes[0].renderMode, 'native');
  assert.deepEqual(state.allowedPaths.sort(), ['/', '/legacy-unknown']);
});


test('buildDynamicNavigationState can include standalone drilldown routes without drawer entries', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'reports',
        name: 'Reports',
        order: 1,
        pages: [{ route: '/wip-overview', name: 'WIP', status: 'released', order: 1 }],
      },
    ],
    { isAdmin: false, includeStandaloneDrilldown: true },
  );

  const targetRoutes = state.dynamicRoutes.map((route) => route.targetRoute);
  assert.equal(targetRoutes.includes('/wip-overview'), true);
  assert.equal(targetRoutes.includes('/wip-detail'), true);
  assert.equal(targetRoutes.includes('/hold-detail'), true);
  assert.equal(state.allowedPaths.includes('/wip-detail'), true);
  assert.equal(state.allowedPaths.includes('/hold-detail'), true);
});


test('buildDynamicNavigationState keeps admin routes as governed external targets', () => {
  const state = buildDynamicNavigationState(
    [
      {
        id: 'dev-tools',
        name: 'Dev',
        order: 1,
        admin_only: true,
        pages: [{ route: '/admin/pages', name: 'Admin Pages', status: 'dev', order: 1 }],
      },
    ],
    { isAdmin: true },
  );

  assert.equal(state.diagnostics.missingContractRoutes.length, 0);
  assert.equal(state.dynamicRoutes.length, 1);
  assert.equal(state.dynamicRoutes[0].targetRoute, '/admin/pages');
  assert.equal(state.dynamicRoutes[0].renderMode, 'external');
  assert.equal(state.dynamicRoutes[0].visibilityPolicy, 'admin_only');
  assert.equal(state.dynamicRoutes[0].scope, 'in-scope');
});

import test from 'node:test';
import assert from 'node:assert/strict';

import { getNativeModuleLoader } from '../src/portal-shell/nativeModuleRegistry.js';
import { buildLaunchHref } from '../src/portal-shell/routeQuery.js';
import { getRouteContract } from '../src/portal-shell/routeContracts.js';


test('yield-alert-center route contract is native and has loader', () => {
  const contract = getRouteContract('/yield-alert-center');
  assert.ok(contract);
  assert.equal(contract.renderMode, 'native');
  assert.equal(typeof getNativeModuleLoader('/yield-alert-center'), 'function');
});


test('yield-alert-center launch href preserves query', () => {
  const href = buildLaunchHref('/yield-alert-center', {
    start_date: '2026-03-01',
    end_date: '2026-03-06',
    departments: ['WB01'],
  });
  assert.ok(href.startsWith('/yield-alert-center?'));
  assert.ok(href.includes('start_date=2026-03-01'));
  assert.ok(href.includes('departments=WB01'));
});

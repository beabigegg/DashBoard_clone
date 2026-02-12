import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  getDeferredRoutes,
  getInScopeRoutes,
  getRouteContract,
  getKnownRoutes,
  validateRouteContractMap,
} from '../src/portal-shell/routeContracts.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendContractPath = path.resolve(
  __dirname,
  '../../docs/migration/full-modernization-architecture-blueprint/route_contracts.json',
);


test('in-scope route contracts satisfy governance metadata requirements', () => {
  const errors = validateRouteContractMap({ inScopeOnly: true });
  assert.deepEqual(errors, []);
});


test('admin shell targets are governed and rendered as external targets', () => {
  const pagesContract = getRouteContract('/admin/pages');
  const perfContract = getRouteContract('/admin/performance');

  assert.equal(pagesContract.scope, 'in-scope');
  assert.equal(perfContract.scope, 'in-scope');
  assert.equal(pagesContract.visibilityPolicy, 'admin_only');
  assert.equal(perfContract.visibilityPolicy, 'admin_only');
  assert.equal(pagesContract.renderMode, 'external');
  assert.equal(perfContract.renderMode, 'external');
});


test('deferred routes stay discoverable but are separable from in-scope gates', () => {
  const inScope = new Set(getInScopeRoutes());
  const deferred = getDeferredRoutes();

  deferred.forEach((route) => {
    assert.equal(inScope.has(route), false, `deferred route leaked into in-scope: ${route}`);
    const contract = getRouteContract(route);
    assert.equal(contract.scope, 'deferred');
  });
});


test('known route inventory covers in-scope + deferred surfaces', () => {
  const known = new Set(getKnownRoutes());
  [...getInScopeRoutes(), ...getDeferredRoutes()].forEach((route) => {
    assert.equal(known.has(route), true, `missing known route: ${route}`);
  });
});


test('frontend route inventory stays aligned with backend route contracts', () => {
  const backendPayload = JSON.parse(fs.readFileSync(backendContractPath, 'utf-8'));
  const backendRoutes = new Map(
    (backendPayload.routes || []).map((route) => [route.route, route.scope]),
  );
  const frontendRoutes = getKnownRoutes();

  assert.deepEqual(
    [...new Set(frontendRoutes)].sort(),
    [...backendRoutes.keys()].sort(),
    'route set drift between frontend routeContracts.js and backend route_contracts.json',
  );

  frontendRoutes.forEach((route) => {
    const frontendScope = getRouteContract(route).scope;
    const backendScope = backendRoutes.get(route);
    assert.equal(
      frontendScope,
      backendScope,
      `scope mismatch for ${route}: frontend=${frontendScope}, backend=${backendScope}`,
    );
  });
});

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isPortalShellRuntime,
  navigateToRuntimeRoute,
  toRuntimeRoute,
} from '../src/core/shell-navigation.js';


test('isPortalShellRuntime detects portal-shell path prefix', () => {
  assert.equal(isPortalShellRuntime('/portal-shell'), true);
  assert.equal(isPortalShellRuntime('/portal-shell/wip-overview'), true);
  assert.equal(isPortalShellRuntime('/wip-overview'), false);
});


test('toRuntimeRoute keeps legacy route outside shell runtime', () => {
  assert.equal(
    toRuntimeRoute('/wip-overview?status=run', { currentPathname: '/wip-overview' }),
    '/wip-overview?status=run',
  );
});


test('toRuntimeRoute prefixes target route inside shell runtime', () => {
  assert.equal(
    toRuntimeRoute('/wip-overview?status=run', { currentPathname: '/portal-shell/wip-overview' }),
    '/portal-shell/wip-overview?status=run',
  );
});


test('toRuntimeRoute avoids double-prefix for already-prefixed path', () => {
  assert.equal(
    toRuntimeRoute('/portal-shell/wip-overview', { currentPathname: '/portal-shell' }),
    '/portal-shell/wip-overview',
  );
});


test('navigateToRuntimeRoute uses shell router bridge in portal runtime', () => {
  const originalWindow = globalThis.window;
  const calls = [];

  globalThis.window = {
    location: {
      pathname: '/portal-shell/wip-overview',
      href: '/portal-shell/wip-overview',
      replace: (value) => calls.push({ kind: 'replace-location', value }),
    },
    __MES_PORTAL_SHELL_NAVIGATE__: (target, options) => {
      calls.push({ kind: 'bridge', target, options });
    },
  };

  navigateToRuntimeRoute('/wip-detail?workcenter=WB12');

  assert.deepEqual(calls, [
    {
      kind: 'bridge',
      target: '/wip-detail?workcenter=WB12',
      options: { replace: false },
    },
  ]);

  globalThis.window = originalWindow;
});


test('navigateToRuntimeRoute falls back to location when bridge is unavailable', () => {
  const originalWindow = globalThis.window;
  const calls = [];

  globalThis.window = {
    location: {
      pathname: '/wip-overview',
      href: '/wip-overview',
      replace: (value) => calls.push({ kind: 'replace-location', value }),
    },
  };

  navigateToRuntimeRoute('/wip-detail?workcenter=WB12');

  assert.equal(globalThis.window.location.href, '/wip-detail?workcenter=WB12');
  assert.deepEqual(calls, []);

  globalThis.window = originalWindow;
});

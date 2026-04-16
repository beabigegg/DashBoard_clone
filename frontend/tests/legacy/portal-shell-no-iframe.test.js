import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  const directPath = resolve(process.cwd(), relativePath);
  if (existsSync(directPath)) {
    return readFileSync(directPath, 'utf8');
  }
  return readFileSync(resolve(process.cwd(), 'frontend', relativePath), 'utf8');
}

test('shell route host sources do not contain iframe rendering paths', () => {
  const files = [
    'src/portal-shell/App.vue',
    'src/portal-shell/views/NativeRouteView.vue',
    'src/portal-shell/router.js',
    'src/portal-shell/navigationState.js',
  ];

  files.forEach((filePath) => {
    const source = readSource(filePath).toLowerCase();
    assert.doesNotMatch(source, /<iframe/);
  });
});

test('page bridge host is removed after native route-view decommission', () => {
  const routerSource = readSource('src/portal-shell/router.js');
  assert.doesNotMatch(routerSource, /PageBridgeView/);

  const appPySource = readSource('../src/mes_dashboard/app.py');
  assert.doesNotMatch(appPySource, /\/api\/portal\/wrapper-telemetry/);
});

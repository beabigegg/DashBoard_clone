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

test('portal shell app renders health summary component and admin entry controls', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /import HealthStatus from '\.\/components\/HealthStatus\.vue';/);
  assert.match(source, /<HealthStatus \/>/);

  assert.match(source, /管理後台/);
  assert.match(source, /管理員登入/);
  assert.match(source, /登出/);
  assert.match(source, /adminLinks\?\.pages/);
});

test('portal shell app keeps fallback notice and route sync wiring', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.doesNotMatch(source, /class="mode-badge"/);
  assert.match(source, /consumeNavigationNotice/);
  // nav-config-to-code: App.vue now passes statusMap (from payload.statuses) not payload.drawers
  assert.match(source, /syncNavigationRoutes\(statusMap/);
});

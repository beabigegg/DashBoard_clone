import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  buildHealthFallbackDetail,
  labelFromHealthStatus,
  normalizeFrontendShellHealth,
} from '../src/portal-shell/healthSummary.js';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}


test('labelFromHealthStatus maps healthy/degraded/unhealthy states', () => {
  assert.equal(labelFromHealthStatus('healthy'), '連線正常');
  assert.equal(labelFromHealthStatus('degraded'), '部分降級');
  assert.equal(labelFromHealthStatus('unhealthy'), '連線異常');
});


test('normalizeFrontendShellHealth reads summary/detail contract', () => {
  const normalized = normalizeFrontendShellHealth({
    summary: { status: 'healthy' },
    detail: { errors: ['none'] },
  });

  assert.equal(normalized.status, 'healthy');
  assert.deepEqual(normalized.errors, ['none']);
});


test('normalizeFrontendShellHealth supports legacy flat payload shape', () => {
  const normalized = normalizeFrontendShellHealth({
    status: 'degraded',
    errors: ['asset missing'],
  });

  assert.equal(normalized.status, 'degraded');
  assert.deepEqual(normalized.errors, ['asset missing']);
});


test('buildHealthFallbackDetail returns deterministic fallback contract', () => {
  const fallback = buildHealthFallbackDetail();
  assert.equal(fallback.status, 'unhealthy');
  assert.equal(fallback.label, '無法連線');
  assert.equal(fallback.detail.database, '無法確認');
  assert.equal(fallback.detail.routeCacheMode, '--');
});


test('HealthStatus component keeps summary-first trigger and detail panel interactions', () => {
  const source = readSource('src/portal-shell/components/HealthStatus.vue');

  assert.match(source, /class=\"health-trigger\"/);
  assert.match(source, /meta-toggle\">詳情/);
  assert.match(source, /v-if=\"popupOpen\"/);

  // Close-on-outside-click and ESC behavior remain part of the UX contract.
  assert.match(source, /document\.addEventListener\('click', onDocumentClick\)/);
  assert.match(source, /document\.addEventListener\('keydown', onDocumentKeydown\)/);
  assert.match(source, /event\.key === 'Escape'/);
});

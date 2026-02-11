import test from 'node:test';
import assert from 'node:assert/strict';

import { buildLaunchHref } from '../src/portal-shell/routeQuery.js';

test('buildLaunchHref keeps base target route without query payload', () => {
  assert.equal(buildLaunchHref('/job-query'), '/job-query');
});

test('buildLaunchHref appends scalar query values', () => {
  assert.equal(
    buildLaunchHref('/job-query', { q: 'ABCD', page: '2' }),
    '/job-query?q=ABCD&page=2',
  );
});

test('buildLaunchHref supports repeated query keys from array values', () => {
  assert.equal(
    buildLaunchHref('/excel-query', { lotid: ['L1', 'L2'], mode: 'upload' }),
    '/excel-query?lotid=L1&lotid=L2&mode=upload',
  );
});

test('buildLaunchHref replaces existing query keys with latest runtime values', () => {
  assert.equal(
    buildLaunchHref('/query-tool?mode=legacy&page=1', { mode: 'runtime', page: '3' }),
    '/query-tool?mode=runtime&page=3',
  );
});

test('buildLaunchHref ignores empty and null-like query values', () => {
  assert.equal(
    buildLaunchHref('/tmtt-defect', { start_date: '', end_date: null, shift: undefined }),
    '/tmtt-defect',
  );
});

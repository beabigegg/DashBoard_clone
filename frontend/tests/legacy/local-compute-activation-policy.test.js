/**
 * Tests for DuckDB local-compute activation policy.
 * Task 5.3 — Verifies that local mode suppresses /view requests when active
 * and that the activation policy gates correctly.
 *
 * Note:
 * `duckdb-activation-policy.js` statically imports `duckdb-client.js`, which in
 * turn imports a Vite worker (`?worker`) that Node's native test runner cannot
 * load. To keep this test runnable under `node --test`, we load the original
 * policy source and replace that single import with a controllable stub.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

globalThis.__testDuckdbSupport = () => true;

const policyPath = new URL('../../src/core/duckdb-activation-policy.js', import.meta.url);
const policySource = await readFile(policyPath, 'utf8');
const transformedSource = policySource.replace(
  "import { isDuckDBSupported } from './duckdb-client.js';",
  "const isDuckDBSupported = () => globalThis.__testDuckdbSupport();",
);
const policyModuleUrl = `data:text/javascript;base64,${Buffer.from(transformedSource, 'utf8').toString('base64')}`;
const { checkLocalComputeEligibility } = await import(policyModuleUrl);

function withDuckdbSupport(supported, fn) {
  const previous = globalThis.__testDuckdbSupport;
  globalThis.__testDuckdbSupport = () => supported;
  try {
    return fn();
  } finally {
    globalThis.__testDuckdbSupport = previous;
  }
}

test('checkLocalComputeEligibility returns eligible=true when all conditions met', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
      threshold: 5000,
      flagEnabled: true,
    });
    assert.equal(result.eligible, true);
    assert.equal(result.reason, 'ok');
  });
});

test('checkLocalComputeEligibility returns eligible=false when flag is disabled', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
      flagEnabled: false,
    });
    assert.equal(result.eligible, false);
    assert.equal(result.reason, 'flag_disabled');
  });
});

test('checkLocalComputeEligibility returns eligible=false when browser does not support DuckDB', () => {
  withDuckdbSupport(false, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 10000,
    });
    assert.equal(result.eligible, false);
    assert.equal(result.reason, 'browser_unsupported');
  });
});

test('checkLocalComputeEligibility returns eligible=false when spool_download_url is absent', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: null,
      totalRowCount: 10000,
    });
    assert.equal(result.eligible, false);
    assert.equal(result.reason, 'no_spool_url');
  });
});

test('checkLocalComputeEligibility returns eligible=false when row count is below threshold', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/resource_dataset/abc123.parquet',
      totalRowCount: 100,
      threshold: 5000,
    });
    assert.equal(result.eligible, false);
    assert.equal(result.reason, 'below_threshold');
  });
});

test('checkLocalComputeEligibility returns eligible=false when totalRowCount equals threshold - 1', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/hold_dataset/abc.parquet',
      totalRowCount: 4999,
      threshold: 5000,
    });
    assert.equal(result.eligible, false);
  });
});

test('checkLocalComputeEligibility returns eligible=true when totalRowCount exactly equals threshold', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({
      spoolDownloadUrl: '/api/spool/hold_dataset/abc.parquet',
      totalRowCount: 5000,
      threshold: 5000,
    });
    assert.equal(result.eligible, true);
  });
});

test('checkLocalComputeEligibility returns eligible=false for empty opts (no spool url)', () => {
  withDuckdbSupport(true, () => {
    const result = checkLocalComputeEligibility({});
    assert.equal(result.eligible, false);
  });
});

test('local compute contract: eligible response triggers activation path (not server view)', () => {
  withDuckdbSupport(true, () => {
    const queryResponse = {
      query_id: 'abc123',
      spool_download_url: '/api/spool/resource_dataset/abc123.parquet',
      total_row_count: 8000,
      summary: {},
      detail: {},
    };

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: queryResponse.spool_download_url,
      totalRowCount: queryResponse.total_row_count,
    });
    assert.equal(eligible, true);
  });
});

test('local compute contract: ineligible response falls back to server view path', () => {
  withDuckdbSupport(true, () => {
    const queryResponse = {
      query_id: 'small_query',
      total_row_count: 500,
      summary: {},
      detail: {},
    };

    const { eligible } = checkLocalComputeEligibility({
      spoolDownloadUrl: queryResponse.spool_download_url,
      totalRowCount: queryResponse.total_row_count,
    });
    assert.equal(eligible, false);
  });
});

test('local compute contract: resource history and hold history use same threshold default (5000)', () => {
  withDuckdbSupport(true, () => {
    const baseOpts = {
      spoolDownloadUrl: '/api/spool/x/y.parquet',
    };
    assert.equal(checkLocalComputeEligibility({ ...baseOpts, totalRowCount: 5000 }).eligible, true);
    assert.equal(checkLocalComputeEligibility({ ...baseOpts, totalRowCount: 4999 }).eligible, false);
  });
});

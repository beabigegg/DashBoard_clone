/**
 * Loading Standardization Governance Tests
 *
 * Verifies that the three-tier loading architecture is correctly implemented:
 * - Page-level: LoadingOverlay tier="page"
 * - Component-level: LoadingSpinner + is-loading pattern
 * - Block-level: BlockLoadingState or DataTable :loading
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const srcDir = resolve(import.meta.dirname, '../../src');

function readSrc(relPath) {
  return readFileSync(resolve(srcDir, relPath), 'utf8');
}

// ── 1. Shared Component Baseline ─────────────────────────────────────────────

test('LoadingSpinner has reduced-motion media query', () => {
  const content = readSrc('shared-ui/components/LoadingSpinner.vue');
  assert.ok(
    content.includes('prefers-reduced-motion'),
    'LoadingSpinner.vue must contain @media (prefers-reduced-motion: reduce)',
  );
});

test('LoadingSpinner sizes are sm/md/lg', () => {
  const content = readSrc('shared-ui/components/LoadingSpinner.vue');
  assert.ok(content.includes("'sm'"), 'LoadingSpinner must support size="sm"');
  assert.ok(content.includes("'md'"), 'LoadingSpinner must support size="md"');
  assert.ok(content.includes("'lg'"), 'LoadingSpinner must support size="lg"');
});

test('LoadingOverlay supports page and section tiers', () => {
  const content = readSrc('shared-ui/components/LoadingOverlay.vue');
  assert.ok(content.includes("'page'"), 'LoadingOverlay must support tier="page"');
  assert.ok(content.includes("'section'"), 'LoadingOverlay must support tier="section"');
});

test('BlockLoadingState component exists and uses LoadingSpinner', () => {
  const content = readSrc('shared-ui/components/BlockLoadingState.vue');
  assert.ok(
    content.includes('LoadingSpinner'),
    'BlockLoadingState must use LoadingSpinner component',
  );
});

// ── 2. MultiSelect uses shared spinner ───────────────────────────────────────

test('MultiSelect does not define custom ms-spin keyframe', () => {
  const content = readSrc('shared-ui/components/MultiSelect.vue');
  assert.ok(
    !content.includes('@keyframes ms-spin'),
    'MultiSelect must not define @keyframes ms-spin (use shared LoadingSpinner instead)',
  );
});

test('MultiSelect uses LoadingSpinner for loading state', () => {
  const content = readSrc('shared-ui/components/MultiSelect.vue');
  assert.ok(
    content.includes('LoadingSpinner'),
    'MultiSelect must import and use LoadingSpinner component',
  );
});

test('MultiSelect has reduced-motion support', () => {
  const content = readSrc('shared-ui/components/MultiSelect.vue');
  assert.ok(
    content.includes('prefers-reduced-motion'),
    'MultiSelect must contain @media (prefers-reduced-motion: reduce)',
  );
});

// ── 3. No page-level custom spinner CSS in feature files ─────────────────────

test('anomaly-overview style.css has no custom ao-spinner or ao-spin keyframe', () => {
  const content = readSrc('anomaly-overview/style.css');
  assert.ok(
    !content.includes('.ao-spinner'),
    'anomaly-overview/style.css must not define .ao-spinner (use shared LoadingSpinner)',
  );
  assert.ok(
    !content.includes('@keyframes ao-spin'),
    'anomaly-overview/style.css must not define @keyframes ao-spin',
  );
});

test('material-trace style.css has no custom btn-spinner', () => {
  const content = readSrc('material-trace/style.css');
  assert.ok(
    !content.includes('.btn-spinner'),
    'material-trace/style.css must not define .btn-spinner (use shared LoadingSpinner)',
  );
});

test('reject-history style.css has no custom table-spinner', () => {
  const content = readSrc('reject-history/style.css');
  assert.ok(
    !content.includes('.table-spinner'),
    'reject-history/style.css must not define .table-spinner (use DataTable :loading or BlockLoadingState)',
  );
});

// ── 4. Page-level loading uses shared overlay ────────────────────────────────

test('qc-gate App.vue uses LoadingOverlay for initial loading', () => {
  const content = readSrc('qc-gate/App.vue');
  assert.ok(
    content.includes("LoadingOverlay") && content.includes('tier="page"'),
    'qc-gate/App.vue must use LoadingOverlay with tier="page" for initial loading state',
  );
});

test('qc-gate App.vue has no text-only loading-state div', () => {
  const content = readSrc('qc-gate/App.vue');
  assert.ok(
    !content.includes('class="loading-state"'),
    'qc-gate/App.vue must not use text-only .loading-state div (use LoadingOverlay)',
  );
});

test('anomaly-overview App.vue uses LoadingOverlay for initial load', () => {
  const content = readSrc('anomaly-overview/App.vue');
  assert.ok(
    content.includes('LoadingOverlay') && content.includes('pageLoading'),
    'anomaly-overview/App.vue must use LoadingOverlay with pageLoading for initial load',
  );
});

// ── 5. Button loading uses shared pattern ────────────────────────────────────

test('ExportButton uses LoadingSpinner when loading', () => {
  const content = readSrc('query-tool/components/ExportButton.vue');
  assert.ok(
    content.includes('LoadingSpinner'),
    'ExportButton.vue must use LoadingSpinner in loading state',
  );
  assert.ok(
    content.includes('is-loading'),
    'ExportButton.vue must apply is-loading class when loading',
  );
});

test('material-trace App.vue uses LoadingSpinner in query button', () => {
  const content = readSrc('material-trace/App.vue');
  assert.ok(
    content.includes('LoadingSpinner'),
    'material-trace/App.vue must use LoadingSpinner in query button',
  );
  assert.ok(
    !content.includes('btn-spinner'),
    'material-trace/App.vue must not use custom .btn-spinner class',
  );
});

// ── 6. DataTable loading consistency ─────────────────────────────────────────

test('DataTable supports :loading prop with opacity transition', () => {
  const content = readSrc('shared-ui/components/DataTable.vue');
  assert.ok(
    content.includes('is-loading'),
    'DataTable must apply is-loading class when loading prop is true',
  );
  assert.ok(
    content.includes('opacity'),
    'DataTable loading state must use opacity transition',
  );
});

test('admin LogsTab passes :loading to DataTable', () => {
  const content = readSrc('admin-dashboard/tabs/LogsTab.vue');
  assert.ok(
    content.includes(':loading="logsLoading"'),
    'admin LogsTab must pass :loading to DataTable',
  );
});

// ── 7. query-tool components use BlockLoadingState ────────────────────────────

test('LotHistoryTable uses BlockLoadingState instead of placeholder div', () => {
  const content = readSrc('query-tool/components/LotHistoryTable.vue');
  assert.ok(
    content.includes('BlockLoadingState'),
    'LotHistoryTable must use BlockLoadingState for loading state',
  );
  assert.ok(
    !content.includes('<div v-if="loading" class="placeholder">'),
    'LotHistoryTable must not use text-only placeholder div for loading',
  );
});

test('LotAssociationTable uses BlockLoadingState instead of placeholder div', () => {
  const content = readSrc('query-tool/components/LotAssociationTable.vue');
  assert.ok(
    content.includes('BlockLoadingState'),
    'LotAssociationTable must use BlockLoadingState for loading state',
  );
});

test('LotRejectTable uses BlockLoadingState instead of placeholder div', () => {
  const content = readSrc('query-tool/components/LotRejectTable.vue');
  assert.ok(
    content.includes('BlockLoadingState'),
    'LotRejectTable must use BlockLoadingState for loading state',
  );
});

test('LotJobsTable uses BlockLoadingState instead of placeholder div', () => {
  const content = readSrc('query-tool/components/LotJobsTable.vue');
  assert.ok(
    content.includes('BlockLoadingState'),
    'LotJobsTable must use BlockLoadingState for loading state',
  );
});

// ── 9. wip-detail uses shared spinner ────────────────────────────────────────

test('LotDetailPanel uses LoadingSpinner instead of custom loading-spinner span', () => {
  const content = readSrc('wip-detail/components/LotDetailPanel.vue');
  assert.ok(
    content.includes('LoadingSpinner'),
    'LotDetailPanel must use LoadingSpinner component',
  );
  assert.ok(
    !content.includes('<span class="loading-spinner">'),
    'LotDetailPanel must not use custom .loading-spinner span',
  );
});

test('wip-shared styles.css has no orphaned .loading-spinner in reduced-motion', () => {
  const content = readSrc('wip-shared/styles.css');
  assert.ok(
    !content.includes('.loading-spinner'),
    'wip-shared/styles.css must not reference .loading-spinner (use LoadingSpinner component)',
  );
});

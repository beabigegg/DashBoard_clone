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

test('shell route view uses direct RouterView host (no transition blank-state)', () => {
  const appSource = readSource('src/portal-shell/App.vue');
  assert.match(appSource, /<RouterView \/>/);
  assert.doesNotMatch(appSource, /<Transition name=\"route-fade\" mode=\"out-in\">/);
});

test('Wave A chart components keep autoresize and tooltip configuration', () => {
  const chartFiles = [
    'src/wip-shared/components/ParetoSection.vue',
    'src/qc-gate/components/QcGateChart.vue',
    'src/hold-history/components/DailyTrend.vue',
    'src/hold-history/components/ReasonPareto.vue',
    'src/hold-history/components/DurationChart.vue',
    'src/resource-history/components/TrendChart.vue',
    'src/resource-history/components/StackedChart.vue',
    'src/resource-history/components/HeatmapChart.vue',
    'src/resource-history/components/ComparisonChart.vue',
  ];

  chartFiles.forEach((filePath) => {
    const source = readSource(filePath);
    assert.match(source, /tooltip\s*:/, `missing tooltip config: ${filePath}`);
    assert.match(source, /autoresize/, `missing autoresize lifecycle hook: ${filePath}`);
  });
});

test('QC Gate keeps linked chart-table interaction guards', () => {
  const source = readSource('src/qc-gate/App.vue');
  assert.match(source, /const activeFilter = ref/);
  assert.match(source, /const filteredLots = computed\(\(\) =>/);
  assert.match(source, /function handleChartSelect\(filter/);
  assert.match(source, /activeFilter\.value = null/);
});

test('resource tooltip lifecycle keeps keydown listener cleanup', () => {
  const source = readSource('src/resource-status/components/FloatingTooltip.vue');
  assert.match(source, /document\.addEventListener\('keydown', handleEscapeKey\)/);
  assert.match(source, /document\.removeEventListener\('keydown', handleEscapeKey\)/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('table parity: Wave B native pages keep deterministic column and empty-state handling', () => {
  const jobSource = readSource('src/job-query/App.vue');
  assert.match(jobSource, /jobsColumns/);
  assert.match(jobSource, /txnColumns/);
  assert.match(jobSource, /目前無資料/);

  const excelSource = readSource('src/excel-query/App.vue');
  assert.match(excelSource, /queryResult\.columns/);
  assert.match(excelSource, /queryResult\.rows\.length === 0/);

  const queryToolSource = readSource('src/query-tool/App.vue');
  assert.match(queryToolSource, /resolvedColumns/);
  assert.match(queryToolSource, /historyColumns/);
  assert.match(queryToolSource, /associationColumns/);
  assert.match(queryToolSource, /equipmentColumns/);
});

test('table parity: list/detail pages preserve pagination and sort continuity hooks', () => {
  const wipDetailSource = readSource('src/wip-detail/App.vue');
  assert.match(wipDetailSource, /const page = ref\(1\)/);
  assert.match(wipDetailSource, /page_size|pageSize/);

  const holdDetailSource = readSource('src/hold-detail/App.vue');
  assert.match(holdDetailSource, /page|currentPage|perPage/);
  assert.match(holdDetailSource, /distribution|lots/i);

  const tmttTableSource = readSource('src/tmtt-defect/components/TmttDetailTable.vue');
  assert.match(tmttTableSource, /sort/i);
});

test('chart parity: chart pages keep tooltip, legend, autoresize and click linkage', () => {
  const qcChartSource = readSource('src/qc-gate/components/QcGateChart.vue');
  assert.match(qcChartSource, /tooltip\s*:/);
  assert.match(qcChartSource, /legend\s*:/);
  assert.match(qcChartSource, /autoresize/);
  assert.match(qcChartSource, /@click="handleChartClick"/);

  const holdParetoSource = readSource('src/hold-history/components/ReasonPareto.vue');
  assert.match(holdParetoSource, /tooltip\s*:/);
  assert.match(holdParetoSource, /legend\s*:/);
  assert.match(holdParetoSource, /@click="handleChartClick"/);

  const tmttChartSource = readSource('src/tmtt-defect/components/TmttChartCard.vue');
  assert.match(tmttChartSource, /tooltip\s*:/);
  assert.match(tmttChartSource, /legend\s*:/);
  assert.match(tmttChartSource, /autoresize/);
});

test('matrix interaction parity: selection/highlight/drill handlers remain present', () => {
  const wipMatrixSource = readSource('src/wip-overview/components/MatrixTable.vue');
  assert.match(wipMatrixSource, /emit\('drilldown'/);

  const holdMatrixSource = readSource('src/hold-overview/components/HoldMatrix.vue');
  assert.match(holdMatrixSource, /emit\('select'/);
  assert.match(holdMatrixSource, /isCellActive|isRowActive|isColumnActive/);

  const resourceMatrixSource = readSource('src/resource-status/components/MatrixSection.vue');
  assert.match(resourceMatrixSource, /cell-filter/);
  assert.match(resourceMatrixSource, /selectedColumns/);
  assert.match(resourceMatrixSource, /toggle-all/);
});

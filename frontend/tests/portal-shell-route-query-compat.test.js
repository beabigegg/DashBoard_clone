import test from 'node:test';
import assert from 'node:assert/strict';

import { buildLaunchHref } from '../src/portal-shell/routeQuery.js';
import { toRuntimeRoute } from '../src/core/shell-navigation.js';

test('list-detail workflow preserves wip filters across launch href and shell runtime prefix', () => {
  const detailHref = buildLaunchHref('/wip-detail', {
    workcenter: 'WB12',
    workorder: 'WO-001',
    lotid: 'LOT-001',
    status: 'queue',
  });
  assert.equal(
    detailHref,
    '/wip-detail?workcenter=WB12&workorder=WO-001&lotid=LOT-001&status=queue',
  );

  assert.equal(
    toRuntimeRoute(detailHref, { currentPathname: '/portal-shell/wip-overview' }),
    '/portal-shell/wip-detail?workcenter=WB12&workorder=WO-001&lotid=LOT-001&status=queue',
  );
});

test('hold list-detail workflow keeps reason/workcenter/package query continuity', () => {
  const holdDetailHref = buildLaunchHref('/hold-detail', {
    reason: 'YieldLimit',
    workcenter: 'DA',
    package: 'QFN',
    page: '2',
  });

  assert.equal(
    holdDetailHref,
    '/hold-detail?reason=YieldLimit&workcenter=DA&package=QFN&page=2',
  );

  assert.equal(
    toRuntimeRoute(holdDetailHref, { currentPathname: '/portal-shell/hold-overview' }),
    '/portal-shell/hold-detail?reason=YieldLimit&workcenter=DA&package=QFN&page=2',
  );
});

test('resource history multi-value filters remain compatible in shell links', () => {
  const historyHref = buildLaunchHref('/resource-history', {
    start_date: '2026-02-01',
    end_date: '2026-02-11',
    workcenter_groups: ['DB', 'WB'],
    families: ['DIP'],
    resource_ids: ['EQ-01', 'EQ-02'],
    granularity: 'day',
  });

  assert.ok(historyHref.includes('workcenter_groups=DB'));
  assert.ok(historyHref.includes('workcenter_groups=WB'));
  assert.ok(historyHref.includes('resource_ids=EQ-01'));
  assert.ok(historyHref.includes('resource_ids=EQ-02'));

  assert.equal(
    toRuntimeRoute(historyHref, { currentPathname: '/portal-shell/resource' }),
    `/portal-shell${historyHref}`,
  );
});

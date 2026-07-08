/**
 * AC-4 data-boundary test: static assertion that
 * `admin-dashboard/style.css` contains `.theme-admin-dashboard`-scoped rules
 * for every class the relocated TargetPermissionsPanel.vue renders.
 *
 * This is the deterministic guard against a missed/renamed class copy when
 * the panel moved from admin-pages → admin-dashboard
 * (specs/changes/move-target-permissions-panel/implementation-plan.md
 * DECISION-3). It must assert the panel-exclusive `.pa-perm-*` names, NOT the
 * original generic admin-pages class list (`.table-container`/`.status-badge`
 * etc.), since those already exist in admin-dashboard/style.css with a
 * DIFFERENT definition for RecentSessionsTable.vue (usage tab).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const styleCssPath = resolve(import.meta.dirname, '../../src/admin-dashboard/style.css');
const styleCss = readFileSync(styleCssPath, 'utf8');

const EXPECTED_PA_PERM_CLASSES = [
  '.pa-perm-table-container',
  '.pa-perm-table',
  '.pa-perm-user-cell',
  '.pa-perm-badge',
  '.pa-perm-badge--granted',
  '.pa-perm-badge--revoked',
  '.pa-perm-empty',
  '.pa-perm-add-row',
  '.pa-perm-add-input',
];

for (const cls of EXPECTED_PA_PERM_CLASSES) {
  test(`admin-dashboard/style.css has a .theme-admin-dashboard-scoped rule for ${cls}`, () => {
    const scoped = `.theme-admin-dashboard ${cls}`;
    assert.ok(
      styleCss.includes(scoped),
      `Expected to find "${scoped}" in admin-dashboard/style.css`,
    );
  });
}

test('admin-dashboard/style.css does not redefine bare table/.status-badge for the permission panel (DECISION-3)', () => {
  // The generic .status-badge/table rules that already exist in this file
  // belong to RecentSessionsTable.vue (usage tab) with a different
  // definition — the permission panel must use its own .pa-perm-* names
  // instead of colliding with them.
  const statusBadgeOccurrences = (styleCss.match(/\.theme-admin-dashboard \.status-badge\b/g) || []).length;
  assert.equal(
    statusBadgeOccurrences,
    1,
    'Expected exactly one .theme-admin-dashboard .status-badge rule (RecentSessionsTable.vue); ' +
    'a second definition would indicate the permission panel classes were copied without renaming',
  );
});

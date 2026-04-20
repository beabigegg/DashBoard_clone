import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  SIDEBAR_STORAGE_KEY,
  buildSidebarUiState,
  parseSidebarCollapsedPreference,
  serializeSidebarCollapsedPreference,
} from '../../src/portal-shell/sidebarState.js';

function readSource(relativePath) {
  const directPath = resolve(process.cwd(), relativePath);
  if (existsSync(directPath)) {
    return readFileSync(directPath, 'utf8');
  }
  return readFileSync(resolve(process.cwd(), 'frontend', relativePath), 'utf8');
}

test('buildSidebarUiState marks desktop collapse correctly', () => {
  const expanded = buildSidebarUiState({
    isMobile: false,
    sidebarCollapsed: false,
    sidebarMobileOpen: false,
  });
  assert.equal(expanded.sidebarClass['sidebar--collapsed'], false);
  assert.equal(expanded.ariaExpanded, 'true');

  const collapsed = buildSidebarUiState({
    isMobile: false,
    sidebarCollapsed: true,
    sidebarMobileOpen: false,
  });
  assert.equal(collapsed.sidebarClass['sidebar--collapsed'], true);
  assert.equal(collapsed.sidebarClass['sidebar--mobile-open'], false);
  assert.equal(collapsed.ariaExpanded, 'false');
});

test('buildSidebarUiState marks mobile overlay states correctly', () => {
  const closed = buildSidebarUiState({
    isMobile: true,
    sidebarCollapsed: true,
    sidebarMobileOpen: false,
  });
  assert.equal(closed.sidebarClass['sidebar--mobile-closed'], true);
  assert.equal(closed.sidebarClass['sidebar--collapsed'], false);
  assert.equal(closed.ariaExpanded, 'false');

  const open = buildSidebarUiState({
    isMobile: true,
    sidebarCollapsed: true,
    sidebarMobileOpen: true,
  });
  assert.equal(open.sidebarClass['sidebar--mobile-open'], true);
  assert.equal(open.sidebarClass['sidebar--mobile-closed'], false);
  assert.equal(open.ariaExpanded, 'true');
});

test('sidebar collapsed preference serializes and parses as expected', () => {
  assert.equal(serializeSidebarCollapsedPreference(true), 'true');
  assert.equal(serializeSidebarCollapsedPreference(false), 'false');
  assert.equal(parseSidebarCollapsedPreference('true'), true);
  assert.equal(parseSidebarCollapsedPreference('false'), false);
  assert.equal(parseSidebarCollapsedPreference(null), false);
});

test('portal shell template uses shell-content and overlay close wiring', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /<section class="shell-content">/);
  assert.doesNotMatch(source, /<section class="content">/);
  assert.match(source, /class="sidebar-overlay"/);
  assert.match(source, /@click="closeMobileSidebar"/);
  assert.match(source, /event\.key === 'Escape'/);
  assert.match(source, /SIDEBAR_STORAGE_KEY/);
});

test('toggleSidebar keeps desktop collapse and persistence wiring', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /function toggleSidebar\(\)/);
  assert.match(source, /sidebarCollapsed\.value = !sidebarCollapsed\.value/);
  assert.match(source, /persistSidebarPreference\(\)/);
});

test('sessionStorage preference restore wiring exists', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /function restoreSidebarPreference\(\)/);
  assert.match(source, /window\.sessionStorage\.getItem\(SIDEBAR_STORAGE_KEY\)/);
});

test('sidebar sessionStorage key remains stable', () => {
  assert.equal(SIDEBAR_STORAGE_KEY, 'portal-shell:sidebar-collapsed');
});

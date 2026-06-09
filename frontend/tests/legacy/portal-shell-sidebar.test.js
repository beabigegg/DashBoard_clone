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

test('buildSidebarUiState closed: sidebar--open absent, ariaExpanded false', () => {
  const state = buildSidebarUiState({ sidebarOpen: false });
  assert.equal(state.sidebarClass['sidebar--open'], false);
  assert.equal(state.sidebarVisible, false);
  assert.equal(state.ariaExpanded, 'false');
});

test('buildSidebarUiState open: sidebar--open present, ariaExpanded true', () => {
  const state = buildSidebarUiState({ sidebarOpen: true });
  assert.equal(state.sidebarClass['sidebar--open'], true);
  assert.equal(state.sidebarVisible, true);
  assert.equal(state.ariaExpanded, 'true');
});

test('buildSidebarUiState shellClass sets sidebar-is-open for scroll lock', () => {
  const closed = buildSidebarUiState({ sidebarOpen: false });
  const open = buildSidebarUiState({ sidebarOpen: true });
  assert.equal(closed.shellClass['sidebar-is-open'], false);
  assert.equal(open.shellClass['sidebar-is-open'], true);
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
  assert.match(source, /@click="closeSidebar"/);
  assert.match(source, /event\.key === 'Escape'/);
});

test('toggleSidebar uses unified sidebarOpen boolean', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /function toggleSidebar\(\)/);
  assert.match(source, /sidebarOpen\.value = !sidebarOpen\.value/);
});

test('closeSidebar sets sidebarOpen to false', () => {
  const source = readSource('src/portal-shell/App.vue');

  assert.match(source, /function closeSidebar\(\)/);
  assert.match(source, /sidebarOpen\.value = false/);
});

test('sidebar sessionStorage key remains stable', () => {
  assert.equal(SIDEBAR_STORAGE_KEY, 'portal-shell:sidebar-collapsed');
});

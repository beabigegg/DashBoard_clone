<script setup lang="ts">
/**
 * Admin pages app — status-toggle only.
 *
 * Navigation structure (drawer assignment, order, display names) is now
 * code-owned by navigationManifest.js. This page manages only the runtime
 * `released` / `dev` status toggle via GET/PUT /admin/api/pages.
 *
 * Display names are joined from the manifest: the backend returns
 * {route, status}; we look up the displayName from the manifest.
 */
import { computed, onMounted, ref } from 'vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import PagesManagementPanel from './components/PagesManagementPanel.vue';
import TargetPermissionsPanel from './components/TargetPermissionsPanel.vue';
import { apiGet } from '../core/api';
import { routes as manifestRoutes, drawers as manifestDrawers } from '../portal-shell/navigationManifest.js';

interface PageStatus {
  route: string;
  status: 'released' | 'dev';
}

interface PageDisplay {
  route: string;
  name: string;
  status: 'released' | 'dev';
}

interface ProductionAchievementPermissionRow {
  user_identifier: string;
  can_edit_targets: boolean;
  granted_at: string;
  granted_by: string;
}

const pages = ref<PageDisplay[]>([]);
const loading = ref(false);
const refreshing = ref(false);
const errorMessage = ref('');

// ── Production-achievement target-edit permission whitelist ────────────────
const permissions = ref<ProductionAchievementPermissionRow[]>([]);
const permissionsError = ref('');

function getCsrfToken(): string {
  return (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null)?.content ?? '';
}

async function putJson<T>(url: string, payload: unknown): Promise<T> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(payload) });
  let body: { success?: boolean; data?: T; error?: { message?: string } | string } | null = null;
  try { body = await resp.json(); } catch { /* empty body */ }
  if (!resp.ok || body?.success === false) {
    const errMsg = typeof body?.error === 'string'
      ? body.error
      : body?.error?.message ?? `HTTP ${resp.status}`;
    throw new Error(errMsg);
  }
  return (body?.data ?? body) as T;
}

async function loadPages(): Promise<void> {
  const res = await apiGet<{ pages: PageStatus[] }>('/admin/api/pages');
  const raw: PageStatus[] = ('data' in res ? res.data : null)?.pages ?? [];
  const statusMap = new Map(raw.map(p => [p.route, p.status]));

  // Build drawer order lookup for sorting
  const drawerOrder = new Map(manifestDrawers.map(d => [d.id, d.order]));

  // Enumerate all non-standalone routes from manifest; overlay with API statuses
  pages.value = Object.entries(manifestRoutes)
    .filter(([, meta]) => meta.drawerId !== null)
    .sort(([, a], [, b]) => {
      const dA = drawerOrder.get(a.drawerId as string) ?? 99;
      const dB = drawerOrder.get(b.drawerId as string) ?? 99;
      return dA !== dB ? dA - dB : a.order - b.order;
    })
    .map(([route, meta]) => ({
      route,
      name: meta.displayName,
      status: statusMap.get(route) ?? ((meta.defaultStatus ?? 'released') as 'released' | 'dev'),
    }));
}

async function refreshAll(): Promise<void> {
  if (refreshing.value) return;
  refreshing.value = true;
  errorMessage.value = '';
  try {
    await loadPages();
  } catch (err: unknown) {
    errorMessage.value = err instanceof Error ? err.message : '載入失敗';
  } finally {
    refreshing.value = false;
  }
}

async function handleUpdatePage(route: string, payload: { status: 'released' | 'dev' }): Promise<void> {
  try {
    await putJson(`/admin/api/pages${route}`, payload);
    await loadPages();
  } catch (err: unknown) {
    window.alert(`更新頁面失敗: ${err instanceof Error ? err.message : ''}`);
    await loadPages();
  }
}

// ── Production-achievement target-edit permission whitelist ────────────────
async function loadPermissions(): Promise<void> {
  const res = await apiGet<ProductionAchievementPermissionRow[]>('/admin/api/production-achievement/permissions');
  permissions.value = ('data' in res ? res.data : null) ?? [];
}

async function refreshPermissions(): Promise<void> {
  permissionsError.value = '';
  try {
    await loadPermissions();
  } catch (err: unknown) {
    permissionsError.value = err instanceof Error ? err.message : '載入授權名單失敗';
  }
}

async function handleTogglePermission(userIdentifier: string, nextValue: boolean): Promise<void> {
  try {
    await putJson(`/admin/api/production-achievement/permissions/${encodeURIComponent(userIdentifier)}`, {
      can_edit_targets: nextValue,
    });
    await loadPermissions();
  } catch (err: unknown) {
    window.alert(`更新授權失敗: ${err instanceof Error ? err.message : ''}`);
    await loadPermissions();
  }
}

async function handleGrantNewPermission(userIdentifier: string): Promise<void> {
  await handleTogglePermission(userIdentifier, true);
}

const isInitialLoading = computed(() => loading.value);

onMounted(async () => {
  loading.value = true;
  try {
    await refreshAll();
    await refreshPermissions();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="theme-admin-pages" data-testid="admin-pages-app">
    <PageHeader title="頁面管理" :refreshing="refreshing" @refresh="refreshAll">
      <template #subtitle>
        管理頁面顯示狀態（Released：所有人可見 / Dev：僅管理員可見）
      </template>
    </PageHeader>

    <div v-if="errorMessage" class="panel error-panel" role="alert">
      {{ errorMessage }}
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">所有頁面</div>
          <div class="panel-subtitle">切換 Released/Dev 狀態；導覽結構由程式碼管理</div>
        </div>
      </div>
      <div v-if="isInitialLoading" class="empty-state">載入中...</div>
      <PagesManagementPanel
        v-else
        :pages="pages"
        @update="handleUpdatePage"
      />
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">生產達成率 — 目標值編輯權限</div>
          <div class="panel-subtitle">管理可編輯「生產達成率」目標值的使用者白名單（can_edit_targets）</div>
        </div>
      </div>
      <div v-if="permissionsError" class="panel error-panel" role="alert">
        {{ permissionsError }}
      </div>
      <div v-if="isInitialLoading" class="empty-state">載入中...</div>
      <TargetPermissionsPanel
        v-else
        :permissions="permissions"
        @toggle="handleTogglePermission"
        @grant-new="handleGrantNewPermission"
      />
    </div>
  </div>
</template>

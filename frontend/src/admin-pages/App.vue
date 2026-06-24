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
import { apiGet } from '../core/api';
import { routes as manifestRoutes } from '../portal-shell/navigationManifest.js';

interface PageStatus {
  route: string;
  status: 'released' | 'dev';
}

interface PageDisplay {
  route: string;
  name: string;
  status: 'released' | 'dev';
}

const pages = ref<PageDisplay[]>([]);
const loading = ref(false);
const refreshing = ref(false);
const errorMessage = ref('');

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

/** Join manifest display names onto a list of {route, status} items. */
function joinManifestNames(statusList: PageStatus[]): PageDisplay[] {
  return statusList.map((item) => {
    const meta = manifestRoutes[item.route as keyof typeof manifestRoutes];
    const name = meta?.displayName ?? item.route;
    return { route: item.route, name, status: item.status };
  });
}

async function loadPages(): Promise<void> {
  const res = await apiGet<{ pages: PageStatus[] }>('/admin/api/pages');
  const raw: PageStatus[] = ('data' in res ? res.data : null)?.pages ?? [];
  pages.value = joinManifestNames(raw);
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

const isInitialLoading = computed(() => loading.value);

onMounted(async () => {
  loading.value = true;
  try {
    await refreshAll();
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

    <div v-if="errorMessage" class="panel error-panel">
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import DrawerManagementPanel from './components/DrawerManagementPanel.vue';
import PagesManagementPanel from './components/PagesManagementPanel.vue';
import { apiGet, apiPost } from '../core/api';

interface Drawer {
  id: string;
  name: string;
  order: number | null;
  admin_only: boolean;
}

interface Page {
  route: string;
  name: string;
  status: 'released' | 'dev';
  drawer_id: string | null;
  order: number | null;
}

const drawers = ref<Drawer[]>([]);
const pages = ref<Page[]>([]);
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

async function deleteJson(url: string): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method: 'DELETE', headers });
  if (!resp.ok) {
    let body: { error?: { message?: string } | string } | null = null;
    try { body = await resp.json(); } catch { /* empty */ }
    const errMsg = typeof body?.error === 'string'
      ? body.error
      : (body?.error as { message?: string } | undefined)?.message ?? `HTTP ${resp.status}`;
    throw new Error(errMsg);
  }
}

async function loadDrawers(): Promise<void> {
  const res = await apiGet<{ drawers: Drawer[] }>('/admin/api/drawers');
  drawers.value = ('data' in res ? res.data : null)?.drawers ?? [];
}

async function loadPages(): Promise<void> {
  const res = await apiGet<{ pages: Page[] }>('/admin/api/pages');
  pages.value = ('data' in res ? res.data : null)?.pages ?? [];
}

async function refreshAll(): Promise<void> {
  if (refreshing.value) return;
  refreshing.value = true;
  errorMessage.value = '';
  try {
    await Promise.all([loadDrawers(), loadPages()]);
  } catch (err: unknown) {
    errorMessage.value = err instanceof Error ? err.message : '載入失敗';
  } finally {
    refreshing.value = false;
  }
}

async function handleCreateDrawer(payload: { name: string; order?: number; admin_only: boolean }): Promise<void> {
  try {
    await apiPost('/admin/api/drawers', payload);
    await refreshAll();
  } catch (err: unknown) {
    window.alert(`新增抽屜失敗: ${err instanceof Error ? err.message : ''}`);
  }
}

async function handleUpdateDrawer(id: string, payload: Partial<Drawer>): Promise<void> {
  try {
    await putJson(`/admin/api/drawers/${encodeURIComponent(id)}`, payload);
    await refreshAll();
  } catch (err: unknown) {
    window.alert(`更新抽屜失敗: ${err instanceof Error ? err.message : ''}`);
  }
}

async function handleDeleteDrawer(id: string): Promise<void> {
  if (!window.confirm(`確定刪除抽屜「${id}」？`)) return;
  try {
    await deleteJson(`/admin/api/drawers/${encodeURIComponent(id)}`);
    await refreshAll();
  } catch (err: unknown) {
    window.alert(`刪除抽屜失敗: ${err instanceof Error ? err.message : ''}`);
  }
}

async function handleUpdatePage(route: string, payload: Partial<Page>): Promise<void> {
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
  <div class="theme-admin-pages">
    <PageHeader title="頁面管理" :refreshing="refreshing" @refresh="refreshAll">
      <template #subtitle>
        管理頁面狀態、抽屜分類與排序（Released：所有人可見 / Dev：僅管理員可見）
      </template>
    </PageHeader>

    <div v-if="errorMessage" class="panel error-panel">
      {{ errorMessage }}
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">抽屜管理</div>
          <div class="panel-subtitle">可新增、改名、排序、設定 admin-only，空抽屜才能刪除</div>
        </div>
      </div>
      <div v-if="isInitialLoading" class="empty-state">載入中...</div>
      <DrawerManagementPanel
        v-else
        :drawers="drawers"
        @create="handleCreateDrawer"
        @update="handleUpdateDrawer"
        @delete="handleDeleteDrawer"
      />
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">所有頁面</div>
          <div class="panel-subtitle">可切換 Released/Dev，並設定抽屜歸屬與抽屜內排序</div>
        </div>
      </div>
      <div v-if="isInitialLoading" class="empty-state">載入中...</div>
      <PagesManagementPanel
        v-else
        :pages="pages"
        :drawers="drawers"
        @update="handleUpdatePage"
      />
    </div>
  </div>
</template>

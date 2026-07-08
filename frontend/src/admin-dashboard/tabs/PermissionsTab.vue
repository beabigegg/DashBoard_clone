<script setup>
/**
 * PermissionsTab — production-achievement target-value edit permission
 * whitelist ("生產達成率 — 目標值編輯權限"), relocated from admin-pages/App.vue
 * per specs/changes/move-target-permissions-panel/implementation-plan.md.
 *
 * Endpoints (api-contract.md rows 260-261, admin-gated):
 *   GET /admin/api/production-achievement/permissions
 *   PUT /admin/api/production-achievement/permissions/{user_identifier}
 */
import { onMounted, ref } from 'vue';

import TargetPermissionsPanel from '../components/TargetPermissionsPanel.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import { apiGet } from '../../core/api.js';
import { useLastUpdated } from '../../admin-shared/composables/useLastUpdated';

const permissions = ref([]);
const permissionsError = ref('');
const loading = ref(true);
const { lastUpdatedLabel, markUpdated } = useLastUpdated();

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
}

async function putJson(url, payload) {
  const csrf = getCsrfToken();
  const headers = { 'Content-Type': 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(payload) });
  let body = null;
  try { body = await resp.json(); } catch { /* empty body */ }
  if (!resp.ok || body?.success === false) {
    const errMsg = typeof body?.error === 'string'
      ? body.error
      : body?.error?.message ?? `HTTP ${resp.status}`;
    throw new Error(errMsg);
  }
  return body?.data ?? body;
}

async function loadPermissions() {
  const res = await apiGet('/admin/api/production-achievement/permissions');
  permissions.value = ('data' in res ? res.data : null) ?? [];
}

async function refresh() {
  permissionsError.value = '';
  try {
    await loadPermissions();
    markUpdated();
  } catch (err) {
    permissionsError.value = err instanceof Error ? err.message : '載入授權名單失敗';
  } finally {
    loading.value = false;
  }
}

async function handleTogglePermission(userIdentifier, nextValue) {
  try {
    await putJson(`/admin/api/production-achievement/permissions/${encodeURIComponent(userIdentifier)}`, {
      can_edit_targets: nextValue,
    });
    await loadPermissions();
  } catch (err) {
    window.alert(`更新授權失敗: ${err instanceof Error ? err.message : ''}`);
    await loadPermissions();
  }
}

async function handleGrantNewPermission(userIdentifier) {
  await handleTogglePermission(userIdentifier, true);
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="permissions-tab">
    <div class="admin-tab__last-updated" role="status" aria-live="polite">{{ lastUpdatedLabel }}</div>
    <ErrorBanner :message="permissionsError" :dismissible="false" data-testid="error-banner" />

    <SectionCard>
      <template #header>
        <div>
          <h2 class="panel-title">生產達成率 — 目標值編輯權限</h2>
          <p class="sub-title">管理可編輯「生產達成率」目標值的使用者白名單（can_edit_targets）</p>
        </div>
      </template>
      <BlockLoadingState v-if="loading" data-testid="loading-state" />
      <TargetPermissionsPanel
        v-else
        :permissions="permissions"
        @toggle="handleTogglePermission"
        @grant-new="handleGrantNewPermission"
      />
    </SectionCard>
  </div>
</template>

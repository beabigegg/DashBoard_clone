<script setup lang="ts">
/**
 * TargetPermissionsPanel — list/assign/revoke the `can_edit_targets`
 * whitelist for the production-achievement target-value editor.
 *
 * Endpoints (api-contract.md rows 260-261, admin-gated):
 *   GET /admin/api/production-achievement/permissions
 *   PUT /admin/api/production-achievement/permissions/{user_identifier}
 *
 * Lives inside the admin-dashboard app (.theme-admin-dashboard scope) as the
 * `permissions` tab — moved from admin-pages per
 * specs/changes/move-target-permissions-panel/implementation-plan.md.
 */
import { ref } from 'vue';

interface PermissionRow {
  user_identifier: string;
  can_edit_targets: boolean;
  granted_at: string;
  granted_by: string;
}

const props = defineProps<{ permissions: PermissionRow[] }>();

const emit = defineEmits<{
  toggle: [userIdentifier: string, nextValue: boolean];
  grantNew: [userIdentifier: string];
}>();

const newUserIdentifier = ref('');

function handleToggle(row: PermissionRow): void {
  emit('toggle', row.user_identifier, !row.can_edit_targets);
}

function handleGrantNew(): void {
  const identifier = newUserIdentifier.value.trim();
  if (!identifier) return;
  emit('grantNew', identifier);
  newUserIdentifier.value = '';
}
</script>

<template>
  <div class="pa-perm-table-container" data-testid="pa-permissions-panel">
    <div class="pa-perm-add-row">
      <input
        v-model="newUserIdentifier"
        type="text"
        class="pa-perm-add-input"
        placeholder="輸入使用者帳號（LDAP username）"
        data-testid="pa-permissions-new-user-input"
        @keydown.enter="handleGrantNew"
      />
      <button
        type="button"
        class="ui-btn ui-btn--primary ui-btn--sm"
        data-testid="pa-permissions-new-user-btn"
        @click="handleGrantNew"
      >
        新增授權
      </button>
    </div>

    <table class="pa-perm-table">
      <thead>
        <tr>
          <th>使用者帳號</th>
          <th>可編輯目標值</th>
          <th>授權時間</th>
          <th>授權人</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="props.permissions.length === 0">
          <td colspan="4" class="pa-perm-empty" data-testid="pa-permissions-empty">尚無授權名單</td>
        </tr>
        <tr v-for="row in props.permissions" :key="row.user_identifier">
          <td class="pa-perm-user-cell">{{ row.user_identifier }}</td>
          <td>
            <button
              type="button"
              class="pa-perm-badge"
              :class="row.can_edit_targets ? 'pa-perm-badge--granted' : 'pa-perm-badge--revoked'"
              :aria-pressed="row.can_edit_targets"
              data-testid="pa-permissions-toggle"
              @click="handleToggle(row)"
            >
              {{ row.can_edit_targets ? '已授權' : '未授權' }}
            </button>
          </td>
          <td>{{ row.granted_at }}</td>
          <td>{{ row.granted_by }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
/**
 * PagesManagementPanel — status-toggle only.
 *
 * Display name is joined from the manifest (passed in as `pages[].name`).
 * Drawer assignment and order are now code-owned by navigationManifest.js
 * and are NOT editable here.
 */

interface Page {
  route: string;
  name: string;
  status: 'released' | 'dev';
}

const props = defineProps<{ pages: Page[] }>();

const emit = defineEmits<{
  update: [route: string, payload: { status: 'released' | 'dev' }];
}>();

function toggleStatus(page: Page): void {
  const nextStatus: 'released' | 'dev' = page.status === 'released' ? 'dev' : 'released';
  emit('update', page.route, { status: nextStatus });
}
</script>

<template>
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>路由</th>
          <th>名稱</th>
          <th>狀態</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="pages.length === 0">
          <td colspan="3" class="empty-state">尚無頁面設定</td>
        </tr>
        <tr v-for="page in pages" :key="page.route">
          <td class="route-cell">{{ page.route }}</td>
          <td>{{ page.name }}</td>
          <td>
            <button
              type="button"
              class="status-badge"
              :class="page.status === 'released' ? 'status-released' : 'status-dev'"
              :aria-pressed="page.status === 'released'"
              @click="toggleStatus(page)"
            >
              {{ page.status === 'released' ? 'Released' : 'Dev' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

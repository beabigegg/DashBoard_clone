<script setup lang="ts">
interface Drawer {
  id: string;
  name: string;
}

interface Page {
  route: string;
  name: string;
  status: 'released' | 'dev';
  drawer_id: string | null;
  order: number | null;
}

const props = defineProps<{ pages: Page[]; drawers: Drawer[] }>();

const emit = defineEmits<{
  update: [route: string, payload: Partial<Page>];
}>();

function toggleStatus(page: Page): void {
  const nextStatus: 'released' | 'dev' = page.status === 'released' ? 'dev' : 'released';
  emit('update', page.route, { status: nextStatus });
}

function changeDrawer(page: Page, event: Event): void {
  const select = event.target as HTMLSelectElement;
  const drawerId = select.value || null;
  emit('update', page.route, { drawer_id: drawerId });
}

function changeOrder(page: Page, event: Event): void {
  const input = event.target as HTMLInputElement;
  const value = input.value.trim();
  emit('update', page.route, { order: value === '' ? null : Number(value) });
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
          <th>抽屜歸屬</th>
          <th>排序</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="pages.length === 0">
          <td colspan="5" class="empty-state">尚無頁面設定</td>
        </tr>
        <tr v-for="page in pages" :key="page.route">
          <td class="route-cell">{{ page.route }}</td>
          <td>{{ page.name }}</td>
          <td>
            <button
              type="button"
              class="status-badge"
              :class="page.status === 'released' ? 'status-released' : 'status-dev'"
              @click="toggleStatus(page)"
            >
              {{ page.status === 'released' ? 'Released' : 'Dev' }}
            </button>
          </td>
          <td>
            <select
              class="input"
              :value="page.drawer_id ?? ''"
              @change="changeDrawer(page, $event)"
            >
              <option value="">未分類</option>
              <option v-for="drawer in drawers" :key="drawer.id" :value="drawer.id">
                {{ drawer.name }}
              </option>
            </select>
          </td>
          <td>
            <input
              class="input order-input"
              type="number"
              min="1"
              :value="page.order ?? ''"
              placeholder="未設定"
              @change="changeOrder(page, $event)"
            />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

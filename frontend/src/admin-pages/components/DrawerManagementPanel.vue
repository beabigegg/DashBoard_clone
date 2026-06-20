<script setup lang="ts">
import { ref } from 'vue';

interface Drawer {
  id: string;
  name: string;
  order: number | null;
  admin_only: boolean;
}

interface DrawerEditState {
  name: string;
  order: string;
  admin_only: boolean;
}

const props = defineProps<{ drawers: Drawer[] }>();

const emit = defineEmits<{
  create: [payload: { name: string; order?: number; admin_only: boolean }];
  update: [id: string, payload: Partial<Drawer>];
  delete: [id: string];
}>();

const newName = ref('');
const newOrder = ref('');
const newAdminOnly = ref(false);

const editStates = ref<Record<string, DrawerEditState>>({});

function getEditState(drawer: Drawer): DrawerEditState {
  if (!editStates.value[drawer.id]) {
    editStates.value[drawer.id] = {
      name: drawer.name,
      order: drawer.order != null ? String(drawer.order) : '',
      admin_only: drawer.admin_only,
    };
  }
  return editStates.value[drawer.id];
}

function handleCreate(): void {
  const name = newName.value.trim();
  if (!name) {
    window.alert('請輸入抽屜名稱');
    return;
  }
  const payload: { name: string; order?: number; admin_only: boolean } = {
    name,
    admin_only: newAdminOnly.value,
  };
  if (newOrder.value.trim() !== '') {
    payload.order = Number(newOrder.value.trim());
  }
  emit('create', payload);
  newName.value = '';
  newOrder.value = '';
  newAdminOnly.value = false;
}

function handleSave(drawer: Drawer): void {
  const state = editStates.value[drawer.id];
  if (!state) return;
  const payload: Partial<Drawer> = {
    name: state.name,
    admin_only: state.admin_only,
  };
  if (state.order.trim() !== '') {
    payload.order = Number(state.order);
  } else {
    payload.order = null;
  }
  emit('update', drawer.id, payload);
}

function handleDelete(id: string): void {
  emit('delete', id);
}
</script>

<template>
  <div class="drawer-create">
    <input
      v-model="newName"
      class="input"
      type="text"
      data-testid="create-drawer-name"
      placeholder="新抽屜名稱（例如：自訂分類）"
      @keydown.enter.prevent="handleCreate"
    />
    <input
      v-model="newOrder"
      class="input order-input"
      type="number"
      min="1"
      placeholder="排序"
    />
    <label class="checkbox-label">
      <input v-model="newAdminOnly" type="checkbox" />
      僅管理員可見
    </label>
    <button class="action-btn primary" type="button" data-testid="create-drawer-btn" @click="handleCreate">新增抽屜</button>
  </div>
  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>名稱</th>
          <th>排序</th>
          <th>可見性</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="drawers.length === 0">
          <td colspan="5" class="empty-state">尚無抽屜</td>
        </tr>
        <tr v-for="drawer in drawers" :key="drawer.id">
          <td class="route-cell">{{ drawer.id }}</td>
          <td>
            <input
              v-model="getEditState(drawer).name"
              class="input"
              type="text"
            />
          </td>
          <td>
            <input
              v-model="getEditState(drawer).order"
              class="input order-input"
              type="number"
              min="1"
            />
          </td>
          <td>
            <label class="checkbox-label">
              <input v-model="getEditState(drawer).admin_only" type="checkbox" />
              僅管理員
            </label>
          </td>
          <td class="actions-cell">
            <button class="action-btn" type="button" @click="handleSave(drawer)">儲存</button>
            <button class="action-btn danger" type="button" @click="handleDelete(drawer.id)">刪除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

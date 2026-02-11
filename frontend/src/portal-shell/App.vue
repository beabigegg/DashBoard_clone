<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import HealthStatus from './components/HealthStatus.vue';
import { syncNavigationRoutes } from './router.js';

const route = useRoute();
const loading = ref(true);
const errorMessage = ref('');
const drawers = ref([]);
const isAdmin = ref(false);
const adminUser = ref(null);

function toShellPath(targetRoute) {
  const normalized = String(targetRoute || '').trim();
  if (!normalized || normalized === '/') {
    return '/';
  }
  return `/${normalized.replace(/^\/+/, '')}`;
}

const breadcrumb = computed(() => {
  const title = route.meta?.title || '首頁';
  const drawerName = route.meta?.drawerName || '';
  return {
    drawerName,
    title,
  };
});

const adminDisplayName = computed(() => {
  if (!adminUser.value) return '';
  return adminUser.value.displayName || adminUser.value.username || '';
});

const adminLoginHref = computed(() => `/admin/login?next=${encodeURIComponent('/portal-shell')}`);

async function loadNavigation() {
  loading.value = true;
  errorMessage.value = '';

  try {
    const response = await fetch('/api/portal/navigation', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Navigation API error: ${response.status}`);
    }
    const payload = await response.json();
    drawers.value = Array.isArray(payload.drawers) ? payload.drawers : [];
    isAdmin.value = Boolean(payload.is_admin);
    adminUser.value = payload.admin_user || null;
    syncNavigationRoutes(drawers.value);
  } catch (error) {
    errorMessage.value = error?.message || '無法載入導覽資料';
    drawers.value = [];
    isAdmin.value = false;
    adminUser.value = null;
    syncNavigationRoutes([]);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadNavigation();
});
</script>

<template>
  <div class="shell">
    <header class="shell-header">
      <div>
        <h1>MES 報表入口 (SPA Shell)</h1>
        <p>No-iframe 路由導覽（遷移完成）</p>
      </div>
      <div class="shell-header-right">
        <HealthStatus />
        <div class="admin-entry">
          <template v-if="isAdmin">
            <a class="admin-link" href="/admin/pages">管理後台</a>
            <span v-if="adminDisplayName" class="admin-name">{{ adminDisplayName }}</span>
            <a class="admin-link" href="/admin/logout">登出</a>
          </template>
          <template v-else>
            <a class="admin-link" :href="adminLoginHref">管理員登入</a>
          </template>
        </div>
      </div>
    </header>

    <main class="shell-main">
      <aside class="sidebar">
        <div v-if="loading" class="muted">載入導覽中...</div>
        <div v-else-if="errorMessage" class="error">{{ errorMessage }}</div>
        <template v-else>
          <section v-for="drawer in drawers" :key="drawer.id" class="drawer">
            <h2 class="drawer-title">{{ drawer.name }}</h2>
            <RouterLink
              v-for="page in drawer.pages"
              :key="page.route"
              class="drawer-link"
              active-class="active"
              :to="toShellPath(page.route)"
            >
              <span>{{ page.name }}</span>
            </RouterLink>
          </section>
        </template>
      </aside>

      <section class="content">
        <div class="breadcrumb">
          <span v-if="breadcrumb.drawerName">{{ breadcrumb.drawerName }}</span>
          <span v-if="breadcrumb.drawerName">/</span>
          <span>{{ breadcrumb.title }}</span>
        </div>
        <RouterView v-slot="{ Component, route: currentRoute }">
          <Transition name="route-fade" mode="out-in">
            <component :is="Component" :key="currentRoute.fullPath" />
          </Transition>
        </RouterView>
      </section>
    </main>
  </div>
</template>

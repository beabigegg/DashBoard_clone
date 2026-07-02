<script setup>
import './ai-chat.css';

import {
  Activity,
  AlertCircle,
  BarChart2,
  Briefcase,
  ChevronRight,
  Circle,
  Clock,
  Cpu,
  GitBranch,
  Layers,
  LayoutDashboard,
  LogOut,
  Monitor,
  Package,
  Search,
  Settings,
  TrendingDown,
  User,
} from 'lucide-vue-next';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAiChat } from '../shared-composables/useAiChat.js';
import { provideUpdateBadge } from '../shared-composables/usePageUpdateBadge.js';
import DataUpdateBadge from '../shared-ui/components/DataUpdateBadge.vue';
import AiChatPanel from '../shared-ui/components/AiChatPanel.vue';
import AiChatTrigger from '../shared-ui/components/AiChatTrigger.vue';
import AnomalyIndicator from './components/AnomalyIndicator.vue';
import HealthStatus from './components/HealthStatus.vue';
import { onlineCount, useAuth } from './composables/useAuth.js';
import { consumeNavigationNotice, setAuthState, syncNavigationRoutes } from './router.js';
import { normalizeRoutePath } from './routeContracts.js';
import { buildSidebarUiState } from './sidebarState.js';

const route = useRoute();
const router = useRouter();
const aiChat = useAiChat();
const auth = useAuth();
const loading = ref(true);
const errorMessage = ref('');
const drawers = ref([]);
const isAdmin = ref(false);
const adminUser = ref(null);
const navigationNotice = ref('');
const adminLinks = ref({
  logout: null,
  dashboard: '/admin/dashboard',
});
const sidebarOpen = ref(false);
const aiEnabled = ref(false);
const updateBadge = provideUpdateBadge();

function toShellPath(targetRoute) {
  return normalizeRoutePath(targetRoute);
}

const userInitial = computed(() => {
  const name = adminDisplayName.value;
  if (!name) return '?';
  return name.charAt(0).toUpperCase();
});

function getPageIcon(routePath) {
  const r = String(routePath).toLowerCase();
  if (r.includes('wip')) return LayoutDashboard;
  if (r.includes('hold')) return AlertCircle;
  if (r.includes('yield') || r.includes('alert-center')) return TrendingDown;
  if (r.includes('resource/status') || r.includes('resource-status')) return Monitor;
  if (r.includes('resource')) return Cpu;
  if (r.includes('query')) return Search;
  if (r.includes('job')) return Briefcase;
  if (r.includes('trace')) return GitBranch;
  if (r.includes('material') || r.includes('consumption')) return Package;
  if (r.includes('eap') || r.includes('alarm')) return AlertCircle;
  if (r.includes('downtime') || r.includes('analysis')) return BarChart2;
  if (r.includes('production') || r.includes('spc')) return Activity;
  if (r.includes('reject') || r.includes('history')) return Clock;
  if (r.includes('defect') || r.includes('mid')) return Layers;
  return Circle;
}

function isPortalShellRootPath() {
  const path = String(window.location.pathname || '').replace(/\/+$/, '');
  return path === '/portal-shell' || path === '';
}

const isLoginPage = computed(() => route.path === '/login');

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

async function handleLogout() {
  await auth.logout();
  await router.push('/login');
}

const sidebarUiState = computed(() =>
  buildSidebarUiState({ sidebarOpen: sidebarOpen.value }),
);

const sidebarToggleLabel = computed(() =>
  sidebarOpen.value ? '關閉選單' : '開啟選單',
);

function closeSidebar() {
  sidebarOpen.value = false;
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}

function handleGlobalKeydown(event) {
  if (event.key === 'Escape') {
    if (aiEnabled.value && aiChat.isOpen.value) {
      aiChat.togglePanel();
    }
    closeSidebar();
  }
}

async function loadNavigation() {
  loading.value = true;
  errorMessage.value = '';

  try {
    const response = await fetch('/api/portal/navigation', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Navigation API error: ${response.status}`);
    }
    const payload = await response.json();
    isAdmin.value = Boolean(payload.is_admin);
    adminUser.value = payload.admin_user || null;
    adminLinks.value = payload.admin_links || adminLinks.value;
    aiEnabled.value = Boolean(payload.features?.ai_query_enabled);
    const statusMap = (payload.statuses && typeof payload.statuses === 'object')
      ? payload.statuses
      : {};
    const state = syncNavigationRoutes(statusMap, {
      isAdmin: isAdmin.value,
      includeStandaloneDrilldown: true,
    });
    drawers.value = state.drawers;

    // Wait for the router's own initial navigation to finish resolving before
    // inspecting `route`. Without this, on a direct/hard-navigated deep link
    // (e.g. /production-achievement) this async loadNavigation() call can
    // read `route` while it is still mid-resolution (route.name undefined,
    // route.path stuck at the pre-navigation placeholder) — so the
    // `shell-fallback` self-heal replace below silently never fires and the
    // page is stuck showing ShellHomeView even though allowedPaths already
    // contains the freshly-synced dynamic route.
    await router.isReady();
    if (route.name === 'shell-fallback') {
      if (state.allowedPaths.includes(route.path)) {
        await router.replace(route.fullPath);
      } else {
        navigationNotice.value = `路由 ${route.path} 不在可用清單，已返回首頁。`;
        await router.replace('/');
      }
    }

    if (route.path === '/' && isPortalShellRootPath()) {
      const firstRoute = state?.drawers?.[0]?.pages?.[0]?.route;
      const defaultShellPath = firstRoute ? normalizeRoutePath(firstRoute) : '/';
      if (defaultShellPath !== '/') {
        await router.replace(defaultShellPath);
      }
    }

    const backendMismatches = Array.isArray(payload?.diagnostics?.contract_mismatch_routes)
      ? payload.diagnostics.contract_mismatch_routes
      : [];

    if (backendMismatches.length > 0) {
      navigationNotice.value = `後端導覽含未納管路由：${backendMismatches.join(', ')}`;
    } else if (state.diagnostics.missingContractRoutes.length > 0) {
      navigationNotice.value = `部分導覽項目缺少 route contract：${state.diagnostics.missingContractRoutes.join(', ')}`;
    } else {
      navigationNotice.value = '';
    }
  } catch (error) {
    errorMessage.value = error?.message || '無法載入導覽資料';
    drawers.value = [];
    isAdmin.value = false;
    adminUser.value = null;
    adminLinks.value = {
      logout: null,
      dashboard: '/admin/dashboard',
    };
    syncNavigationRoutes({}, { isAdmin: false, includeStandaloneDrilldown: false });
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown);
  if (!isLoginPage.value) {
    void loadNavigation();
    auth.startHeartbeat();
  }

  // Global 401 interceptor: redirect to /login if session expires.
  let _redirecting401 = false;
  const _origFetch = window.fetch;
  window.fetch = async (...args) => {
    const res = await _origFetch(...args);
    if (res.status === 401 && !_redirecting401) {
      const url = String(args[0] || '');
      if (!url.includes('/api/auth/')) {
        _redirecting401 = true;
        auth.stopHeartbeat();
        setAuthState(false);
        await router.push('/login');
        _redirecting401 = false;
      }
    }
    return res;
  };
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown);
  document.body.style.overflow = '';
});

watch(sidebarOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : '';
});

watch(
  () => route.fullPath,
  () => {
    closeSidebar();
    navigationNotice.value = consumeNavigationNotice();
  },
  { immediate: true },
);

// Reload navigation when transitioning away from login page (after successful login).
watch(isLoginPage, (isLogin, wasLogin) => {
  if (wasLogin && !isLogin) {
    void loadNavigation();
  }
});
</script>

<template>
  <!-- Login page: full-screen, no shell chrome -->
  <RouterView v-if="isLoginPage" />

  <!-- Authenticated shell: header + sidebar + content -->
  <div v-else class="shell theme-portal-shell" :class="sidebarUiState.shellClass">
    <a href="#main-content" class="sr-only focus:not-sr-only">跳至主要內容</a>
    <header class="shell-header">
      <div class="shell-header-left">
        <button
          type="button"
          class="sidebar-toggle"
          :aria-expanded="sidebarUiState.ariaExpanded"
          :aria-label="sidebarToggleLabel"
          @click="toggleSidebar"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M4 6h16M4 12h16M4 18h16"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
            />
          </svg>
        </button>
        <h1>MES 報表入口</h1>
      </div>
      <div class="shell-header-right">
        <AnomalyIndicator />
        <div v-if="onlineCount !== null" class="online-count" aria-label="在線人數">
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
          <span>{{ onlineCount }}</span>
        </div>
        <HealthStatus />
      </div>
    </header>

    <Transition name="overlay-fade">
      <div v-if="sidebarOpen" class="sidebar-overlay" @click="closeSidebar" />
    </Transition>

    <main id="main-content" class="shell-main">
      <aside class="sidebar" :class="sidebarUiState.sidebarClass" role="navigation" aria-label="主選單">
        <nav class="sidebar-nav">
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
                :title="page.name"
              >
                <component :is="getPageIcon(page.route)" class="drawer-link-icon" :size="16" aria-hidden="true" />
                <span class="drawer-link-label">{{ page.name }}</span>
              </RouterLink>
            </section>
          </template>
        </nav>
        <div class="sidebar-footer">
          <div v-if="adminDisplayName" class="sidebar-user">
            <div class="sidebar-user-avatar" :title="adminDisplayName">{{ userInitial }}</div>
            <div class="sidebar-user-details">
              <span class="sidebar-user-name">{{ adminDisplayName }}</span>
              <span v-if="adminUser?.department" class="sidebar-user-dept">{{ adminUser.department }}</span>
            </div>
          </div>
          <div class="sidebar-actions">
            <a
              v-if="adminLinks?.pages?.dashboard"
              :href="adminLinks.pages.dashboard"
              class="sidebar-action-link"
              title="管理後台"
            >
              <Settings class="sidebar-action-icon" :size="15" aria-hidden="true" />
              <span class="sidebar-action-label">管理後台</span>
            </a>
            <a
              v-if="adminLinks?.pages?.login"
              :href="adminLinks.pages.login"
              class="sidebar-action-link"
              title="管理員登入"
            >
              <User class="sidebar-action-icon" :size="15" aria-hidden="true" />
              <span class="sidebar-action-label">管理員登入</span>
            </a>
            <button type="button" class="sidebar-action-link" title="登出" @click="handleLogout">
              <LogOut class="sidebar-action-icon" :size="15" aria-hidden="true" />
              <span class="sidebar-action-label">登出</span>
            </button>
          </div>
        </div>
      </aside>

      <section class="shell-content">
        <div v-if="navigationNotice" class="notice-banner">{{ navigationNotice }}</div>
        <div class="breadcrumb">
          <div class="breadcrumb-nav">
            <span v-if="breadcrumb.drawerName">{{ breadcrumb.drawerName }}</span>
            <ChevronRight v-if="breadcrumb.drawerName" :size="14" class="breadcrumb-separator" />
            <span>{{ breadcrumb.title }}</span>
          </div>
          <DataUpdateBadge
            v-if="updateBadge.updateTime !== '--'"
            :update-time="updateBadge.updateTime"
            :refreshing="updateBadge.refreshing"
            :refresh-success="updateBadge.refreshSuccess"
            :refresh-error="updateBadge.refreshError"
          />
        </div>
        <RouterView />
      </section>
    </main>

    <template v-if="aiEnabled">
      <AiChatTrigger v-if="!aiChat.isOpen.value" @click="aiChat.togglePanel" />
      <AiChatPanel
        v-if="aiChat.isOpen.value"
        :messages="aiChat.messages.value"
        :is-loading="aiChat.isLoading.value"
        :is-rate-limited="aiChat.isRateLimited.value"
        :can-submit="aiChat.canSubmit.value"
        :loading-step-text="aiChat.loadingStepText.value"
        @close="aiChat.togglePanel"
        @submit="aiChat.submitQuestion"
        @reset="aiChat.clearHistory"
      />
    </template>
  </div>
</template>

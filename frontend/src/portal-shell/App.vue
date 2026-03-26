<script setup>
import './ai-chat.css';

import { ChevronRight } from 'lucide-vue-next';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAiChat } from '../shared-composables/useAiChat.js';
import AiChatPanel from '../shared-ui/components/AiChatPanel.vue';
import AiChatTrigger from '../shared-ui/components/AiChatTrigger.vue';
import AnomalyIndicator from './components/AnomalyIndicator.vue';
import HealthStatus from './components/HealthStatus.vue';
import { useAuth } from './composables/useAuth.js';
import { consumeNavigationNotice, setAuthState, syncNavigationRoutes } from './router.js';
import { normalizeRoutePath } from './routeContracts.js';
import {
  SIDEBAR_STORAGE_KEY,
  buildSidebarUiState,
  isMobileViewport,
  parseSidebarCollapsedPreference,
  serializeSidebarCollapsedPreference,
} from './sidebarState.js';

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
const sidebarCollapsed = ref(false);
const sidebarMobileOpen = ref(false);
const isMobile = ref(false);

function toShellPath(targetRoute) {
  return normalizeRoutePath(targetRoute);
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
  buildSidebarUiState({
    isMobile: isMobile.value,
    sidebarCollapsed: sidebarCollapsed.value,
    sidebarMobileOpen: sidebarMobileOpen.value,
  }),
);

const sidebarToggleLabel = computed(() => {
  if (isMobile.value) {
    return sidebarMobileOpen.value ? '關閉側邊欄' : '開啟側邊欄';
  }
  return sidebarCollapsed.value ? '展開側邊欄' : '收合側邊欄';
});

function restoreSidebarPreference() {
  try {
    const stored = window.sessionStorage.getItem(SIDEBAR_STORAGE_KEY);
    sidebarCollapsed.value = parseSidebarCollapsedPreference(stored);
  } catch {
    sidebarCollapsed.value = false;
  }
}

function persistSidebarPreference() {
  try {
    window.sessionStorage.setItem(
      SIDEBAR_STORAGE_KEY,
      serializeSidebarCollapsedPreference(sidebarCollapsed.value),
    );
  } catch {
    // Keep UI behavior deterministic even if storage is unavailable.
  }
}

function checkViewport() {
  isMobile.value = isMobileViewport(window.innerWidth);
  if (!isMobile.value) {
    sidebarMobileOpen.value = false;
  }
}

function closeMobileSidebar() {
  sidebarMobileOpen.value = false;
}

function toggleSidebar() {
  if (isMobile.value) {
    sidebarMobileOpen.value = !sidebarMobileOpen.value;
    return;
  }
  sidebarCollapsed.value = !sidebarCollapsed.value;
  persistSidebarPreference();
}

function handleViewportResize() {
  checkViewport();
}

function handleGlobalKeydown(event) {
  if (event.key === 'Escape') {
    if (aiChat.isOpen.value) {
      aiChat.togglePanel();
    }
    closeMobileSidebar();
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
    const state = syncNavigationRoutes(payload.drawers, {
      isAdmin: isAdmin.value,
      includeStandaloneDrilldown: true,
    });
    drawers.value = state.drawers;

    if (route.name === 'shell-fallback') {
      if (state.allowedPaths.includes(route.path)) {
        await router.replace(route.fullPath);
      } else {
        navigationNotice.value = `路由 ${route.path} 不在可用清單，已返回首頁。`;
        await router.replace('/');
      }
    }

    if (route.path === '/') {
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
    syncNavigationRoutes([]);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  restoreSidebarPreference();
  checkViewport();
  window.addEventListener('resize', handleViewportResize, { passive: true });
  window.addEventListener('keydown', handleGlobalKeydown);
  if (!isLoginPage.value) {
    void loadNavigation();
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
  window.removeEventListener('resize', handleViewportResize);
  window.removeEventListener('keydown', handleGlobalKeydown);
});

watch(
  () => route.fullPath,
  () => {
    closeMobileSidebar();
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
        <HealthStatus />
        <div class="admin-entry">
          <span v-if="adminDisplayName" class="admin-name">{{ adminDisplayName }}</span>
          <button type="button" class="admin-link" @click="handleLogout">登出</button>
        </div>
      </div>
    </header>

    <Transition name="overlay-fade">
      <div v-if="isMobile && sidebarMobileOpen" class="sidebar-overlay" @click="closeMobileSidebar" />
    </Transition>

    <main class="shell-main">
      <aside class="sidebar" :class="sidebarUiState.sidebarClass" role="navigation" aria-label="主選單">
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

      <main id="main-content" class="shell-content">
        <div v-if="navigationNotice" class="notice-banner">{{ navigationNotice }}</div>
        <div class="breadcrumb">
          <span v-if="breadcrumb.drawerName">{{ breadcrumb.drawerName }}</span>
          <ChevronRight v-if="breadcrumb.drawerName" :size="14" class="breadcrumb-separator" />
          <span>{{ breadcrumb.title }}</span>
        </div>
        <RouterView />
      </main>
    </main>

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
  </div>
</template>

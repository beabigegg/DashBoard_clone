import { createRouter, createWebHistory } from 'vue-router';

import LoginPage from './views/LoginPage.vue';
import NativeRouteView from './views/NativeRouteView.vue';
import ShellHomeView from './views/ShellHomeView.vue';
import { buildDynamicNavigationState } from './navigationState.js';
import { normalizeRoutePath } from './routeContracts.js';
import { restoreUrlState } from '../core/shell-navigation.js';

// `createWebHistory` below captures `window.location` synchronously and immediately
// `replaceState`s with the captured value. If `?_s=1` is still in the URL when that
// happens, vue-router will stamp it back even after `restoreUrlState` tries to strip it.
// Restore before createRouter so the history layer sees the reconstructed query.
restoreUrlState();

let allowedRoutePaths = new Set(['/']);
let dynamicRouteNames = [];
let pendingNavigationNotice = '';
let navigationSynced = false;

// Auth state cache — avoids calling /api/auth/me on every navigation.
let authChecked = false;
let isAuthenticated = false;

function toShellPath(route) {
  return normalizeRoutePath(route);
}

export const router = createRouter({
  history: createWebHistory('/portal-shell'),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginPage,
      meta: { title: '登入', public: true }
    },
    {
      path: '/',
      name: 'shell-home',
      component: ShellHomeView,
      meta: { title: 'MES Portal Shell' }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'shell-fallback',
      component: ShellHomeView,
      meta: { title: 'MES 報表入口' },
    }
  ],
  scrollBehavior() {
    return { top: 0 };
  }
});

/**
 * Sync router routes from a runtime status map (from GET /api/portal/navigation).
 *
 * @param {Record<string,string>} statusMap - route → 'released'|'dev' (absent = 'released')
 * @param {{ isAdmin?: boolean, includeStandaloneDrilldown?: boolean }} options
 */
export function syncNavigationRoutes(
  statusMap,
  { isAdmin = false, includeStandaloneDrilldown = false } = {},
) {
  dynamicRouteNames.forEach((name) => {
    if (router.hasRoute(name)) {
      router.removeRoute(name);
    }
  });
  dynamicRouteNames = [];

  // Pass statusMap (plain object) as first arg; navigationState.js detects non-array
  // first arg and uses the manifest drawers imported from navigationManifest.js.
  const state = buildDynamicNavigationState(statusMap, { isAdmin, includeStandaloneDrilldown });

  state.dynamicRoutes.forEach((entry) => {
    router.addRoute({
      path: toShellPath(entry.shellPath),
      name: entry.routeName,
      component: NativeRouteView,
      props: {
        targetRoute: entry.targetRoute,
        pageName: entry.pageName,
        drawerName: entry.drawerName,
        owner: entry.owner,
        renderMode: entry.renderMode,
      },
      meta: {
        title: entry.pageName,
        drawerName: entry.drawerName,
        targetRoute: entry.targetRoute,
        renderMode: entry.renderMode,
        routeId: entry.routeId,
        visibilityPolicy: entry.visibilityPolicy,
        scope: entry.scope,
        compatibilityPolicy: entry.compatibilityPolicy,
      },
    });
    dynamicRouteNames.push(entry.routeName);
  });

  allowedRoutePaths = new Set(state.allowedPaths);
  navigationSynced = true;
  return state;
}

export function consumeNavigationNotice() {
  const notice = pendingNavigationNotice;
  pendingNavigationNotice = '';
  return notice;
}

/**
 * Mark the auth state as authenticated (called after successful login,
 * so we don't immediately re-fetch /api/auth/me on the next navigation).
 */
export function setAuthState(authenticated) {
  isAuthenticated = authenticated;
  authChecked = true;
}

router.beforeEach(async (to) => {
  // Login page is always accessible.
  if (to.path === '/login') {
    return true;
  }

  // Check auth on first navigation to a protected route.
  if (!authChecked) {
    try {
      const res = await fetch('/api/auth/me', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        isAuthenticated = data.data !== null;
      } else {
        isAuthenticated = false;
      }
    } catch {
      isAuthenticated = false;
    }
    authChecked = true;
  }

  if (!isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } };
  }

  // Navigation route guard (only after sync).
  if (!navigationSynced) {
    return true;
  }

  if (to.path === '/' || allowedRoutePaths.has(to.path)) {
    return true;
  }
  pendingNavigationNotice = `路由 ${to.path} 不在可用清單，已返回首頁。`;
  return { path: '/' };
});

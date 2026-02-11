import { createRouter, createWebHistory } from 'vue-router';

import NativeRouteView from './views/NativeRouteView.vue';
import ShellHomeView from './views/ShellHomeView.vue';
import { buildDynamicNavigationState } from './navigationState.js';
import { normalizeRoutePath } from './routeContracts.js';

let allowedRoutePaths = new Set(['/']);
let dynamicRouteNames = [];
let pendingNavigationNotice = '';
let navigationSynced = false;

function toShellPath(route) {
  return normalizeRoutePath(route);
}

export const router = createRouter({
  history: createWebHistory('/portal-shell'),
  routes: [
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

export function syncNavigationRoutes(
  drawers,
  { isAdmin = false, includeStandaloneDrilldown = false } = {},
) {
  dynamicRouteNames.forEach((name) => {
    if (router.hasRoute(name)) {
      router.removeRoute(name);
    }
  });
  dynamicRouteNames = [];

  const state = buildDynamicNavigationState(drawers, { isAdmin, includeStandaloneDrilldown });

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
      },
      meta: {
        title: entry.pageName,
        drawerName: entry.drawerName,
        targetRoute: entry.targetRoute,
        renderMode: entry.renderMode,
        routeId: entry.routeId,
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

router.beforeEach((to) => {
  if (!navigationSynced) {
    return true;
  }

  if (to.path === '/' || allowedRoutePaths.has(to.path)) {
    return true;
  }
  pendingNavigationNotice = `路由 ${to.path} 不在可用清單，已返回首頁。`;
  return { path: '/' };
});

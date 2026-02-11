import { createRouter, createWebHistory } from 'vue-router';

import PageBridgeView from './views/PageBridgeView.vue';
import ShellHomeView from './views/ShellHomeView.vue';

let allowedRoutePaths = new Set(['/']);
let dynamicRouteNames = [];

function toShellPath(route) {
  const normalized = String(route || '').trim();
  if (!normalized || normalized === '/') {
    return '/';
  }
  return `/${normalized.replace(/^\/+/, '')}`;
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
      redirect: '/'
    }
  ],
  scrollBehavior() {
    return { top: 0 };
  }
});

export function syncNavigationRoutes(drawers) {
  dynamicRouteNames.forEach((name) => {
    if (router.hasRoute(name)) {
      router.removeRoute(name);
    }
  });
  dynamicRouteNames = [];

  const nextAllowed = new Set(['/']);
  let index = 0;

  (drawers || []).forEach((drawer) => {
    (drawer.pages || []).forEach((page) => {
      const shellPath = toShellPath(page.route);
      if (shellPath === '/') {
        return;
      }

      const routeName = `shell-page-${index++}`;
      router.addRoute({
        path: shellPath,
        name: routeName,
        component: PageBridgeView,
        props: {
          targetRoute: page.route,
          pageName: page.name || page.route,
          drawerName: drawer.name || drawer.id || ''
        },
        meta: {
          title: page.name || page.route,
          drawerName: drawer.name || drawer.id || '',
          targetRoute: page.route,
        }
      });

      dynamicRouteNames.push(routeName);
      nextAllowed.add(shellPath);
    });
  });

  allowedRoutePaths = nextAllowed;
}

router.beforeEach((to) => {
  if (to.path === '/' || allowedRoutePaths.has(to.path)) {
    return true;
  }
  return { path: '/' };
});

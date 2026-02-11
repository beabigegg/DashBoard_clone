import { getRouteContract, normalizeRoutePath } from './routeContracts.js';

const STANDALONE_DRILLDOWN_ROUTES = Object.freeze([
  '/wip-detail',
  '/hold-detail',
]);

function safeInt(value, fallback = 9999) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function canViewPage(status, isAdmin) {
  if (isAdmin) {
    return true;
  }
  return String(status || 'released') === 'released';
}

function sortByOrderThenName(items, nameKey = 'name') {
  return [...items].sort((a, b) => {
    const orderDiff = safeInt(a?.order) - safeInt(b?.order);
    if (orderDiff !== 0) {
      return orderDiff;
    }
    return String(a?.[nameKey] || '').localeCompare(String(b?.[nameKey] || ''));
  });
}

export function normalizeNavigationDrawers(drawers, { isAdmin = false } = {}) {
  const input = Array.isArray(drawers) ? drawers : [];
  const normalizedDrawers = sortByOrderThenName(input).flatMap((drawer) => {
    const drawerId = String(drawer?.id || '').trim();
    if (!drawerId) {
      return [];
    }

    const adminOnly = Boolean(drawer?.admin_only);
    if (adminOnly && !isAdmin) {
      return [];
    }

    const pages = Array.isArray(drawer?.pages) ? drawer.pages : [];
    const normalizedPages = sortByOrderThenName(pages).flatMap((page) => {
      const route = String(page?.route || '').trim();
      if (!route || !route.startsWith('/')) {
        return [];
      }
      if (!canViewPage(page?.status, isAdmin)) {
        return [];
      }
      return [
        {
          route,
          name: page?.name || route,
          status: page?.status || 'dev',
          order: safeInt(page?.order),
        },
      ];
    });

    if (!normalizedPages.length) {
      return [];
    }

    return [
      {
        id: drawerId,
        name: drawer?.name || drawerId,
        order: safeInt(drawer?.order),
        admin_only: adminOnly,
        pages: normalizedPages,
      },
    ];
  });

  return normalizedDrawers;
}

export function buildDynamicNavigationState(
  drawers,
  { isAdmin = false, includeStandaloneDrilldown = false } = {},
) {
  const normalizedDrawers = normalizeNavigationDrawers(drawers, { isAdmin });
  const allowedPaths = ['/'];
  const dynamicRoutes = [];
  const diagnostics = {
    missingContractRoutes: [],
  };
  const registeredRoutes = new Set();

  let index = 0;
  normalizedDrawers.forEach((drawer) => {
    drawer.pages.forEach((page) => {
      const shellPath = normalizeRoutePath(page.route);
      if (shellPath === '/') {
        return;
      }

      const contract = getRouteContract(page.route);
      if (!contract) {
        diagnostics.missingContractRoutes.push(page.route);
      }

      const renderMode = 'native';
      dynamicRoutes.push({
        routeName: `shell-page-${index++}`,
        shellPath,
        targetRoute: page.route,
        pageName: page.name || contract?.title || page.route,
        drawerName: drawer.name || drawer.id || '',
        owner: contract?.owner || '',
        renderMode,
        routeId: contract?.routeId || '',
      });
      registeredRoutes.add(page.route);
      allowedPaths.push(shellPath);
    });
  });

  if (includeStandaloneDrilldown) {
    STANDALONE_DRILLDOWN_ROUTES.forEach((route) => {
      if (registeredRoutes.has(route)) {
        return;
      }

      const shellPath = normalizeRoutePath(route);
      if (shellPath === '/') {
        return;
      }

      const contract = getRouteContract(route);
      if (!contract) {
        diagnostics.missingContractRoutes.push(route);
      }

      dynamicRoutes.push({
        routeName: `shell-page-${index++}`,
        shellPath,
        targetRoute: route,
        pageName: contract?.title || route,
        drawerName: '',
        owner: contract?.owner || '',
        renderMode: 'native',
        routeId: contract?.routeId || '',
      });
      registeredRoutes.add(route);
      allowedPaths.push(shellPath);
    });
  }

  diagnostics.missingContractRoutes = [...new Set(diagnostics.missingContractRoutes)].sort();
  return {
    drawers: normalizedDrawers,
    dynamicRoutes,
    allowedPaths: [...new Set(allowedPaths)],
    diagnostics,
  };
}

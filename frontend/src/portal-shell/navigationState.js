import { getRouteContract, normalizeRoutePath } from './routeContracts.js';
import { drawers as manifestDrawers, routes as manifestRoutes } from './navigationManifest.js';

const STANDALONE_DRILLDOWN_ROUTES = Object.freeze([
  '/wip-detail',
  '/hold-detail',
  '/anomaly-overview',
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

/**
 * Build the merged drawer array from the manifest structure and a runtime
 * status map returned by GET /api/portal/navigation.
 *
 * Supported call forms:
 *   (A) normalizeNavigationDrawers(drawerList, statusMap, { isAdmin })
 *       drawerList = manifest drawers array (no .pages — pages come from manifestRoutes)
 *   (B) normalizeNavigationDrawers(legacyDrawers, { isAdmin })
 *       legacyDrawers = old-style drawers[] that already have .pages[] on them
 *       (backward compat for existing unit tests that pass drawer objects with pages)
 *
 * Mode is detected by the second argument:
 *   - object with only isAdmin/includeStandaloneDrilldown keys → form (B) legacy
 *   - otherwise → form (A) new
 *
 * @param {Array} drawerListOrLegacy
 * @param {Record<string,string>|{isAdmin?:boolean}} statusMapOrOptions
 * @param {{isAdmin?:boolean}} [options]
 */
export function normalizeNavigationDrawers(
  drawerListOrLegacy,
  statusMapOrOptions,
  options,
) {
  // Detect legacy call: normalizeNavigationDrawers(legacyDrawers, { isAdmin })
  // where only two args are passed and second arg has only isAdmin/includeStandaloneDrilldown keys.
  // If a third `options` arg is explicitly provided (not undefined), we are in the new
  // (manifest, statusMap, options) form even if statusMap happens to be empty {}.
  const isLegacyPagesCall =
    options === undefined &&
    statusMapOrOptions !== null &&
    typeof statusMapOrOptions === 'object' &&
    !Array.isArray(statusMapOrOptions) &&
    Object.keys(statusMapOrOptions).every(
      (k) => k === 'isAdmin' || k === 'includeStandaloneDrilldown',
    );

  let resolvedStatusMap;
  let effectiveIsAdmin;
  let useLegacyPagesMode; // true = use drawer.pages[] directly (old format)

  if (isLegacyPagesCall || statusMapOrOptions === undefined) {
    // Legacy mode: second arg is options, drawers already have .pages[]
    resolvedStatusMap = {};
    effectiveIsAdmin = Boolean((statusMapOrOptions || {}).isAdmin);
    useLegacyPagesMode = true;
  } else {
    resolvedStatusMap =
      typeof statusMapOrOptions === 'object' ? statusMapOrOptions : {};
    effectiveIsAdmin = Boolean((options || {}).isAdmin);
    useLegacyPagesMode = false;
  }

  const drawerList = Array.isArray(drawerListOrLegacy) ? drawerListOrLegacy : manifestDrawers;

  if (useLegacyPagesMode) {
    // Legacy path: use drawer.pages[] arrays directly (existing test behaviour)
    const normalizedDrawers = sortByOrderThenName(drawerList).flatMap((drawer) => {
      const drawerId = String(drawer?.id || '').trim();
      if (!drawerId) return [];

      const adminOnly = Boolean(drawer?.admin_only);
      if (adminOnly && !effectiveIsAdmin) return [];

      const pages = Array.isArray(drawer?.pages) ? drawer.pages : [];
      const normalizedPages = sortByOrderThenName(pages).flatMap((page) => {
        const route = String(page?.route || '').trim();
        if (!route || !route.startsWith('/')) return [];
        if (!canViewPage(page?.status, effectiveIsAdmin)) return [];
        return [{
          route,
          name: page?.name || route,
          status: page?.status || 'dev',
          order: safeInt(page?.order),
        }];
      });

      if (!normalizedPages.length) return [];

      return [{
        id: drawerId,
        name: drawer?.name || drawerId,
        order: safeInt(drawer?.order),
        admin_only: adminOnly,
        pages: normalizedPages,
      }];
    });
    return normalizedDrawers;
  }

  // New path: build pages from manifestRoutes + statusMap
  const pagesByDrawer = {};
  const routeEntries = manifestRoutes || {};
  for (const [route, meta] of Object.entries(routeEntries)) {
    const dId = meta.drawerId;
    if (!dId) continue; // standalone / drilldown — excluded from drawer menu
    const defaultStatus = meta.defaultStatus || 'released';
    const runtimeStatus = resolvedStatusMap[route];
    const status = runtimeStatus !== undefined ? runtimeStatus : defaultStatus;
    if (!pagesByDrawer[dId]) pagesByDrawer[dId] = [];
    pagesByDrawer[dId].push({
      route,
      order: meta.order,
      name: meta.displayName || route,
      status,
    });
  }

  const normalizedDrawers = sortByOrderThenName(drawerList).flatMap((drawer) => {
    const drawerId = String(drawer?.id || '').trim();
    if (!drawerId) return [];

    const adminOnly = Boolean(drawer?.admin_only);
    if (adminOnly && !effectiveIsAdmin) return [];

    const rawPages = pagesByDrawer[drawerId] || [];
    const normalizedPages = sortByOrderThenName(rawPages).flatMap((page) => {
      const route = String(page?.route || '').trim();
      if (!route || !route.startsWith('/')) return [];
      if (!canViewPage(page?.status, effectiveIsAdmin)) return [];
      return [{
        route,
        name: page?.name || route,
        status: page?.status || 'dev',
        order: safeInt(page?.order),
      }];
    });

    if (!normalizedPages.length) return [];

    return [{
      id: drawerId,
      name: drawer?.name || drawerId,
      order: safeInt(drawer?.order),
      admin_only: adminOnly,
      pages: normalizedPages,
    }];
  });

  return normalizedDrawers;
}

/**
 * Build the full dynamic navigation state from a manifest structure and
 * a runtime status map (from GET /api/portal/navigation).
 *
 * Preferred signature (from router.js / App.vue):
 *   buildDynamicNavigationState(statusMap, { isAdmin, includeStandaloneDrilldown })
 *     where statusMap is a plain object (route → status).
 *     The manifest drawers array is imported automatically from navigationManifest.js.
 *
 * Legacy signature (existing unit tests pass an array of drawer objects):
 *   buildDynamicNavigationState(drawers[], { isAdmin, includeStandaloneDrilldown })
 *     In this case drawers is used as-is (old API still works for tests).
 *
 * @param {Array|Record<string,string>} drawersOrStatusMap
 * @param {{isAdmin?:boolean, includeStandaloneDrilldown?:boolean}} options
 */
export function buildDynamicNavigationState(
  drawersOrStatusMap,
  { isAdmin = false, includeStandaloneDrilldown = false } = {},
) {
  // Detect call mode by first argument type:
  //   array  → legacy: drawers[]  (backward compat for unit tests)
  //   object → new:    statusMap  (from App.vue / syncNavigationRoutes)
  const isLegacyDrawersArray = Array.isArray(drawersOrStatusMap);

  let resolvedStatusMap;
  let resolvedManifestStructure;

  if (isLegacyDrawersArray) {
    // Legacy: drawers[] was passed directly (existing tests)
    resolvedStatusMap = {};
    resolvedManifestStructure = drawersOrStatusMap; // use passed drawers directly
  } else {
    // New: statusMap object passed; use manifest drawers from import
    resolvedStatusMap =
      drawersOrStatusMap && typeof drawersOrStatusMap === 'object' ? drawersOrStatusMap : {};
    resolvedManifestStructure = manifestDrawers; // from navigationManifest.js import
  }

  const normalizedDrawers = isLegacyDrawersArray
    // Legacy path: call with two args so normalizeNavigationDrawers uses drawer.pages[] directly
    ? normalizeNavigationDrawers(resolvedManifestStructure, { isAdmin })
    // New path: call with three args so normalizeNavigationDrawers uses manifestRoutes + statusMap
    : normalizeNavigationDrawers(resolvedManifestStructure, resolvedStatusMap, { isAdmin });

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

      const renderMode = contract?.renderMode || 'native';
      dynamicRoutes.push({
        routeName: `shell-page-${index++}`,
        shellPath,
        targetRoute: page.route,
        pageName: page.name || contract?.title || page.route,
        drawerName: drawer.name || drawer.id || '',
        owner: contract?.owner || '',
        renderMode,
        routeId: contract?.routeId || '',
        visibilityPolicy: contract?.visibilityPolicy || 'released_or_admin',
        scope: contract?.scope || 'unknown',
        compatibilityPolicy: contract?.compatibilityPolicy || 'legacy_direct_entry_allowed',
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
        renderMode: contract?.renderMode || 'native',
        routeId: contract?.routeId || '',
        visibilityPolicy: contract?.visibilityPolicy || 'released_or_admin',
        scope: contract?.scope || 'unknown',
        compatibilityPolicy: contract?.compatibilityPolicy || 'legacy_direct_entry_allowed',
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

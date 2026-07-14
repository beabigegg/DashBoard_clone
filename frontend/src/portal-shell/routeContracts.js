const IN_SCOPE_REPORT_ROUTES = Object.freeze([
  '/wip-overview',
  '/wip-detail',
  '/hold-overview',
  '/hold-detail',
  '/hold-history',
  '/reject-history',
  '/resource',
  '/resource-history',
  '/qc-gate',
  '/job-query',
  '/query-tool',
  '/mid-section-defect',
  '/material-trace',
  '/yield-alert-center',
  '/anomaly-overview',
  '/production-history',
  '/material-consumption',
  '/downtime-analysis',
  '/eap-alarm',
  '/uph-performance',
  '/login',
]);

const IN_SCOPE_ADMIN_ROUTES = Object.freeze([
  '/admin/pages',
  '/admin/dashboard',
  '/admin/performance',
]);

const DEFERRED_ROUTES = Object.freeze([]);

const ALL_KNOWN_ROUTES = Object.freeze([
  ...IN_SCOPE_REPORT_ROUTES,
  ...IN_SCOPE_ADMIN_ROUTES,
  ...DEFERRED_ROUTES,
]);

function buildContract({
  route,
  routeId,
  title,
  owner,
  renderMode,
  rollbackStrategy,
  visibilityPolicy,
  scope,
  compatibilityPolicy,
}) {
  return Object.freeze({
    routeId,
    route,
    title,
    owner,
    renderMode,
    rollbackStrategy,
    visibilityPolicy,
    scope,
    compatibilityPolicy,
    canonicalShellPath: `/portal-shell${route}`,
  });
}

const ROUTE_CONTRACTS = Object.freeze({
  '/wip-overview': buildContract({
    route: '/wip-overview',
    routeId: 'wip-overview',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'WIP 即時概況',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/wip-detail': buildContract({
    route: '/wip-detail',
    routeId: 'wip-detail',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'WIP 詳細列表',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/hold-overview': buildContract({
    route: '/hold-overview',
    routeId: 'hold-overview',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 即時概況',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/hold-detail': buildContract({
    route: '/hold-detail',
    routeId: 'hold-detail',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 詳細查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/hold-history': buildContract({
    route: '/hold-history',
    routeId: 'hold-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 歷史報表',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/reject-history': buildContract({
    route: '/reject-history',
    routeId: 'reject-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '報廢歷史查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/resource': buildContract({
    route: '/resource',
    routeId: 'resource',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備即時狀況',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/resource-history': buildContract({
    route: '/resource-history',
    routeId: 'resource-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備歷史績效',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/qc-gate': buildContract({
    route: '/qc-gate',
    routeId: 'qc-gate',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'QC-GATE 狀態',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/job-query': buildContract({
    route: '/job-query',
    routeId: 'job-query',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備維修查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/admin/pages': buildContract({
    route: '/admin/pages',
    routeId: 'admin-pages',
    renderMode: 'native',
    owner: 'frontend-platform-admin',
    title: '頁面管理',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'admin_only',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/admin/dashboard': buildContract({
    route: '/admin/dashboard',
    routeId: 'admin-dashboard',
    renderMode: 'native',
    owner: 'frontend-platform-admin',
    title: '管理儀表板',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'admin_only',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/query-tool': buildContract({
    route: '/query-tool',
    routeId: 'query-tool',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Query Tool',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/mid-section-defect': buildContract({
    route: '/mid-section-defect',
    routeId: 'mid-section-defect',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '製程不良追溯分析',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/material-trace': buildContract({
    route: '/material-trace',
    routeId: 'material-trace',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '原物料追溯查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/yield-alert-center': buildContract({
    route: '/yield-alert-center',
    routeId: 'yield-alert-center',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '良率查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/anomaly-overview': buildContract({
    route: '/anomaly-overview',
    routeId: 'anomaly-overview',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '異常總覽',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/production-history': buildContract({
    route: '/production-history',
    routeId: 'production-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '生產歷程查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/material-consumption': buildContract({
    route: '/material-consumption',
    routeId: 'material-consumption',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '料號用量報表',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/downtime-analysis': buildContract({
    route: '/downtime-analysis',
    routeId: 'downtime-analysis',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備停機分析',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/eap-alarm': buildContract({
    route: '/eap-alarm',
    routeId: 'eap-alarm',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'EAP ALARM 分析',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/login': buildContract({
    route: '/login',
    routeId: 'login',
    renderMode: 'native',
    owner: 'frontend-platform-admin',
    title: 'Login',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/admin/performance': buildContract({
    route: '/admin/performance',
    routeId: 'admin-performance',
    renderMode: 'native',
    owner: 'frontend-platform-admin',
    title: '效能監控',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'admin_only',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/db-scheduling': buildContract({
    route: '/db-scheduling',
    routeId: 'db-scheduling',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'DB 生產排程助手',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/production-achievement': buildContract({
    route: '/production-achievement',
    routeId: 'production-achievement',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '生產達成率',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/uph-performance': buildContract({
    route: '/uph-performance',
    routeId: 'uph-performance',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'UPH表現',
    rollbackStrategy: 'fallback_to_legacy_route',
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
  '/production-achievement-settings': buildContract({
    route: '/production-achievement-settings',
    routeId: 'production-achievement-settings',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '生產達成率 - 對照設定',
    rollbackStrategy: 'fallback_to_legacy_route',
    // Standalone drilldown (D4, no drawer entry) — same whitelisted-edit/
    // read-only-else visibility as the report page itself: any released user
    // can view it (state-settings-readonly), write access is gated
    // server-side by can_edit_targets (editForbidden, first-403 fail-closed),
    // never a route-level admin_only gate.
    visibilityPolicy: 'released_or_admin',
    scope: 'in-scope',
    compatibilityPolicy: 'redirect_to_shell_when_spa_enabled',
  }),
});

const REQUIRED_FIELDS = Object.freeze([
  'routeId',
  'route',
  'title',
  'owner',
  'renderMode',
  'rollbackStrategy',
  'visibilityPolicy',
  'scope',
  'compatibilityPolicy',
  'canonicalShellPath',
]);

const VALID_RENDER_MODES = new Set(['native', 'external']);
const VALID_VISIBILITY_POLICIES = new Set(['released_or_admin', 'admin_only']);
const VALID_SCOPES = new Set(['in-scope', 'deferred']);

export function normalizeRoutePath(route) {
  const normalized = String(route || '').trim();
  if (!normalized || normalized === '/') {
    return '/';
  }
  return `/${normalized.replace(/^\/+/, '')}`;
}

export function getRouteContract(route) {
  return ROUTE_CONTRACTS[normalizeRoutePath(route)] || null;
}

export function getRouteContractMap() {
  return ROUTE_CONTRACTS;
}

export function getInScopeRoutes() {
  return [...IN_SCOPE_REPORT_ROUTES, ...IN_SCOPE_ADMIN_ROUTES];
}

export function getDeferredRoutes() {
  return [...DEFERRED_ROUTES];
}

export function getKnownRoutes() {
  return [...ALL_KNOWN_ROUTES];
}

export function validateRouteContractMap({ inScopeOnly = false } = {}) {
  const entries = Object.entries(ROUTE_CONTRACTS).filter(([, contract]) => {
    if (!inScopeOnly) {
      return true;
    }
    return contract.scope === 'in-scope';
  });

  const errors = [];
  entries.forEach(([path, contract]) => {
    REQUIRED_FIELDS.forEach((field) => {
      if (!String(contract?.[field] ?? '').trim()) {
        errors.push(`${path}: missing required field ${field}`);
      }
    });

    if (contract.route !== path) {
      errors.push(`${path}: route field does not match key`);
    }
    if (!VALID_RENDER_MODES.has(contract.renderMode)) {
      errors.push(`${path}: invalid renderMode ${contract.renderMode}`);
    }
    if (!VALID_VISIBILITY_POLICIES.has(contract.visibilityPolicy)) {
      errors.push(`${path}: invalid visibilityPolicy ${contract.visibilityPolicy}`);
    }
    if (!VALID_SCOPES.has(contract.scope)) {
      errors.push(`${path}: invalid scope ${contract.scope}`);
    }
    if (contract.canonicalShellPath !== `/portal-shell${path}`) {
      errors.push(`${path}: canonicalShellPath mismatch`);
    }
  });

  return [...new Set(errors)].sort();
}

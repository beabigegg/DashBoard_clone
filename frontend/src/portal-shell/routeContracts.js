const ROUTE_CONTRACTS = Object.freeze({
  '/wip-overview': {
    routeId: 'wip-overview',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'WIP 即時概況',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/wip-detail': {
    routeId: 'wip-detail',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'WIP 詳細列表',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/hold-overview': {
    routeId: 'hold-overview',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 即時概況',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/hold-detail': {
    routeId: 'hold-detail',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 詳細查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/hold-history': {
    routeId: 'hold-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Hold 歷史報表',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/resource': {
    routeId: 'resource',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備即時狀況',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/resource-history': {
    routeId: 'resource-history',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備歷史績效',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/qc-gate': {
    routeId: 'qc-gate',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'QC-GATE 狀態',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/job-query': {
    routeId: 'job-query',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: '設備維修查詢',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/excel-query': {
    routeId: 'excel-query',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Excel 查詢工具',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/query-tool': {
    routeId: 'query-tool',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'Query Tool',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
  '/tmtt-defect': {
    routeId: 'tmtt-defect',
    renderMode: 'native',
    owner: 'frontend-mes-reporting',
    title: 'TMTT Defect',
    rollbackStrategy: 'fallback_to_legacy_route',
  },
});

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

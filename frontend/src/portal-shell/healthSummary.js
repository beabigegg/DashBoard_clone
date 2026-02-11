export function labelFromHealthStatus(status) {
  if (status === 'healthy') return '連線正常';
  if (status === 'degraded') return '部分降級';
  if (status === 'loading') return '檢查中...';
  return '連線異常';
}

export function normalizeFrontendShellHealth(shellData) {
  const summary = shellData?.summary || {};
  const detail = shellData?.detail || shellData || {};
  const status = summary?.status || shellData?.status || 'unhealthy';
  const errors = Array.isArray(detail?.errors) ? detail.errors : [];
  return {
    status,
    errors,
  };
}

export function buildHealthFallbackDetail() {
  return {
    status: 'unhealthy',
    label: '無法連線',
    detail: {
      database: '無法確認',
      redis: '無法確認',
      cacheEnabled: '無法確認',
      cacheUpdatedAt: '--',
      resourceCacheEnabled: '無法確認',
      resourceCacheCount: '--',
      routeCacheMode: '--',
      routeCacheHitRate: '--',
      routeCacheDegraded: '--',
      frontendShell: '無法確認',
    },
  };
}

function createNativeLoader(componentLoader, styleLoaders = []) {
  let styleBootstrapPromise = null;
  let componentModuleCache = null;

  return async () => {
    if (!styleBootstrapPromise) {
      styleBootstrapPromise = Promise.all(styleLoaders.map((loadStyle) => loadStyle())).catch((error) => {
        styleBootstrapPromise = null;
        throw error;
      });
    }
    await styleBootstrapPromise;
    if (!componentModuleCache) {
      componentModuleCache = await componentLoader();
    }
    return componentModuleCache;
  };
}

const NATIVE_MODULE_LOADERS = Object.freeze({
  '/wip-overview': createNativeLoader(
    () => import('../wip-overview/App.vue'),
    [() => import('../wip-overview/style.css')],
  ),
  '/wip-detail': createNativeLoader(
    () => import('../wip-detail/App.vue'),
    [() => import('../wip-detail/style.css')],
  ),
  '/hold-overview': createNativeLoader(
    () => import('../hold-overview/App.vue'),
    [() => import('../resource-shared/styles.css'), () => import('../wip-shared/styles.css'), () => import('../hold-overview/style.css')],
  ),
  '/hold-detail': createNativeLoader(
    () => import('../hold-detail/App.vue'),
    [() => import('../hold-detail/style.css')],
  ),
  '/hold-history': createNativeLoader(
    () => import('../hold-history/App.vue'),
    [() => import('../wip-shared/styles.css'), () => import('../hold-history/style.css')],
  ),
  '/reject-history': createNativeLoader(
    () => import('../reject-history/App.vue'),
    [() => import('../wip-shared/styles.css'), () => import('../reject-history/style.css')],
  ),
  '/resource': createNativeLoader(
    () => import('../resource-status/App.vue'),
    [() => import('../resource-shared/styles.css'), () => import('../resource-status/style.css')],
  ),
  '/resource-history': createNativeLoader(
    () => import('../resource-history/App.vue'),
    [() => import('../resource-shared/styles.css'), () => import('../resource-history/style.css')],
  ),
  '/qc-gate': createNativeLoader(
    () => import('../qc-gate/App.vue'),
    [() => import('../qc-gate/style.css')],
  ),
  '/job-query': createNativeLoader(
    () => import('../job-query/App.vue'),
    [() => import('../resource-shared/styles.css'), () => import('../job-query/style.css')],
  ),
  '/query-tool': createNativeLoader(
    () => import('../query-tool/App.vue'),
    [() => import('../wip-shared/styles.css'), () => import('../styles/tailwind.css'), () => import('../query-tool/style.css')],
  ),
  '/mid-section-defect': createNativeLoader(
    () => import('../mid-section-defect/App.vue'),
    [() => import('../mid-section-defect/style.css')],
  ),
  '/material-trace': createNativeLoader(
    () => import('../material-trace/App.vue'),
    [() => import('../wip-shared/styles.css'), () => import('../material-trace/style.css')],
  ),
  '/yield-alert-center': createNativeLoader(
    () => import('../yield-alert-center/App.vue'),
    [() => import('../wip-shared/styles.css'), () => import('../resource-shared/styles.css'), () => import('../yield-alert-center/style.css')],
  ),
  '/anomaly-overview': createNativeLoader(
    () => import('../anomaly-overview/App.vue'),
    [() => import('../anomaly-overview/style.css')],
  ),
  '/production-history': createNativeLoader(
    () => import('../production-history/App.vue'),
    [() => import('../resource-shared/styles.css'), () => import('../styles/tailwind.css'), () => import('../wip-shared/styles.css'), () => import('../production-history/style.css')],
  ),
  '/material-consumption': createNativeLoader(
    () => import('../material-consumption/App.vue'),
    [() => import('../material-consumption/style.css')],
  ),
  '/downtime-analysis': createNativeLoader(
    () => import('../downtime-analysis/App.vue'),
    [() => import('../downtime-analysis/style.css')],
  ),
  '/admin/dashboard': createNativeLoader(
    () => import('../admin-dashboard/App.vue'),
    [() => import('../styles/tailwind.css'), () => import('../admin-dashboard/style.css')],
  ),
  '/admin/pages': createNativeLoader(
    () => import('../admin-pages/App.vue'),
    [() => import('../styles/tailwind.css'), () => import('../admin-pages/style.css')],
  ),
});

export function getNativeModuleLoader(route) {
  return NATIVE_MODULE_LOADERS[String(route || '').trim()] || null;
}

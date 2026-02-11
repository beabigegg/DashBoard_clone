function normalizeTargetPath(path) {
  const normalized = String(path || '').trim();
  if (!normalized) {
    return '/';
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
}

function toShellRouterPath(path) {
  const normalized = normalizeTargetPath(path);
  if (!normalized.startsWith('/portal-shell')) {
    return normalized;
  }

  const stripped = normalized.slice('/portal-shell'.length);
  if (!stripped) {
    return '/';
  }
  return stripped.startsWith('/') ? stripped : `/${stripped}`;
}

function getShellRouterBridge() {
  const bridge = window.__MES_PORTAL_SHELL_NAVIGATE__;
  return typeof bridge === 'function' ? bridge : null;
}

export function isPortalShellRuntime(currentPathname = null) {
  const pathname = currentPathname ?? window.location.pathname;
  return String(pathname || '').startsWith('/portal-shell');
}

export function toRuntimeRoute(path, { currentPathname = null } = {}) {
  const normalized = normalizeTargetPath(path);
  if (normalized.startsWith('/portal-shell')) {
    return normalized;
  }
  if (isPortalShellRuntime(currentPathname)) {
    return `/portal-shell${normalized}`;
  }
  return normalized;
}

export function navigateToRuntimeRoute(path, { replace = false } = {}) {
  const target = toRuntimeRoute(path);
  const shellRouterBridge = getShellRouterBridge();

  if (shellRouterBridge && isPortalShellRuntime()) {
    shellRouterBridge(toShellRouterPath(target), { replace });
    return;
  }

  if (replace) {
    window.location.replace(target);
    return;
  }
  window.location.href = target;
}

export function replaceRuntimeHistory(path) {
  const target = toRuntimeRoute(path);
  window.history.replaceState({}, '', target);
}

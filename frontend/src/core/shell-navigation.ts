function normalizeTargetPath(path: string | null | undefined): string {
  const normalized = String(path || '').trim();
  if (!normalized) {
    return '/';
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
}

function toShellRouterPath(path: string): string {
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

function getShellRouterBridge(): ((path: string, options?: { replace?: boolean }) => void) | null {
  const bridge = window.__MES_PORTAL_SHELL_NAVIGATE__;
  return typeof bridge === 'function' ? bridge : null;
}

export function isPortalShellRuntime(currentPathname: string | null = null): boolean {
  const pathname = currentPathname ?? window.location.pathname;
  return String(pathname || '').startsWith('/portal-shell');
}

export interface ToRuntimeRouteOptions {
  currentPathname?: string | null;
}

export function toRuntimeRoute(
  path: string,
  { currentPathname = null }: ToRuntimeRouteOptions = {}
): string {
  const normalized = normalizeTargetPath(path);
  if (normalized.startsWith('/portal-shell')) {
    return normalized;
  }
  if (isPortalShellRuntime(currentPathname)) {
    return `/portal-shell${normalized}`;
  }
  return normalized;
}

export interface NavigateOptions {
  replace?: boolean;
}

export function navigateToRuntimeRoute(path: string, { replace = false }: NavigateOptions = {}): void {
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

const URL_SAFE_LENGTH = 2000;
const URL_STATE_KEY_PREFIX = 'url-state:';

export function replaceRuntimeHistory(path: string): void {
  const target = toRuntimeRoute(path);

  // Guard: if URL exceeds safe length, spill query params to sessionStorage
  if (target.length > URL_SAFE_LENGTH) {
    const qIndex = path.indexOf('?');
    if (qIndex !== -1) {
      const logicalPathname = path.slice(0, qIndex);
      const query = path.slice(qIndex + 1);
      const storageKey = URL_STATE_KEY_PREFIX + logicalPathname;
      try {
        sessionStorage.setItem(storageKey, query);
      } catch {
        // sessionStorage unavailable — fall through to full URL
      }
      window.history.replaceState({}, '', toRuntimeRoute(logicalPathname + '?_s=1'));
      return;
    }
  }

  window.history.replaceState({}, '', target);
}

/**
 * Restore URL state spilled by replaceRuntimeHistory on previous navigation.
 * Call synchronously before app mount so initializePage reads the full params.
 */
export function restoreUrlState(): void {
  const params = new URLSearchParams(window.location.search);
  if (params.get('_s') !== '1') {
    return;
  }

  const logicalPathname = toShellRouterPath(window.location.pathname);
  const storageKey = URL_STATE_KEY_PREFIX + logicalPathname;

  try {
    const stored = sessionStorage.getItem(storageKey);
    sessionStorage.removeItem(storageKey);
    const newSearch = stored ? '?' + stored : '';
    window.history.replaceState({}, '', window.location.pathname + newSearch);
  } catch {
    window.history.replaceState({}, '', window.location.pathname);
  }
}

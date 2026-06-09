export const SIDEBAR_STORAGE_KEY = 'portal-shell:sidebar-collapsed';
export const MOBILE_BREAKPOINT = 900;

export function isMobileViewport(width, breakpoint = MOBILE_BREAKPOINT) {
  return Number(width) <= breakpoint;
}

export function parseSidebarCollapsedPreference(value) {
  return String(value).trim() === 'true';
}

export function serializeSidebarCollapsedPreference(collapsed) {
  return collapsed ? 'true' : 'false';
}

export function buildSidebarUiState({ sidebarOpen }) {
  const open = Boolean(sidebarOpen);
  return {
    shellClass: { 'sidebar-is-open': open },
    sidebarClass: {
      'sidebar--open': open,
    },
    sidebarVisible: open,
    ariaExpanded: open ? 'true' : 'false',
  };
}

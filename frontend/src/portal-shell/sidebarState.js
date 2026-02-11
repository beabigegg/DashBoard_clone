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

export function buildSidebarUiState({ isMobile, sidebarCollapsed, sidebarMobileOpen }) {
  const mobile = Boolean(isMobile);
  const desktopCollapsed = !mobile && Boolean(sidebarCollapsed);
  const mobileOpen = mobile && Boolean(sidebarMobileOpen);
  const sidebarVisible = mobile ? mobileOpen : !desktopCollapsed;

  return {
    shellClass: {
      'sidebar-collapsed': desktopCollapsed,
    },
    sidebarClass: {
      'sidebar--collapsed': desktopCollapsed,
      'sidebar--mobile-open': mobileOpen,
      'sidebar--mobile-closed': mobile && !mobileOpen,
    },
    sidebarVisible,
    ariaExpanded: sidebarVisible ? 'true' : 'false',
  };
}

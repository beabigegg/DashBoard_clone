import { type InjectionKey, inject, onUnmounted, provide, reactive, watch, type WatchSource } from 'vue';

interface UpdateBadgeState {
  updateTime: string;
  refreshing: boolean;
  refreshSuccess: boolean;
  refreshError: boolean;
}

interface BindOptions {
  updateTime: WatchSource<string>;
  refreshing?: WatchSource<boolean> | (() => boolean);
  refreshSuccess?: WatchSource<boolean> | (() => boolean);
  refreshError?: WatchSource<boolean> | (() => boolean);
}

const UPDATE_BADGE_KEY: InjectionKey<UpdateBadgeState> = Symbol('mes-update-badge');

export function provideUpdateBadge(): UpdateBadgeState {
  const state = reactive<UpdateBadgeState>({
    updateTime: '--',
    refreshing: false,
    refreshSuccess: false,
    refreshError: false,
  });
  provide(UPDATE_BADGE_KEY, state);
  return state;
}

export function useUpdateBadge(): UpdateBadgeState | null {
  return inject(UPDATE_BADGE_KEY, null);
}

/**
 * Binds feature-app state refs to the portal-shell breadcrumb badge.
 * Resets badge on unmount so navigating away clears the display.
 */
export function bindUpdateBadge({ updateTime, refreshing, refreshSuccess, refreshError }: BindOptions): void {
  const badge = useUpdateBadge();
  if (!badge) return;

  watch(updateTime, (val) => { badge.updateTime = val ?? '--'; }, { immediate: true });
  if (refreshing !== undefined) {
    watch(refreshing as WatchSource<boolean>, (val) => { badge.refreshing = !!val; }, { immediate: true });
  }
  if (refreshSuccess !== undefined) {
    watch(refreshSuccess as WatchSource<boolean>, (val) => { badge.refreshSuccess = !!val; }, { immediate: true });
  }
  if (refreshError !== undefined) {
    watch(refreshError as WatchSource<boolean>, (val) => { badge.refreshError = !!val; }, { immediate: true });
  }

  onUnmounted(() => {
    badge.updateTime = '--';
    badge.refreshing = false;
    badge.refreshSuccess = false;
    badge.refreshError = false;
  });
}

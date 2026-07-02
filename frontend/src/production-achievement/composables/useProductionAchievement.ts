/**
 * useProductionAchievement — filter state + report/target fetch orchestration
 * for the 生產達成率 report page.
 *
 * Modeled on production-history's filter-orchestration pattern but WITHOUT the
 * async-job/spool machinery (explicit non-goal — this is an ordinary
 * synchronous filterable report, not an auto-refresh kanban).
 *
 * Endpoints (api-contract.md rows 256-261):
 *   GET /api/production-achievement/report?start_date&end_date&shift_code&workcenter_group
 *   GET /api/production-achievement/filter-options
 *   GET /api/production-achievement/targets?shift_code&workcenter_group
 *   PUT /api/production-achievement/targets  { shift_code, workcenter_group, target_qty }
 */
import { reactive, ref } from 'vue';
import { apiGet } from '../../core/api';
import type { ApiResponse } from '../../core/types';

export interface ProductionAchievementReportRow {
  output_date: string;
  shift_code: string;
  workcenter_group: string;
  actual_output_qty: number;
  target_qty: number | null;
  achievement_rate: number | null;
}

export interface ProductionAchievementTargetRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number;
  updated_at: string;
  updated_by: string;
}

export interface FilterState {
  start_date: string;
  end_date: string;
  shift_code: string;
  workcenter_group: string;
}

const DEFAULT_SHIFT_CODES = ['N', 'D', 'A', 'B', 'C'];

function getCsrfToken(): string {
  return (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null)?.content ?? '';
}

interface PutError extends Error {
  status: number;
  errorCode: string | null;
}

/**
 * core/api.ts's apiPost() hardcodes method: 'POST' (no PUT override hook), so
 * PUT requests use a small dedicated helper — same CSRF-header + envelope
 * pattern as the existing admin-pages/App.vue putJson() precedent.
 */
async function apiPut<T>(url: string, payload: unknown): Promise<ApiResponse<T>> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(payload) });
  let body: ApiResponse<T> | null = null;
  try {
    body = await resp.json();
  } catch {
    // empty/non-JSON body — fall through to the status-based error below
  }
  if (!resp.ok || (body && body.success === false)) {
    const message =
      (body && !body.success ? body.error?.message : undefined) || `HTTP ${resp.status}`;
    const err = new Error(message) as PutError;
    err.status = resp.status;
    err.errorCode = (body && !body.success ? body.error?.code : null) || null;
    throw err;
  }
  return body as ApiResponse<T>;
}

function defaultDateRange(): { start: string; end: string } {
  const today = new Date();
  const end = today.toISOString().slice(0, 10);
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  return { start: monthAgo.toISOString().slice(0, 10), end };
}

export function useProductionAchievement() {
  const { start, end } = defaultDateRange();

  const filters = reactive<FilterState>({
    start_date: start,
    end_date: end,
    shift_code: '',
    workcenter_group: '',
  });

  const filterOptions = reactive<{ shift_codes: string[]; workcenter_groups: string[] }>({
    shift_codes: [...DEFAULT_SHIFT_CODES],
    workcenter_groups: [],
  });

  const rows = ref<ProductionAchievementReportRow[]>([]);
  const targets = ref<ProductionAchievementTargetRow[]>([]);
  const loading = ref(false);
  const error = ref('');
  const hasQueried = ref(false);

  // Permission is not pre-checkable via a dedicated contract endpoint for a
  // non-admin user (api-contract.md only exposes GET .../targets, ungated,
  // and the admin-only GET .../permissions). The edit control is shown
  // optimistically and this flag is flipped to false the first time a PUT
  // 403s, so a stale permission cache never lets the user retry silently.
  const editForbidden = ref(false);
  const editError = ref('');
  const editSaving = ref(false);

  async function fetchFilterOptions(): Promise<void> {
    try {
      const res = await apiGet<{ shift_codes?: string[]; workcenter_groups?: string[] }>(
        '/api/production-achievement/filter-options',
      );
      if (res.success) {
        const data = (res.data ?? {}) as { shift_codes?: string[]; workcenter_groups?: string[] };
        if (Array.isArray(data.shift_codes) && data.shift_codes.length > 0) {
          filterOptions.shift_codes = data.shift_codes;
        }
        filterOptions.workcenter_groups = Array.isArray(data.workcenter_groups) ? data.workcenter_groups : [];
      }
    } catch {
      // Fail-open on filter-options load: keep the default shift-code enum,
      // leave workcenter_groups empty (user can still submit with no filter).
    }
  }

  async function fetchTargets(): Promise<void> {
    try {
      const res = await apiGet<ProductionAchievementTargetRow[]>('/api/production-achievement/targets');
      if (res.success) {
        targets.value = Array.isArray(res.data) ? res.data : [];
      }
    } catch {
      // GET targets degrades server-side to null target_qty; a network-level
      // failure here just leaves the local target list empty (view-only, no crash).
      targets.value = [];
    }
  }

  async function runQuery(): Promise<void> {
    if (loading.value) return;
    error.value = '';
    loading.value = true;
    hasQueried.value = true;
    try {
      const res = await apiGet<ProductionAchievementReportRow[]>('/api/production-achievement/report', {
        params: {
          start_date: filters.start_date,
          end_date: filters.end_date,
          shift_code: filters.shift_code || undefined,
          workcenter_group: filters.workcenter_group || undefined,
        },
      });
      if (res.success) {
        rows.value = Array.isArray(res.data) ? res.data : [];
      } else {
        rows.value = [];
        error.value = (res as { error?: { message?: string } }).error?.message || '查詢失敗，請稍後再試';
      }
    } catch (err: unknown) {
      rows.value = [];
      error.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
    } finally {
      loading.value = false;
    }
  }

  async function saveTarget(payload: { shift_code: string; workcenter_group: string; target_qty: number }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await apiPut<null>('/api/production-achievement/targets', payload);
      await fetchTargets();
      // Re-query so the achievement_rate reflects the new target immediately.
      if (hasQueried.value) await runQuery();
      return true;
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      const code = (err as { errorCode?: string | null })?.errorCode;
      if (status === 403 || code === 'FORBIDDEN') {
        // A 403 that slips through the proactive UI (e.g. stale permission
        // cache) is handled gracefully here: disable further edit attempts
        // for the rest of the session rather than retrying silently.
        editForbidden.value = true;
        editError.value = '您沒有編輯目標值的權限';
      } else if (status === 503) {
        editError.value = '目標值服務暫時無法使用，請稍後再試';
      } else if (status === 400) {
        editError.value = err instanceof Error ? err.message : '目標值格式錯誤';
      } else {
        editError.value = err instanceof Error ? err.message : '儲存失敗，請稍後再試';
      }
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  function resetFilters(): void {
    const { start: s, end: e } = defaultDateRange();
    filters.start_date = s;
    filters.end_date = e;
    filters.shift_code = '';
    filters.workcenter_group = '';
    rows.value = [];
    hasQueried.value = false;
    error.value = '';
  }

  return {
    filters,
    filterOptions,
    rows,
    targets,
    loading,
    error,
    hasQueried,
    editForbidden,
    editError,
    editSaving,
    fetchFilterOptions,
    fetchTargets,
    runQuery,
    saveTarget,
    resetFilters,
  };
}

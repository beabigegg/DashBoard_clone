/**
 * useProductionAchievementSettings — data fetch/write orchestration for the
 * standalone /production-achievement-settings mini-app.
 *
 * Change: production-achievement-overhaul (IP-9). Mirrors the
 * admin-dashboard smart-page/dumb-panel split and TargetEditPanel.vue's
 * fail-closed `editForbidden` shape (optimistic edit, flips to read-only on
 * the FIRST 403 from ANY of the 3 tables — one shared flag, "one language
 * everywhere" per interaction-design.md § Consistency Commitments).
 *
 * OD-5: a successful write sets `saveNote` to a "changes apply on the next
 * data refresh" message (shown once, dismissible) — no spool-refresh-on-save.
 * OD-6: no unsaved-edit navigation guard (matches TargetEditPanel precedent;
 * nothing here listens for beforeunload/route-leave).
 * OD-8: `workcenterFullList` cross-references `known-workcenter-groups`
 * (the full raw universe) against `workcenter-merge-map` (currently-included
 * rows) so WorkcenterMergeMappingPanel can render an include/exclude toggle
 * for every raw group, not just the ~12 already included.
 * OD-12: `packageLfGroupOptions`/`workcenterGroupOptions` are the constrained
 * dropdown sources for DailyPlanPanel's new-row form (no free-text option).
 *
 * Endpoints (api-contract.md rows 273-282, data-shape-contract.md §3.30-§3.34):
 *   GET/PUT/DELETE /api/production-achievement/package-lf-map[/<raw>]
 *   GET/PUT/DELETE /api/production-achievement/workcenter-merge-map[/<raw>]
 *   GET/PUT        /api/production-achievement/daily-plans
 *   POST           /api/production-achievement/daily-plans/import/preview
 *   POST           /api/production-achievement/daily-plans/import/confirm
 *   GET            /api/production-achievement/known-package-lf-values
 *   GET            /api/production-achievement/known-workcenter-groups
 */
import { computed, ref } from 'vue';
import { apiGet, apiPost, apiUpload } from '../../core/api';
import type { ApiResponse } from '../../core/types';

export interface PackageLfMapRow {
  raw_package_lf: string;
  merged_group: string;
  updated_at: string;
  updated_by: string;
}

export interface WorkcenterMergeMapRow {
  raw_workcenter_group: string;
  merged_workcenter_group: string;
  /** PA-19: the 大項 this子站 rolls up under (電鍍/切割 for their sub-stations;
   *  otherwise === merged_workcenter_group). */
  parent_group: string;
  updated_at: string;
  updated_by: string;
}

export interface DailyPlanRow {
  workcenter_group: string;
  package_lf_group: string;
  daily_plan_qty: number;
  updated_at: string;
  updated_by: string;
}

export interface WorkcenterFullListRow {
  raw_workcenter_group: string;
  included: boolean;
  merged_workcenter_group: string | null;
  parent_group: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

// ── Excel-import for DailyPlanPanel (business-rules.md PA-16) ──────────────
export type DailyPlanImportRowStatus =
  | 'new'
  | 'update'
  | 'unchanged'
  | 'invalid_workcenter'
  | 'invalid_package'
  | 'invalid_qty';

export interface DailyPlanImportRow {
  workcenter_group: string;
  package_lf_group: string;
  daily_plan_qty: number | null;
  current_qty: number | null;
  status: DailyPlanImportRowStatus;
  source_sheet: string;
  source_block: string;
  importable: boolean;
  default_selected: boolean;
  warning: string | null;
}

export interface DailyPlanMissingRow {
  workcenter_group: string;
  package_lf_group: string;
  daily_plan_qty: number;
}

export interface DailyPlanImportSummary {
  total_parsed: number;
  new: number;
  update: number;
  unchanged: number;
  invalid: number;
  missing_from_file: number;
}

export interface DailyPlanImportPreview {
  rows: DailyPlanImportRow[];
  missing_from_file: DailyPlanMissingRow[];
  summary: DailyPlanImportSummary;
}

const SAVE_NOTE_TEXT = '變更將於下次資料重新整理後套用';

function getCsrfToken(): string {
  return (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null)?.content ?? '';
}

interface WriteError extends Error {
  status: number;
  errorCode: string | null;
}

async function requestJson<T>(method: 'PUT' | 'DELETE', url: string, payload?: unknown): Promise<ApiResponse<T>> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (payload !== undefined) headers['Content-Type'] = 'application/json';
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { method, headers, body: payload !== undefined ? JSON.stringify(payload) : undefined });
  let body: ApiResponse<T> | null = null;
  try {
    body = await resp.json();
  } catch {
    // empty/non-JSON body — fall through to the status-based error below
  }
  if (!resp.ok || (body && body.success === false)) {
    const message = (body && !body.success ? body.error?.message : undefined) || `HTTP ${resp.status}`;
    const err = new Error(message) as WriteError;
    err.status = resp.status;
    err.errorCode = (body && !body.success ? body.error?.code : null) || null;
    throw err;
  }
  return body as ApiResponse<T>;
}

export function useProductionAchievementSettings() {
  const packageLfMap = ref<PackageLfMapRow[]>([]);
  const knownPackageLfValues = ref<string[]>([]);
  const workcenterMergeMap = ref<WorkcenterMergeMapRow[]>([]);
  const knownWorkcenterGroups = ref<string[]>([]);
  const dailyPlans = ref<DailyPlanRow[]>([]);

  const importPreview = ref<DailyPlanImportPreview | null>(null);
  const importLoading = ref(false);
  const importResult = ref<{ acknowledged: boolean; upserted: number } | null>(null);

  const loading = ref(false);
  const loadError = ref('');

  // Shared fail-closed permission state across ALL 3 panels (one language
  // everywhere — interaction-design.md § Consistency Commitments).
  const editForbidden = ref(false);
  const editError = ref('');
  const editSaving = ref(false);
  const saveNote = ref('');

  function dismissSaveNote(): void {
    saveNote.value = '';
  }

  function _handleWriteError(err: unknown): void {
    const status = (err as { status?: number })?.status;
    const code = (err as { errorCode?: string | null })?.errorCode;
    if (status === 403 || code === 'FORBIDDEN') {
      editForbidden.value = true;
      editError.value = '您沒有編輯權限';
    } else if (status === 503) {
      editError.value = '服務暫時無法使用，請稍後再試';
    } else if (status === 400) {
      editError.value = err instanceof Error ? err.message : '格式錯誤';
    } else {
      editError.value = err instanceof Error ? err.message : '儲存失敗，請稍後再試';
    }
  }

  async function fetchPackageLfMap(): Promise<void> {
    try {
      const res = await apiGet<PackageLfMapRow[]>('/api/production-achievement/package-lf-map');
      packageLfMap.value = res.success && Array.isArray(res.data) ? res.data : [];
    } catch {
      packageLfMap.value = [];
    }
  }

  async function fetchKnownPackageLfValues(): Promise<void> {
    try {
      const res = await apiGet<{ package_lf_values?: string[] }>('/api/production-achievement/known-package-lf-values');
      knownPackageLfValues.value = res.success && Array.isArray(res.data?.package_lf_values) ? res.data.package_lf_values : [];
    } catch {
      knownPackageLfValues.value = [];
    }
  }

  async function fetchWorkcenterMergeMap(): Promise<void> {
    try {
      const res = await apiGet<WorkcenterMergeMapRow[]>('/api/production-achievement/workcenter-merge-map');
      workcenterMergeMap.value = res.success && Array.isArray(res.data) ? res.data : [];
    } catch {
      workcenterMergeMap.value = [];
    }
  }

  async function fetchKnownWorkcenterGroups(): Promise<void> {
    try {
      const res = await apiGet<{ raw_workcenter_groups?: string[] }>('/api/production-achievement/known-workcenter-groups');
      knownWorkcenterGroups.value = res.success && Array.isArray(res.data?.raw_workcenter_groups) ? res.data.raw_workcenter_groups : [];
    } catch {
      knownWorkcenterGroups.value = [];
    }
  }

  async function fetchDailyPlans(): Promise<void> {
    try {
      const res = await apiGet<DailyPlanRow[]>('/api/production-achievement/daily-plans');
      dailyPlans.value = res.success && Array.isArray(res.data) ? res.data : [];
    } catch {
      dailyPlans.value = [];
    }
  }

  async function fetchAll(): Promise<void> {
    loading.value = true;
    loadError.value = '';
    try {
      await Promise.all([
        fetchPackageLfMap(),
        fetchKnownPackageLfValues(),
        fetchWorkcenterMergeMap(),
        fetchKnownWorkcenterGroups(),
        fetchDailyPlans(),
      ]);
    } finally {
      loading.value = false;
    }
  }

  // ── OD-8: full raw workcenter_group universe + include/exclude state ────
  const workcenterFullList = computed<WorkcenterFullListRow[]>(() => {
    const byRaw = new Map(workcenterMergeMap.value.map((r) => [r.raw_workcenter_group, r]));
    const allRaw = new Set<string>([...knownWorkcenterGroups.value, ...workcenterMergeMap.value.map((r) => r.raw_workcenter_group)]);
    return [...allRaw].sort().map((raw) => {
      const row = byRaw.get(raw);
      return {
        raw_workcenter_group: raw,
        included: !!row,
        merged_workcenter_group: row?.merged_workcenter_group ?? null,
        parent_group: row?.parent_group ?? null,
        updated_at: row?.updated_at ?? null,
        updated_by: row?.updated_by ?? null,
      };
    });
  });

  // ── PackageLfMappingPanel's "known-unmapped raw value" hint list ────────
  const packageLfUnmappedHints = computed<string[]>(() => {
    const mapped = new Set(packageLfMap.value.map((r) => r.raw_package_lf));
    return knownPackageLfValues.value.filter((v) => !mapped.has(v));
  });

  // ── OD-12: DailyPlanPanel's constrained dropdown sources (no free-text) ──
  const workcenterGroupOptions = computed<string[]>(() =>
    [...new Set(workcenterMergeMap.value.map((r) => r.merged_workcenter_group))].sort(),
  );
  const packageLfGroupOptions = computed<string[]>(() => {
    const merged = packageLfMap.value.map((r) => r.merged_group);
    const fallbackToSelf = packageLfUnmappedHints.value; // raw values with no merge row resolve to themselves (D1)
    return [...new Set([...merged, ...fallbackToSelf])].sort();
  });

  // ── Writes (all share the fail-closed editForbidden pattern) ────────────

  async function savePackageLf(payload: { raw_package_lf: string; merged_group: string }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await requestJson('PUT', '/api/production-achievement/package-lf-map', payload);
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchPackageLfMap();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  async function deletePackageLf(raw: string): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await requestJson('DELETE', `/api/production-achievement/package-lf-map/${encodeURIComponent(raw)}`);
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchPackageLfMap();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  async function saveWorkcenterMerge(payload: { raw_workcenter_group: string; merged_workcenter_group: string; parent_group?: string }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await requestJson('PUT', '/api/production-achievement/workcenter-merge-map', payload);
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchWorkcenterMergeMap();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  /** Excluding a group (D2) means removing its row — absence excludes it. */
  async function excludeWorkcenterGroup(raw: string): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await requestJson('DELETE', `/api/production-achievement/workcenter-merge-map/${encodeURIComponent(raw)}`);
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchWorkcenterMergeMap();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  async function saveDailyPlan(payload: { workcenter_group: string; package_lf_group: string; daily_plan_qty: number }): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      await requestJson('PUT', '/api/production-achievement/daily-plans', payload);
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchDailyPlans();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  // ── Excel-import: preview (parse-only, no write) → confirm (bulk upsert) ─
  // apiUpload/apiPost (core/api.ts) throw an ApiError with the same
  // {status, errorCode} shape requestJson()'s WriteError uses, so a 403 here
  // flows through the same _handleWriteError fail-closed path as every
  // other write in this composable.

  async function previewDailyPlanImport(file: File): Promise<boolean> {
    editError.value = '';
    importLoading.value = true;
    importPreview.value = null;
    importResult.value = null;
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await apiUpload<DailyPlanImportPreview>(
        '/api/production-achievement/daily-plans/import/preview',
        formData,
      );
      importPreview.value = res.success ? res.data : null;
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      importLoading.value = false;
    }
  }

  async function confirmDailyPlanImport(
    rows: { workcenter_group: string; package_lf_group: string; daily_plan_qty: number }[],
  ): Promise<boolean> {
    editError.value = '';
    editSaving.value = true;
    try {
      const res = await apiPost<{ acknowledged: boolean; upserted: number }>(
        '/api/production-achievement/daily-plans/import/confirm',
        { rows },
      );
      importResult.value = res.success ? res.data : null;
      saveNote.value = SAVE_NOTE_TEXT;
      await fetchDailyPlans();
      return true;
    } catch (err) {
      _handleWriteError(err);
      return false;
    } finally {
      editSaving.value = false;
    }
  }

  function dismissImportState(): void {
    importPreview.value = null;
    importResult.value = null;
  }

  // Plain object of refs/computed/functions — matches the established
  // useProductionAchievement()/useProductionAchievementDuckDB() convention
  // (not reactive()-wrapped; callers use `.value` in script, template refs
  // auto-unwrap as usual).
  return {
    packageLfMap,
    knownPackageLfValues,
    workcenterMergeMap,
    knownWorkcenterGroups,
    dailyPlans,
    importPreview,
    importLoading,
    importResult,
    loading,
    loadError,
    editForbidden,
    editError,
    editSaving,
    saveNote,
    workcenterFullList,
    packageLfUnmappedHints,
    workcenterGroupOptions,
    packageLfGroupOptions,
    fetchAll,
    savePackageLf,
    deletePackageLf,
    saveWorkcenterMerge,
    excludeWorkcenterGroup,
    saveDailyPlan,
    previewDailyPlanImport,
    confirmDailyPlanImport,
    dismissImportState,
    dismissSaveNote,
  };
}

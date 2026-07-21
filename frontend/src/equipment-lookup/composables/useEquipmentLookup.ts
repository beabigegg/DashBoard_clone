/**
 * useEquipmentLookup — composable for equipment-lookup (機台查詢) page
 *
 * API surface:
 *   loadOptions() → GET /api/equipment-lookup/options (locations/families/resource_names)
 *   submitQuery() → GET /api/equipment-lookup/list (sync, always; no cross-filter narrowing)
 *   handleSort()  → re-fetches page 1 with new sort_by/sort_dir
 *   handlePageChange() → re-fetches given page, preserving current filters/sort
 *   exportCsv()   → NO dedicated backend export endpoint. Re-fetches the full
 *                   current filtered set via page_size=10000 in one call, then
 *                   builds the CSV client-side and triggers a blob download.
 */

import { ref } from 'vue';
import { apiGet } from '../../core/api';

// --- Types ---
export interface EquipmentLookupOptions {
  locations: string[];
  families: string[];
  resource_names: string[];
}

export interface EquipmentRow {
  RESOURCENAME?: string | null;
  LOCATIONNAME?: string | null;
  RESOURCEFAMILYNAME?: string | null;
  VENDORNAME?: string | null;
  VENDORMODEL?: string | null;
  WORKCENTERNAME?: string | null;
  [key: string]: unknown;
}

export interface EquipmentPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ListFilters {
  locations: string[];
  families: string[];
  resource_names: string[];
}

const DEFAULT_PAGE_SIZE = 20;
const EXPORT_PAGE_SIZE = 10000;
const DEFAULT_SORT_BY = 'RESOURCENAME';
const DEFAULT_SORT_DIR = 'asc';

const EMPTY_PAGINATION: EquipmentPagination = {
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  total: 0,
  total_pages: 1,
};

// --- CSV export helpers (mirrors hold-overview/csvExport.ts pattern) ---
const CSV_HEADERS = ['編號', '機台位置', '機型', '供應商', '廠商型號', '工站'];
const CSV_KEYS = [
  'RESOURCENAME',
  'LOCATIONNAME',
  'RESOURCEFAMILYNAME',
  'VENDORNAME',
  'VENDORMODEL',
  'WORKCENTERNAME',
];

/** RFC 4180: quote values containing commas/quotes/newlines; double internal quotes. */
function toCsvField(value: unknown): string {
  const s = String(value ?? '');
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

/** Builds a full CSV string (header row always present, header-only when rows is empty). */
export function buildEquipmentCsv(rows: EquipmentRow[]): string {
  const headerLine = CSV_HEADERS.join(',');
  if (!Array.isArray(rows) || rows.length === 0) {
    return headerLine;
  }
  const dataLines = rows.map((row) => CSV_KEYS.map((key) => toCsvField(row[key])).join(','));
  return [headerLine, ...dataLines].join('\n');
}

/** Triggers a browser Blob download; prepends a UTF-8 BOM so Excel opens it correctly. */
function downloadCsv(content: string, filename: string): void {
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function useEquipmentLookup() {
  // --- Filter options state ---
  const options = ref<EquipmentLookupOptions>({ locations: [], families: [], resource_names: [] });
  const isOptionsLoading = ref(false);
  const optionsError = ref('');

  // --- List/query state ---
  const rows = ref<EquipmentRow[]>([]);
  const pagination = ref<EquipmentPagination>({ ...EMPTY_PAGINATION });
  const isListLoading = ref(false);
  const listError = ref('');
  const hasQueried = ref(false);

  const activeSortBy = ref(DEFAULT_SORT_BY);
  const activeSortDir = ref(DEFAULT_SORT_DIR);
  const currentFilters = ref<ListFilters>({ locations: [], families: [], resource_names: [] });

  const isExporting = ref(false);

  // --- Load filter dropdown options ---
  async function loadOptions(): Promise<void> {
    isOptionsLoading.value = true;
    optionsError.value = '';
    try {
      const res = await apiGet<EquipmentLookupOptions>('/api/equipment-lookup/options', {
        timeout: 30000,
      });
      if (!res.success) {
        optionsError.value =
          (res as { error?: { message?: string } }).error?.message || '篩選條件載入失敗';
        return;
      }
      const data = res.data!;
      options.value = {
        locations: data.locations ?? [],
        families: data.families ?? [],
        resource_names: data.resource_names ?? [],
      };
    } catch (err) {
      optionsError.value = err instanceof Error ? err.message : '篩選條件載入失敗';
    } finally {
      isOptionsLoading.value = false;
    }
  }

  /** fetchList — GET /api/equipment-lookup/list with the current filters/sort/page. */
  async function fetchList(page: number, sortBy: string, sortDir: string): Promise<void> {
    isListLoading.value = true;
    listError.value = '';
    activeSortBy.value = sortBy;
    activeSortDir.value = sortDir;
    try {
      const params: Record<string, unknown> = {
        locations: currentFilters.value.locations,
        families: currentFilters.value.families,
        resource_names: currentFilters.value.resource_names,
        page,
        page_size: DEFAULT_PAGE_SIZE,
        sort_by: sortBy,
        sort_dir: sortDir,
      };
      const result = await apiGet<{ rows: EquipmentRow[]; pagination: EquipmentPagination }>(
        '/api/equipment-lookup/list',
        { params, timeout: 30000 }
      );

      if (!result.success) {
        listError.value =
          (result as { error?: { message?: string } }).error?.message || '查詢失敗';
        return;
      }

      const data = result.data!;
      rows.value = data.rows ?? [];
      pagination.value = data.pagination ?? { ...EMPTY_PAGINATION };
    } catch (err) {
      listError.value = err instanceof Error ? err.message : '查詢失敗，請稍後再試';
    } finally {
      isListLoading.value = false;
    }
  }

  /** submitQuery — new filter submission from FilterPanel; resets sort/page to defaults. */
  async function submitQuery(filters: ListFilters): Promise<void> {
    currentFilters.value = filters;
    hasQueried.value = true;
    await fetchList(1, DEFAULT_SORT_BY, DEFAULT_SORT_DIR);
  }

  /** handleSort — server-side sort: re-fetch page 1 with the new ORDER BY. */
  async function handleSort(payload: { key: string; direction: string }): Promise<void> {
    if (!hasQueried.value) return;
    await fetchList(1, payload.key, payload.direction);
  }

  /** handlePageChange — preserves current filters/sort. */
  async function handlePageChange(page: number): Promise<void> {
    if (!hasQueried.value) return;
    await fetchList(page, activeSortBy.value, activeSortDir.value);
  }

  /** reset — clears query state back to the pre-query (initial) state. */
  function reset(): void {
    currentFilters.value = { locations: [], families: [], resource_names: [] };
    rows.value = [];
    pagination.value = { ...EMPTY_PAGINATION };
    hasQueried.value = false;
    listError.value = '';
    activeSortBy.value = DEFAULT_SORT_BY;
    activeSortDir.value = DEFAULT_SORT_DIR;
  }

  /**
   * exportCsv — no dedicated backend export endpoint (deliberate). Re-fetches
   * the full current filtered set in one call via page_size=10000, then
   * builds the CSV client-side and triggers a blob download.
   */
  async function exportCsv(): Promise<void> {
    isExporting.value = true;
    listError.value = '';
    try {
      const params: Record<string, unknown> = {
        locations: currentFilters.value.locations,
        families: currentFilters.value.families,
        resource_names: currentFilters.value.resource_names,
        page: 1,
        page_size: EXPORT_PAGE_SIZE,
        sort_by: activeSortBy.value,
        sort_dir: activeSortDir.value,
      };
      const result = await apiGet<{ rows: EquipmentRow[]; pagination: EquipmentPagination }>(
        '/api/equipment-lookup/list',
        { params, timeout: 60000 }
      );

      if (!result.success) {
        listError.value =
          (result as { error?: { message?: string } }).error?.message || '匯出失敗';
        return;
      }

      const exportRows = result.data?.rows ?? [];
      const csv = buildEquipmentCsv(exportRows);
      const today = new Date().toISOString().slice(0, 10);
      downloadCsv(csv, `equipment_lookup_${today}.csv`);
    } catch (err) {
      listError.value = err instanceof Error ? err.message : '匯出失敗，請稍後再試';
    } finally {
      isExporting.value = false;
    }
  }

  return {
    // Options
    options,
    isOptionsLoading,
    optionsError,
    loadOptions,

    // List
    rows,
    pagination,
    isListLoading,
    listError,
    hasQueried,
    activeSortBy,
    activeSortDir,
    submitQuery,
    handleSort,
    handlePageChange,
    reset,

    // Export
    isExporting,
    exportCsv,
  };
}

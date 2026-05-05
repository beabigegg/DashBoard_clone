const DEFAULT_LIMIT = 20;

const FIELD_MAP: Readonly<Record<string, string>> = Object.freeze({
  workorder: 'workorder',
  lotid: 'lotid',
  package: 'package',
  type: 'pj_type',
});

export type TimerHandle = ReturnType<typeof setTimeout> | null;

export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  wait = 300
): (...args: Parameters<T>) => void {
  let timer: TimerHandle = null;
  return (...args: Parameters<T>) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), wait);
  };
}

export interface WipAutocompleteFilters {
  workorder?: string;
  lotid?: string;
  package?: string;
  type?: string;
  [key: string]: string | undefined;
}

export interface WipAutocompleteParams {
  field: string;
  q: string;
  limit: number;
  [key: string]: string | number;
}

export function buildWipAutocompleteParams(
  searchType: string,
  query: string,
  filters: WipAutocompleteFilters = {},
  limit = DEFAULT_LIMIT
): WipAutocompleteParams | null {
  const keyword = (query || '').trim();
  if (keyword.length < 2) {
    return null;
  }

  const params: WipAutocompleteParams = {
    field: FIELD_MAP[searchType] || searchType,
    q: keyword,
    limit,
  };

  const filterKeys = ['workorder', 'lotid', 'package', 'type'];
  filterKeys.forEach((key) => {
    const value = ((filters[key] || '') as string).trim();
    if (key !== searchType && value) {
      params[key] = value;
    }
  });

  return params;
}

export interface FetchWipAutocompleteOptions {
  searchType: string;
  query: string;
  filters?: WipAutocompleteFilters;
  request: (url: string, options: { params: WipAutocompleteParams; silent: boolean; retries: number }) => Promise<unknown>;
  limit?: number;
}

export async function fetchWipAutocompleteItems(
  options: FetchWipAutocompleteOptions
): Promise<unknown[]> {
  const { searchType, query, filters, request, limit = DEFAULT_LIMIT } = options;
  const params = buildWipAutocompleteParams(searchType, query, filters, limit);
  if (!params) {
    return [];
  }
  try {
    const result = await request('/api/wip/meta/search', {
      params,
      silent: true,
      retries: 0,
    });
    const r = result as { success?: boolean; data?: { items?: unknown[] } } | null | undefined;
    if (r?.success) {
      return r?.data?.items || [];
    }
    return [];
  } catch {
    return [];
  }
}

export { FIELD_MAP as WIP_AUTOCOMPLETE_FIELD_MAP };

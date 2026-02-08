const DEFAULT_LIMIT = 20;

const FIELD_MAP = Object.freeze({
  workorder: 'workorder',
  lotid: 'lotid',
  package: 'package',
  type: 'pj_type'
});

export function debounce(fn, wait = 300) {
  let timer = null;
  return (...args) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function buildWipAutocompleteParams(searchType, query, filters = {}, limit = DEFAULT_LIMIT) {
  const keyword = (query || '').trim();
  if (keyword.length < 2) {
    return null;
  }

  const params = {
    field: FIELD_MAP[searchType] || searchType,
    q: keyword,
    limit
  };

  const filterKeys = ['workorder', 'lotid', 'package', 'type'];
  filterKeys.forEach((key) => {
    const value = (filters[key] || '').trim();
    if (key !== searchType && value) {
      params[key] = value;
    }
  });

  return params;
}

export async function fetchWipAutocompleteItems({
  searchType,
  query,
  filters,
  request,
  limit = DEFAULT_LIMIT,
}) {
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
    if (result?.success) {
      return result?.data?.items || [];
    }
    return [];
  } catch {
    return [];
  }
}

export { FIELD_MAP as WIP_AUTOCOMPLETE_FIELD_MAP };

import { reactive } from 'vue';

import { debounce, fetchWipAutocompleteItems } from '../../core/autocomplete.js';
import { apiGet } from '../../core/api.js';

function createFieldState() {
  return {
    query: '',
    items: [],
    loading: false,
    open: false,
  };
}

export function useAutocomplete({
  getFilters = () => ({}),
  request = (url, options) => apiGet(url, options),
  debounceMs = 300,
  minChars = 2,
} = {}) {
  const fields = reactive({});
  const debouncedSearchers = new Map();

  function ensureField(type) {
    if (!fields[type]) {
      fields[type] = createFieldState();
    }
    return fields[type];
  }

  async function search(type, rawQuery) {
    const field = ensureField(type);
    const query = String(rawQuery ?? '').trim();

    if (query.length < minChars) {
      field.loading = false;
      field.items = [];
      field.open = false;
      return [];
    }

    field.loading = true;
    const items = await fetchWipAutocompleteItems({
      searchType: type,
      query,
      filters: getFilters(),
      request,
    });

    field.items = Array.isArray(items) ? items : [];
    field.open = true;
    field.loading = false;
    return field.items;
  }

  function getDebouncedSearcher(type) {
    if (!debouncedSearchers.has(type)) {
      debouncedSearchers.set(
        type,
        debounce((query) => {
          void search(type, query);
        }, debounceMs)
      );
    }
    return debouncedSearchers.get(type);
  }

  function handleInput(type, value) {
    const field = ensureField(type);
    field.query = value;

    if (String(value ?? '').trim().length < minChars) {
      field.open = false;
      field.items = [];
      return;
    }

    getDebouncedSearcher(type)(value);
  }

  function handleFocus(type) {
    const field = ensureField(type);
    if (String(field.query ?? '').trim().length >= minChars) {
      void search(type, field.query);
    }
  }

  function handleBlur(type, delayMs = 200) {
    setTimeout(() => {
      const field = ensureField(type);
      field.open = false;
    }, delayMs);
  }

  function selectItem(type, value) {
    const field = ensureField(type);
    field.query = value;
    field.open = false;
    return value;
  }

  function setValue(type, value) {
    const field = ensureField(type);
    field.query = value ?? '';
  }

  function clearField(type) {
    const field = ensureField(type);
    field.query = '';
    field.items = [];
    field.open = false;
  }

  function hideAll() {
    Object.keys(fields).forEach((key) => {
      fields[key].open = false;
    });
  }

  return {
    fields,
    ensureField,
    search,
    handleInput,
    handleFocus,
    handleBlur,
    selectItem,
    setValue,
    clearField,
    hideAll,
  };
}

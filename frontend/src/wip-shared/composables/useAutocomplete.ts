import { reactive } from 'vue';

import { debounce, fetchWipAutocompleteItems } from '../../core/autocomplete';
import type { WipAutocompleteFilters, WipAutocompleteParams } from '../../core/autocomplete';
import { apiGet } from '../../core/api';
import type { FetchOptions } from '../../core/api';

interface UseAutocompleteOptions {
  getFilters?: () => Record<string, unknown>;
  request?: (url: string, options: { params: WipAutocompleteParams; silent: boolean; retries: number }) => Promise<unknown>;
  debounceMs?: number;
  minChars?: number;
}

interface FieldState {
  query: string;
  items: string[];
  loading: boolean;
  open: boolean;
}

function createFieldState(): FieldState {
  return {
    query: '',
    items: [],
    loading: false,
    open: false,
  };
}

const defaultRequest = (url: string, options?: FetchOptions) => apiGet(url, options);

export function useAutocomplete({
  getFilters = () => ({}),
  request = defaultRequest as UseAutocompleteOptions['request'],
  debounceMs = 300,
  minChars = 2,
}: UseAutocompleteOptions = {}) {
  const fields = reactive<Record<string, FieldState>>({});
  const debouncedSearchers = new Map<string, (...args: unknown[]) => unknown>();

  function ensureField(type: string): FieldState {
    if (!fields[type]) {
      fields[type] = createFieldState();
    }
    return fields[type];
  }

  async function search(type: string, rawQuery: unknown): Promise<string[]> {
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
      filters: getFilters() as WipAutocompleteFilters,
      request: request!,
    });

    field.items = Array.isArray(items) ? (items as string[]) : [];
    field.open = true;
    field.loading = false;
    return field.items;
  }

  function getDebouncedSearcher(type: string): (...args: unknown[]) => unknown {
    if (!debouncedSearchers.has(type)) {
      debouncedSearchers.set(
        type,
        debounce((...args: unknown[]) => {
          void search(type, args[0]);
        }, debounceMs)
      );
    }
    return debouncedSearchers.get(type)!;
  }

  function handleInput(type: string, value: string): void {
    const field = ensureField(type);
    field.query = value;

    if (String(value ?? '').trim().length < minChars) {
      field.open = false;
      field.items = [];
      return;
    }

    getDebouncedSearcher(type)(value);
  }

  function handleFocus(type: string): void {
    const field = ensureField(type);
    if (String(field.query ?? '').trim().length >= minChars) {
      void search(type, field.query);
    }
  }

  function handleBlur(type: string, delayMs = 200): void {
    setTimeout(() => {
      const field = ensureField(type);
      field.open = false;
    }, delayMs);
  }

  function selectItem(type: string, value: string): string {
    const field = ensureField(type);
    field.query = value;
    field.open = false;
    return value;
  }

  function setValue(type: string, value: string | null | undefined): void {
    const field = ensureField(type);
    field.query = value ?? '';
  }

  function clearField(type: string): void {
    const field = ensureField(type);
    field.query = '';
    field.items = [];
    field.open = false;
  }

  function hideAll(): void {
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

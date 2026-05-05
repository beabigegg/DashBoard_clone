// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error wip-shared is not yet TypeScript — Phase 1c will migrate it
import { useAutocomplete as useAutocompleteBase } from '../wip-shared/composables/useAutocomplete.js';

export interface AutocompleteFieldState {
  query: string;
  items: string[];
  loading: boolean;
  open: boolean;
}

export interface AutocompleteOptions {
  getFilters?: () => Record<string, unknown>;
  request?: (url: string, options?: unknown) => Promise<unknown>;
  debounceMs?: number;
  minChars?: number;
  [key: string]: unknown;
}

export interface AutocompleteComposable {
  fields: Record<string, AutocompleteFieldState>;
  ensureField: (type: string) => AutocompleteFieldState;
  search: (type: string, rawQuery: string) => Promise<string[]>;
  handleInput: (type: string, value: string) => void;
  handleFocus: (type: string) => void;
  handleBlur: (type: string, delayMs?: number) => void;
  selectItem: (type: string, value: string) => string;
  setValue: (type: string, value: string | null | undefined) => void;
  clearField: (type: string) => void;
  hideAll: () => void;
}

export function useAutocomplete(options: AutocompleteOptions = {}): AutocompleteComposable {
  return useAutocompleteBase(options) as AutocompleteComposable;
}

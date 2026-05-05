import rawContracts from '../../../shared/field_contracts.json';

// TODO: type this more precisely once field_contracts.json schema is documented
// The JSON has shape { [pageKey: string]: { [sectionKey: string]: FieldContract[] } }
const contracts = rawContracts as Record<string, Record<string, FieldContract[]>> || {};

export interface FieldContract {
  api_key: string;
  ui_label?: string;
  export_header?: string;
  [key: string]: unknown; // TODO: type remaining field contract fields
}

export function getPageContract(pageKey: string, sectionKey: string): FieldContract[] {
  const page = contracts[pageKey] || {};
  const section = page[sectionKey] || [];
  return Array.isArray(section) ? section : [];
}

export function getFieldContractByApiKey(
  pageKey: string,
  sectionKey: string,
  apiKey: string
): FieldContract | null {
  return getPageContract(pageKey, sectionKey).find((field) => field.api_key === apiKey) || null;
}

export function getUiHeaders(pageKey: string, sectionKey: string): string[] {
  return getPageContract(pageKey, sectionKey).map((field) => field.ui_label || field.api_key);
}

export function getExportHeaders(pageKey: string): string[] {
  return getPageContract(pageKey, 'export').map(
    (field) => field.export_header || field.ui_label || field.api_key
  );
}

export function getContractRegistry(): Record<string, Record<string, FieldContract[]>> {
  return contracts;
}

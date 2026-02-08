import rawContracts from '../../../shared/field_contracts.json';

const contracts = rawContracts || {};

export function getPageContract(pageKey, sectionKey) {
  const page = contracts[pageKey] || {};
  const section = page[sectionKey] || [];
  return Array.isArray(section) ? section : [];
}

export function getFieldContractByApiKey(pageKey, sectionKey, apiKey) {
  return getPageContract(pageKey, sectionKey).find((field) => field.api_key === apiKey) || null;
}

export function getUiHeaders(pageKey, sectionKey) {
  return getPageContract(pageKey, sectionKey).map((field) => field.ui_label || field.api_key);
}

export function getExportHeaders(pageKey) {
  return getPageContract(pageKey, 'export').map((field) => field.export_header || field.ui_label || field.api_key);
}

export function getContractRegistry() {
  return contracts;
}

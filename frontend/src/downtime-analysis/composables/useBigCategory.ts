/**
 * useBigCategory — client-side 8-bucket big-category map mirror.
 *
 * Mirrors the backend's _BIG_CATEGORY_MAP frozendict and _match_prefix_categories list.
 * Source of truth: design.md §Big-category taxonomy (DA-04).
 *
 * Important: strip OLDREASONNAME trailing CHAR spaces before lookup (Oracle CHAR pads to fixed width).
 */

export const BIG_CATEGORY_MAP: Record<string, string> = {
  // 維修
  'EE Repair': '維修',
  'EAP Minor stoppage': '維修',
  // 保養
  'EE_PM': '保養',
  'MF_PM': '保養',
  'PD_PM': '保養',
  // 換型換線
  'Change Type': '換型換線',
  'Change Package': '換型換線',
  'Re Layout': '換型換線',
  'Change Marking Code': '換型換線',
  'Change Model': '換型換線',
  // 換刀清模
  'Change Tool/Consumables': '換刀清模',
  'Clean Mold': '換刀清模',
  // 檢查 (non-TMTT_ reasons)
  'Prod_QC_Inspection': '檢查',
  'Prod_PD_inspection': '檢查',
  // 待料待指示
  'Wait For Instructions': '待料待指示',
  'No Operator': '待料待指示',
  'No Raw Material': '待料待指示',
};

/** Prefix-based categories (order matters: first match wins) */
const PREFIX_CATEGORIES: Array<[string, string]> = [
  ['TMTT_', '檢查'],
];

const FALLBACK_CATEGORY = '其他/未分類';

/**
 * Map a single reason + status to a big category.
 * - EGT status always maps to '工程' regardless of reason (DA-04).
 * - Strip trailing whitespace from reason before lookup (Oracle CHAR padding).
 * - Unknown reasons map to '其他/未分類'.
 */
export function getBigCategory(reason: string | null | undefined, status?: string): string {
  // EGT always maps to '工程'
  if (status && status.trim() === 'EGT') {
    return '工程';
  }

  if (!reason) return FALLBACK_CATEGORY;

  // Strip Oracle CHAR trailing spaces before lookup
  const stripped = reason.trim();
  if (!stripped) return FALLBACK_CATEGORY;

  // Direct map lookup
  if (stripped in BIG_CATEGORY_MAP) {
    return BIG_CATEGORY_MAP[stripped];
  }

  // Prefix match (TMTT_* → 檢查)
  for (const [prefix, category] of PREFIX_CATEGORIES) {
    if (stripped.startsWith(prefix)) {
      return category;
    }
  }

  return FALLBACK_CATEGORY;
}

/**
 * All 8 canonical big categories (in display order).
 */
export const ALL_BIG_CATEGORIES: readonly string[] = [
  '維修',
  '保養',
  '換型換線',
  '換刀清模',
  '檢查',
  '待料待指示',
  '工程',
  '其他/未分類',
];

/**
 * Composable: useBigCategory
 * Returns the category-mapping utilities for use in Vue components.
 */
export function useBigCategory() {
  return {
    getBigCategory,
    allCategories: ALL_BIG_CATEGORIES,
    fallbackCategory: FALLBACK_CATEGORY,
  };
}

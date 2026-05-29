import { describe, it, expect } from 'vitest';
import { getBigCategory, ALL_BIG_CATEGORIES, BIG_CATEGORY_MAP, useBigCategory } from '../composables/useBigCategory';

describe('getBigCategory — 8-bucket mapping (DA-04)', () => {
  describe('維修 bucket', () => {
    it('maps EE Repair → 維修', () => {
      expect(getBigCategory('EE Repair')).toBe('維修');
    });
    it('maps EAP Minor stoppage → 維修', () => {
      expect(getBigCategory('EAP Minor stoppage')).toBe('維修');
    });
  });

  describe('保養 bucket', () => {
    it('maps EE_PM → 保養', () => {
      expect(getBigCategory('EE_PM')).toBe('保養');
    });
    it('maps MF_PM → 保養', () => {
      expect(getBigCategory('MF_PM')).toBe('保養');
    });
    it('maps PD_PM → 保養', () => {
      expect(getBigCategory('PD_PM')).toBe('保養');
    });
  });

  describe('換型換線 bucket', () => {
    it('maps Change Type → 換型換線', () => {
      expect(getBigCategory('Change Type')).toBe('換型換線');
    });
    it('maps Change Package → 換型換線', () => {
      expect(getBigCategory('Change Package')).toBe('換型換線');
    });
    it('maps Re Layout → 換型換線', () => {
      expect(getBigCategory('Re Layout')).toBe('換型換線');
    });
    it('maps Change Marking Code → 換型換線', () => {
      expect(getBigCategory('Change Marking Code')).toBe('換型換線');
    });
    it('maps Change Model → 換型換線', () => {
      expect(getBigCategory('Change Model')).toBe('換型換線');
    });
  });

  describe('換刀清模 bucket', () => {
    it('maps Change Tool/Consumables → 換刀清模', () => {
      expect(getBigCategory('Change Tool/Consumables')).toBe('換刀清模');
    });
    it('maps Clean Mold → 換刀清模', () => {
      expect(getBigCategory('Clean Mold')).toBe('換刀清模');
    });
  });

  describe('檢查 bucket', () => {
    it('maps Prod_QC_Inspection → 檢查', () => {
      expect(getBigCategory('Prod_QC_Inspection')).toBe('檢查');
    });
    it('maps Prod_PD_inspection → 檢查', () => {
      expect(getBigCategory('Prod_PD_inspection')).toBe('檢查');
    });
    it('maps TMTT_Check → 檢查 (prefix match)', () => {
      expect(getBigCategory('TMTT_Check')).toBe('檢查');
    });
    it('maps TMTT_Inspection_001 → 檢查 (prefix match)', () => {
      expect(getBigCategory('TMTT_Inspection_001')).toBe('檢查');
    });
    it('maps TMTT_ prefix with CHAR-padded trailing spaces → 檢查', () => {
      // Simulates Oracle CHAR padding: strip() must happen before startsWith
      expect(getBigCategory('TMTT_Check  ')).toBe('檢查');
    });
  });

  describe('待料待指示 bucket', () => {
    it('maps Wait For Instructions → 待料待指示', () => {
      expect(getBigCategory('Wait For Instructions')).toBe('待料待指示');
    });
    it('maps No Operator → 待料待指示', () => {
      expect(getBigCategory('No Operator')).toBe('待料待指示');
    });
    it('maps No Raw Material → 待料待指示', () => {
      expect(getBigCategory('No Raw Material')).toBe('待料待指示');
    });
  });

  describe('工程 bucket — EGT status always maps to 工程 regardless of reason', () => {
    it('EGT status + known reason → 工程 (status overrides reason)', () => {
      expect(getBigCategory('EE Repair', 'EGT')).toBe('工程');
    });
    it('EGT status + unknown reason → 工程', () => {
      expect(getBigCategory('Unknown Reason', 'EGT')).toBe('工程');
    });
    it('EGT status + null reason → 工程', () => {
      expect(getBigCategory(null, 'EGT')).toBe('工程');
    });
    it('EGT status with leading/trailing spaces → 工程', () => {
      expect(getBigCategory('EE Repair', ' EGT ')).toBe('工程');
    });
  });

  describe('其他/未分類 fallback', () => {
    it('unknown reason → 其他/未分類', () => {
      expect(getBigCategory('Some Unknown Reason')).toBe('其他/未分類');
    });
    it('null reason → 其他/未分類', () => {
      expect(getBigCategory(null)).toBe('其他/未分類');
    });
    it('empty string → 其他/未分類', () => {
      expect(getBigCategory('')).toBe('其他/未分類');
    });
    it('blank/whitespace-only string → 其他/未分類', () => {
      expect(getBigCategory('   ')).toBe('其他/未分類');
    });
    it('undefined → 其他/未分類', () => {
      expect(getBigCategory(undefined)).toBe('其他/未分類');
    });
  });

  describe('Oracle CHAR trailing-space stripping', () => {
    it('EE Repair with 8 trailing CHAR spaces → 維修 (not 其他/未分類)', () => {
      // Oracle CHAR(20) pads 'EE Repair' to 20 chars with spaces
      expect(getBigCategory('EE Repair        ')).toBe('維修');
    });
    it('EE_PM with trailing spaces → 保養', () => {
      expect(getBigCategory('EE_PM   ')).toBe('保養');
    });
  });
});

describe('ALL_BIG_CATEGORIES — all 8 buckets present', () => {
  const expected = ['維修', '保養', '換型換線', '換刀清模', '檢查', '待料待指示', '工程', '其他/未分類'];

  it('contains exactly 8 categories', () => {
    expect(ALL_BIG_CATEGORIES).toHaveLength(8);
  });

  for (const cat of expected) {
    it(`contains '${cat}'`, () => {
      expect(ALL_BIG_CATEGORIES).toContain(cat);
    });
  }
});

describe('BIG_CATEGORY_MAP — membership completeness', () => {
  it('every mapped reason resolves correctly', () => {
    for (const [reason, expected] of Object.entries(BIG_CATEGORY_MAP)) {
      expect(getBigCategory(reason)).toBe(expected);
    }
  });
});

describe('useBigCategory composable', () => {
  it('returns getBigCategory, allCategories, fallbackCategory', () => {
    const { getBigCategory: fn, allCategories, fallbackCategory } = useBigCategory();
    expect(typeof fn).toBe('function');
    expect(Array.isArray(allCategories)).toBe(true);
    expect(fallbackCategory).toBe('其他/未分類');
  });
});

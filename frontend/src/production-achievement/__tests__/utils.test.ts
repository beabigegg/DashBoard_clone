import { describe, it, expect } from 'vitest';
import {
  formatQty,
  formatAchievementRate,
  achievementRateForChart,
  validateTargetQtyInput,
} from '../utils';

describe('formatQty', () => {
  it('formats a finite number with locale grouping', () => {
    expect(formatQty(12345)).toBe('12,345');
  });

  it('renders "—" for null (missing target_qty)', () => {
    expect(formatQty(null)).toBe('—');
  });

  it('renders "—" for undefined', () => {
    expect(formatQty(undefined)).toBe('—');
  });

  it('renders "—" for non-finite values (defensive)', () => {
    expect(formatQty(Number.POSITIVE_INFINITY)).toBe('—');
    expect(formatQty(Number.NaN)).toBe('—');
  });

  it('renders 0 for zero actual_output_qty (not null)', () => {
    expect(formatQty(0)).toBe('0');
  });
});

describe('formatAchievementRate', () => {
  it('formats a ratio as a percentage with 1 decimal', () => {
    expect(formatAchievementRate(0.873)).toBe('87.3%');
  });

  it('renders "—" for null (missing or zero target)', () => {
    expect(formatAchievementRate(null)).toBe('—');
  });

  it('renders "—" for undefined', () => {
    expect(formatAchievementRate(undefined)).toBe('—');
  });

  it('never renders Infinity even if a bad value slips through', () => {
    expect(formatAchievementRate(Number.POSITIVE_INFINITY)).toBe('—');
  });

  it('never renders NaN even if a bad value slips through', () => {
    expect(formatAchievementRate(Number.NaN)).toBe('—');
  });

  it('renders 0.0% for zero-output/nonzero-target (achievement rate 0)', () => {
    expect(formatAchievementRate(0)).toBe('0.0%');
  });
});

describe('achievementRateForChart', () => {
  it('scales a ratio to a 0..100 number for chart series', () => {
    expect(achievementRateForChart(0.5)).toBe(50);
  });

  it('degrades null to 0 (no bar height) instead of throwing/NaN', () => {
    expect(achievementRateForChart(null)).toBe(0);
    expect(achievementRateForChart(undefined)).toBe(0);
    expect(achievementRateForChart(Number.POSITIVE_INFINITY)).toBe(0);
  });
});

describe('validateTargetQtyInput', () => {
  it('accepts a valid non-negative integer string', () => {
    expect(validateTargetQtyInput('100')).toBe('');
    expect(validateTargetQtyInput('0')).toBe('');
  });

  it('rejects empty input', () => {
    expect(validateTargetQtyInput('')).not.toBe('');
    expect(validateTargetQtyInput('   ')).not.toBe('');
  });

  it('rejects non-numeric input', () => {
    expect(validateTargetQtyInput('abc')).not.toBe('');
    expect(validateTargetQtyInput('12abc')).not.toBe('');
  });

  it('rejects negative input', () => {
    expect(validateTargetQtyInput('-1')).not.toBe('');
    expect(validateTargetQtyInput('-100')).not.toBe('');
  });

  it('rejects non-integer (decimal) input', () => {
    expect(validateTargetQtyInput('1.5')).not.toBe('');
  });
});

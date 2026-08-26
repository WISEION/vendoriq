import { describe, expect, it } from 'vitest';
import { formatDate, formatMoney, formatNumber } from './format';

describe('formatNumber', () => {
  it('groups thousands and drops decimals', () => {
    expect(formatNumber(4500000, 'en')).toBe('4,500,000');
    expect(formatNumber(4500000, 'az')).toBe('4.500.000');
  });

  it('renders an em dash for an unknown amount', () => {
    expect(formatNumber(null, 'en')).toBe('—');
    expect(formatNumber(undefined, 'en')).toBe('—');
    expect(formatNumber(Number.NaN, 'en')).toBe('—');
  });
});

describe('formatMoney', () => {
  it('appends the AZN suffix', () => {
    expect(formatMoney(600000, 'en')).toBe('600,000 AZN');
  });

  it('renders an em dash for an unknown amount, not "— AZN"', () => {
    expect(formatMoney(null, 'en')).toBe('—');
  });
});

describe('formatDate', () => {
  it('renders an em dash for a missing date', () => {
    expect(formatDate(null, 'en')).toBe('—');
    expect(formatDate(undefined, 'en')).toBe('—');
  });

  it('formats a real date', () => {
    expect(formatDate('2026-08-24', 'en')).toContain('2026');
  });
});

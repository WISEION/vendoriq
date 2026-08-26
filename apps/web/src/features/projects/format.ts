import type { Locale } from '../../i18n';

/** Thousands-grouped number, no decimals — the prototype's `fmt()` (`docs/design/app.js`). */
export function formatNumber(value: number | null | undefined, locale: Locale): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(locale === 'az' ? 'de-DE' : 'en-US', {
    maximumFractionDigits: 0,
  });
}

/** `formatNumber` with an "AZN" suffix, or an em dash when the amount is unknown. */
export function formatMoney(value: number | null | undefined, locale: Locale): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${formatNumber(value, locale)} AZN`;
}

const DATE_FORMAT: Record<Locale, string> = { az: 'az-AZ', en: 'en-GB' };

/** `YYYY-MM-DD` → a locale-formatted date, or an em dash when absent. */
export function formatDate(value: string | null | undefined, locale: Locale): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(DATE_FORMAT[locale], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/** Same as {@link formatDate} but for a full timestamp (`ran_at`, `last_matched_at`). */
export function formatDateTime(value: string | null | undefined, locale: Locale): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(DATE_FORMAT[locale], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

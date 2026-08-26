import az from './az.json';
import en from './en.json';

/** Azerbaijani is the default; English is a toggle (spec §13). */
export const LOCALES = ['az', 'en'] as const;
export type Locale = (typeof LOCALES)[number];

/**
 * The dictionaries are seeded from the approved prototype (`docs/design/app.js`), so the
 * wording the owner already signed off survives into the product. Both files carry the same
 * key set — `i18n.test.ts` fails the build if they drift apart.
 */
export const DICTIONARIES = { az, en } satisfies Record<Locale, Record<string, string>>;

export type TranslationKey = keyof typeof az;

export const STORAGE_KEY = 'vendoriq.locale';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/** Falls back to English, then to the key itself, so a missing string is visible, not blank. */
export function translate(locale: Locale, key: string): string {
  const dictionary = DICTIONARIES[locale] as Record<string, string>;
  const fallback = DICTIONARIES.en as Record<string, string>;
  return dictionary[key] ?? fallback[key] ?? key;
}

import az from './az.json';
import en from './en.json';

/**
 * Per-feature dictionaries, merged over the shared ones at module load.
 *
 * Phase 2 builds seven feature areas in parallel and each needs its own strings. One shared
 * pair of JSON files would be the single place all seven met in the same diff, so a feature
 * instead owns `features/<name>.az.json` and `features/<name>.en.json` and nothing else.
 * `import.meta.glob` picks them up with no registry to update — adding a feature is adding
 * two files.
 *
 * A feature may not redefine a shared key: `i18n.test.ts` fails on a collision, because a
 * feature quietly changing the meaning of a shared label is the bug this arrangement would
 * otherwise introduce.
 */
const FEATURE_DICTIONARIES = import.meta.glob<Record<string, string>>('./features/*.json', {
  eager: true,
  import: 'default',
});

function featureStrings(locale: string): Record<string, string> {
  const merged: Record<string, string> = {};
  for (const [path, strings] of Object.entries(FEATURE_DICTIONARIES)) {
    if (path.endsWith(`.${locale}.json`)) Object.assign(merged, strings);
  }
  return merged;
}

/** Every key a feature contributes, with the file it came from — used by the drift test. */
export function featureKeyOrigins(locale: string): Map<string, string> {
  const origins = new Map<string, string>();
  for (const [path, strings] of Object.entries(FEATURE_DICTIONARIES)) {
    if (!path.endsWith(`.${locale}.json`)) continue;
    for (const key of Object.keys(strings)) origins.set(key, path);
  }
  return origins;
}

export const SHARED_DICTIONARIES = { az, en };

/** Azerbaijani is the default; English is a toggle (spec §13). */
export const LOCALES = ['az', 'en'] as const;
export type Locale = (typeof LOCALES)[number];

/**
 * The dictionaries are seeded from the approved prototype (`docs/design/app.js`), so the
 * wording the owner already signed off survives into the product. Both files carry the same
 * key set — `i18n.test.ts` fails the build if they drift apart.
 */
export const DICTIONARIES = {
  az: { ...az, ...featureStrings('az') },
  en: { ...en, ...featureStrings('en') },
} satisfies Record<Locale, Record<string, string>>;

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

import { describe, expect, it } from 'vitest';
import az from './az.json';
import en from './en.json';
import { featureKeyOrigins, LOCALES, SHARED_DICTIONARIES, translate } from './index';

describe('i18n dictionaries', () => {
  it('carry the same keys in both languages', () => {
    expect(Object.keys(az).sort()).toEqual(Object.keys(en).sort());
  });

  it('have no empty strings', () => {
    for (const [key, value] of Object.entries({ ...az, ...en })) {
      expect(value, key).not.toBe('');
    }
  });

  it('falls back to English and then to the key itself', () => {
    expect(translate('az', 'nav_overview')).toBe('İcmal');
    expect(translate('en', 'nav_overview')).toBe('Overview');
    expect(translate('az', 'no_such_key')).toBe('no_such_key');
  });
});

describe('per-feature dictionaries', () => {
  it('does not let a feature redefine a shared key', () => {
    for (const locale of LOCALES) {
      const shared = new Set(Object.keys(SHARED_DICTIONARIES[locale]));
      const collisions = [...featureKeyOrigins(locale)]
        .filter(([key]) => shared.has(key))
        .map(([key, file]) => `${key} (${file})`);

      expect(collisions, `${locale}: feature files redefining a shared key`).toEqual([]);
    }
  });

  it('declares every feature key in both languages', () => {
    const az = featureKeyOrigins('az');
    const en = featureKeyOrigins('en');

    expect([...az.keys()].sort()).toEqual([...en.keys()].sort());
  });
});

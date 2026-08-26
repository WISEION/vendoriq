import { describe, expect, it } from 'vitest';
import { DICTIONARIES, LOCALES } from '../i18n';
import { MANAGER_NAV, PAGE_TEXT, VENDOR_NAV } from './navigation';

describe('navigation', () => {
  /**
   * Against the **merged** dictionaries, not the shared file alone. A feature owns its own
   * strings (`i18n/features/<name>.<lang>.json`) and `t()` reads the merge, so checking only
   * the shared file reports a missing key for every heading a feature supplies — which is
   * most of them.
   */
  it.each(LOCALES)('uses only keys that exist in the %s dictionary', (locale) => {
    const dictionary = DICTIONARIES[locale] as Record<string, string>;

    for (const section of [...MANAGER_NAV, ...VENDOR_NAV]) {
      expect(dictionary[section.titleKey], section.titleKey).toBeDefined();
      for (const item of section.items) {
        expect(dictionary[item.labelKey], item.labelKey).toBeDefined();
      }
    }
    for (const [route, text] of Object.entries(PAGE_TEXT)) {
      expect(dictionary[text.titleKey], `${route} title`).toBeDefined();
      expect(dictionary[text.subKey], `${route} subtitle`).toBeDefined();
    }
  });

  it('gives every rail entry a page text', () => {
    for (const section of [...MANAGER_NAV, ...VENDOR_NAV]) {
      for (const item of section.items) {
        expect(PAGE_TEXT[item.path], item.path).toBeDefined();
      }
    }
  });
});

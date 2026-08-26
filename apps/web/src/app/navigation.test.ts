import { describe, expect, it } from 'vitest';
import az from '../i18n/az.json';
import { MANAGER_NAV, PAGE_TEXT, VENDOR_NAV } from './navigation';

const dictionary = az as Record<string, string>;

describe('navigation', () => {
  it('uses only keys that exist in the dictionaries', () => {
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

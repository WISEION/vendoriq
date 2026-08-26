import { expect, test } from '@playwright/test';
import { VENDOR_STATE } from '../paths';
import { setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';

// The vendor journey (brief §7.3 / task 3A): sign in as Wesa (a full, submitted, prequalified
// application — `docs/TEST_ACCOUNTS.md`) → profile → the seven application sections →
// documents → declaration and submit. Wesa's application is already decided, so "submit"
// exercises the real "already submitted" state rather than a fresh one — resubmitting would
// mutate the fixture the manager journey and the screenshots both depend on (90.3 / class A).
test.use({ storageState: VENDOR_STATE });

const HEADINGS: Record<Lang, Record<string, string>> = {
  az: {
    status: 'Müraciət statusu',
    profile: 'Şirkət profili',
    documents: 'Sənədlər paketi',
    submit: 'Bəyannamə və göndəriş',
  },
  en: {
    status: 'Application status',
    profile: 'Company profile',
    documents: 'Document package',
    submit: 'Declaration & submission',
  },
};

const LOCKED: Record<Lang, { profile: string; application: string; submitted: string }> = {
  az: {
    profile: 'Prekvalifikasiya keçmiş profil dəyişdirilə bilməz — dəyişiklik üçün əməkdaşla əlaqə saxlayın.',
    application: 'Müraciət göndərildikdən sonra cavablar dəyişdirilə bilməz.',
    submitted: 'Müraciət göndərildi — komissiya baxışına keçdi',
  },
  en: {
    profile: 'A prequalified profile cannot be edited directly — contact the officer for a change.',
    application: 'Answers cannot be changed once the application has been submitted.',
    submitted: 'Application submitted — now under commission review',
  },
};

// Exact tab labels from `apps/web/src/features/vendor/fieldCatalog.ts` (`FORM_SECTIONS`) —
// capitalisation and wording there is the source of truth, not `docs/SCREENS.md`'s prose.
const SECTION_TABS: Record<Lang, string[]> = {
  az: [
    'A. Şirkət Profili',
    'B. Maliyyə',
    'C. Texniki Təcrübə',
    'D. Maddi-Texniki Baza',
    'E. Kadr Resursları',
    'F. SƏTƏMM və Keyfiyyət',
    'G. Sığorta və Referanslar',
  ],
  en: [
    'A. Company profile',
    'B. Financial',
    'C. Technical experience',
    'D. Facilities & equipment',
    'E. Human resources',
    'F. HSE & quality',
    'G. Insurance & references',
  ],
};

for (const lang of ['az', 'en'] as const) {
  test(`vendor journey (${lang}): Wesa — profile, application, documents, submit`, async ({ page }) => {
    await page.goto('/portal');
    await setLanguage(page, lang);

    // 1. Status — the released prequalification result is a fact from the server, not a guess:
    // Wesa is 90.3 / class A (spec §11.2 fixture, `docs/TEST_ACCOUNTS.md`).
    await expect(page.getByRole('heading', { name: HEADINGS[lang].status, level: 2 })).toBeVisible();
    await expect(page.locator('.vp-class-badge')).toHaveText('A');
    await expect(page.locator('.vp-grid-2')).toContainText('90.3');

    // 2. Profile — locked, because the vendor is prequalified.
    await page.getByRole('link', { name: lang === 'az' ? 'Şirkət profili' : 'Company profile', exact: true }).click();
    await expect(page.getByRole('heading', { name: HEADINGS[lang].profile, level: 2 })).toBeVisible();
    await expect(page.getByText(LOCKED[lang].profile)).toBeVisible();

    // 3. Application sections A–G — one shared renderer, seven tabs; each is read-only for an
    // already-submitted application.
    await page.getByRole('link', { name: lang === 'az' ? 'Müraciət forması' : 'Application form', exact: true }).click();
    await expect(page).toHaveURL(/\/portal\/application\/A$/);
    for (const [index, tabLabel] of SECTION_TABS[lang].entries()) {
      const letter = String.fromCharCode('A'.charCodeAt(0) + index);
      await page.getByRole('link', { name: tabLabel, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/portal/application/${letter}$`));
      await expect(page.getByText(LOCKED[lang].application)).toBeVisible();
    }

    // 4. Documents — the 38-item checklist, 13 of them mandatory for Wesa. Its prequalification
    // came through the Excel import path (`primary_source: excel`, not the portal's own
    // `submitApplication` gate), so most mandatory rows read "missing" here even though the
    // vendor is decided and prequalified — that is provenance, not a live-app contradiction:
    // the historical Rev4 decision did not require every PDF to land in this document store.
    // What this step checks is the real, current count the screen renders, not a guess.
    await page.getByRole('link', { name: lang === 'az' ? 'Sənədlər' : 'Documents', exact: true }).click();
    await expect(page.getByRole('heading', { name: HEADINGS[lang].documents, level: 2 })).toBeVisible();
    const progress = page.locator('.small.muted').filter({ hasText: /\d+\/\d+/ }).first();
    await expect(progress).toBeVisible();
    const progressText = (await progress.textContent()) ?? '';
    const match = progressText.match(/(\d+)\/(\d+)/);
    expect(match, `expected an "N/M" mandatory-document progress readout, got: ${progressText}`).toBeTruthy();
    if (match) {
      const [, ready, mandatory] = match;
      expect(Number(mandatory), 'Wesa has 13 mandatory document codes').toBe(13);
      expect(Number(ready)).toBeGreaterThanOrEqual(0);
      expect(Number(ready)).toBeLessThanOrEqual(Number(mandatory));
    }

    // 5. Declaration and submit — already submitted, so the screen shows the confirmation
    // rather than an open form (submitting again would mutate the fixture).
    await page.getByRole('link', { name: lang === 'az' ? 'Bəyannamə və göndəriş' : 'Declaration & submit', exact: true }).click();
    await expect(page.getByText(LOCKED[lang].submitted)).toBeVisible();
  });
}

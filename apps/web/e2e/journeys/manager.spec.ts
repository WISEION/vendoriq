import { expect, test } from '@playwright/test';
import { resolveManagerIds } from '../support/ids';
import { setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';

// The manager journey (brief §7.3 / task 3A): vendor register → open a vendor → applications
// queue → evaluation with live scoring → project matching. Uses the default project session
// (staff/manager, `playwright.config.ts`), so no `test.use({ storageState })` override here.

const HEADINGS: Record<Lang, Record<string, string>> = {
  az: {
    vendors: 'Vendor reyestri',
    applications: 'Müraciətlər və qiymətləndirmə',
  },
  en: {
    vendors: 'Vendor register',
    applications: 'Applications & evaluation',
  },
};

for (const lang of ['az', 'en'] as const) {
  test(`manager journey (${lang}): register → vendor → applications → evaluation → matching`, async ({
    page,
    request,
  }) => {
    const ids = await resolveManagerIds(request);

    await page.goto('/');
    await setLanguage(page, lang);

    // 1. Vendor register — filterable table; open Wesa.
    await page.getByRole('link', { name: HEADINGS[lang].vendors, exact: true }).click();
    await expect(page.getByRole('link', { name: 'VVESA MMC (Wesa)', exact: true })).toBeVisible();
    await page.getByRole('link', { name: 'VVESA MMC (Wesa)', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/vendors/${ids.wesaVendorId}$`));
    await expect(page.getByText('VVESA MMC (Wesa)')).toBeVisible();

    // 2. Applications queue — open Wesa's application.
    await page.goto('/applications');
    await expect(page.getByRole('heading', { name: HEADINGS[lang].applications, level: 2 })).toBeVisible();
    await page.getByRole('link', { name: 'VVESA MMC (Wesa)', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/applications/${ids.wesaApplicationId}$`));

    // 3. Evaluation, Wesa — the fact this suite exists to pin down: 90.3 / class A
    // (spec §11.2's Rev4 fixture). Every number on this screen is server-computed
    // (`Evaluation.tsx`'s own rule); this reads what the server already decided, it computes
    // nothing here.
    const decisionAlert = page.locator('.mgr-alert-good, .mgr-alert-crit').first();
    await expect(decisionAlert).toContainText('90.3/100');
    await expect(decisionAlert.locator('.mgr-cls-A')).toBeVisible();

    // Live scoring: nudge one non-knock-out rubric cell (B.3) and watch the total react —
    // `computeScore` is a preview endpoint, it persists nothing (`Evaluation.tsx` §top
    // comment). Put the value back the same way (typing 3 again), NOT via the "Sıfırla"/
    // "Reset" button: that button is a confirmed bug (reported separately) — it restores the
    // input's value but never clears `live.data`, so the score/class display is left stuck at
    // the edited number while the input silently shows the original again.
    const rubricB3 = page.locator('#rubric-B\\.3');
    await expect(rubricB3).toHaveValue('3');
    await rubricB3.fill('1');
    await expect(decisionAlert).not.toContainText('90.3/100', { timeout: 5000 });
    await rubricB3.fill('3');
    await expect(decisionAlert).toContainText('90.3/100');
    await expect(decisionAlert.locator('.mgr-cls-A')).toBeVisible();
    // Deliberately not saved: `putEvaluation` would persist this round trip against a
    // decided, prequalified application — a write this suite has no business making.

    // 4. Evaluation, Shield — the second fixed fact: 94.7 / class A.
    await page.goto('/applications');
    await page.getByRole('link', { name: 'Shield', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/applications/${ids.shieldApplicationId}$`));
    const shieldAlert = page.locator('.mgr-alert-good, .mgr-alert-crit').first();
    await expect(shieldAlert).toContainText('94.7/100');
    await expect(shieldAlert.locator('.mgr-cls-A')).toBeVisible();

    // 5. Project matching, TQS-238 — run it live, then read the recommendation the server
    // returns: 96% coverage, flooring the only NO-GO package (spec §11.2).
    await page.goto(`/projects/${ids.tqs238ProjectId}`);
    await page.getByRole('button', { name: lang === 'az' ? 'Uyğunlaşdırmanı işə sal' : 'Run matching' }).click();
    const banner = page.locator('.viq-banner');
    await expect(banner).toContainText('96%');
    await expect(banner.locator('.viq-pill-nogo')).toBeVisible();

    // Scoped to `.viq-card-head`: the package's own go/no-go `StatePill` lives there. A
    // candidate row's *eligibility* pill reuses the same `viq-pill-nogo` class for an
    // ineligible vendor's reason (e.g. "Not prequalified") — that is not the package verdict
    // and must not be counted as a second NO-GO package.
    const flooringName = lang === 'az' ? 'Döşəmə / parket' : 'Flooring / parquet';
    const packageCards = page.locator('.viq-card');
    await expect(
      packageCards.filter({ hasText: flooringName }).locator('.viq-card-head .viq-pill-nogo'),
    ).toBeVisible();

    // "The only NO-GO": every other package card's own verdict pill must not be NO-GO.
    const otherCards = packageCards.filter({ hasNotText: flooringName });
    const otherCount = await otherCards.count();
    expect(otherCount).toBeGreaterThan(0);
    for (let i = 0; i < otherCount; i += 1) {
      await expect(otherCards.nth(i).locator('.viq-card-head .viq-pill-nogo')).toHaveCount(0);
    }
  });
}

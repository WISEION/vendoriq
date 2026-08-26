import type { APIRequestContext } from '@playwright/test';
import { test } from '@playwright/test';
import { ensureProjectMatch, resolveManagerIds } from '../support/ids';
import type { ManagerIds } from '../support/ids';
import { captureScreen, gotoAndSettle, setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';
import { managerScreens } from '../support/screens';

// Screens 15–34 except `admin-users` (`docs/SCREENS.md`): the default project session
// (manager) already carries every permission these need.

// Memoised per worker process: every test in this file needs the same ids and the same
// one-off "run the match so the screen has real data" call, and `test()` bodies below are
// generated before any fixture runs, so the resolution has to happen lazily, on first use,
// rather than in a file-level `beforeAll`.
let setup: Promise<ManagerIds> | null = null;
function ensureSetup(request: APIRequestContext): Promise<ManagerIds> {
  if (!setup) {
    setup = resolveManagerIds(request).then(async (ids) => {
      await ensureProjectMatch(request, ids.tqs238ProjectId);
      return ids;
    });
  }
  return setup;
}

// The set of screens is fixed regardless of ids (only the *paths* of a few nested ones depend
// on them), so the slugs to iterate over are known upfront; the placeholder ids below are
// replaced with the resolved ones inside each test.
const PLACEHOLDER_IDS: ManagerIds = {
  wesaVendorId: 'placeholder',
  shieldVendorId: 'placeholder',
  wesaApplicationId: 'placeholder',
  shieldApplicationId: 'placeholder',
  tqs238ProjectId: 'placeholder',
};
const SLUGS = managerScreens(PLACEHOLDER_IDS).map((screen) => screen.slug);

for (const slug of SLUGS) {
  for (const lang of ['az', 'en'] as const) {
    test(`@screenshot ${slug} (${lang})`, async ({ page, request }) => {
      const ids = await ensureSetup(request);
      const screen = managerScreens(ids).find((entry) => entry.slug === slug)!;
      await gotoAndSettle(page, screen.path);
      await setLanguage(page, lang as Lang);
      await captureScreen(page, screen.slug, lang as Lang);
    });
  }
}

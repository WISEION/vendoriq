import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page, Response } from '@playwright/test';
import { expect } from '@playwright/test';

export type Lang = 'az' | 'en';

const here = path.dirname(fileURLToPath(import.meta.url));

/** `docs/screens/<slug>.<lang>.png` — the contract `docs/SCREENS.md` fixes. */
export const SCREENS_DIR = path.join(here, '..', '..', '..', '..', 'docs', 'screens');

export function screenshotPath(slug: string, lang: Lang): string {
  return path.join(SCREENS_DIR, `${slug}.${lang}.png`);
}

/**
 * Freezes everything that could make two runs of the same screenshot differ: CSS
 * transitions/animations, the blinking text-input caret, and smooth-scroll easing. The app
 * itself has no client-side clock or `Math.random()` in its render path (checked directly),
 * so this — plus `networkidle` before capture — is the whole determinism story.
 */
async function freezeUi(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        scroll-behavior: auto !important;
        caret-color: transparent !important;
      }
    `,
  });
}

/**
 * Sets the AZ/EN toggle explicitly rather than assuming the default — the toggle is the same
 * `role="group" aria-label="Language"` segmented control on every screen, public or
 * protected (`AuthLayout.tsx` / `Topbar.tsx`), and it persists to `localStorage` so it holds
 * across the navigation the caller does next.
 */
export async function setLanguage(page: Page, lang: Lang): Promise<void> {
  const group = page.getByRole('group', { name: 'Language' });
  await expect(group).toBeVisible();
  await group.getByRole('button', { name: lang.toUpperCase() }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
}

/**
 * Response statuses that fail the request but do not put the *screen* into an error state —
 * each is caught, or its result quietly optional, in the component that made the call, so the
 * page still renders real content. Every entry here is a reported finding, not a shrug:
 *
 * - `GET /api/auth/me` → 401: the normal "am I signed in" check on a signed-out visit
 *   (`auth/session.ts`) — expected on every public screen, not a bug.
 * - `GET /api/projects/{id}/match/latest` → 404: `ProjectMatchingScreen.tsx`'s own
 *   `fetchLatestMatch` catches exactly this and renders the "never matched" state on purpose.
 * - `PATCH /api/applications/{id}/answers` → 409: `useAnswerState` (`vendor/hooks.ts`) reads
 *   computed fields and the completion meter through an *empty* `patchAnswers` call rather
 *   than a dedicated read endpoint. For a locked application (submitted/decided — anything
 *   outside `EDITABLE_STATUSES`) the server correctly refuses the write, so this 409 fires on
 *   every visit to any of screens 6–12 for such an application; the query then silently has no
 *   data, and the completion bar reads 0% for an application that is, in Wesa's case, complete
 *   and prequalified. Reported separately — not fixed here, and not hidden: the screenshot
 *   still shows the resulting 0% bar, because that is what the shipped screen actually renders.
 * - `GET /api/admin/users` → 403: `AuditLogScreen.tsx` builds its actor filter from
 *   `listUsers` unconditionally, but `docs/SCREENS.md` grants `/admin/audit` itself to
 *   `manager` too (gated on `listAuditEvents`, which manager holds) — `listUsers` is
 *   `admin`-only. The screen degrades gracefully (`actors.data?.items ?? []`, no error
 *   rendered), but the actor filter is silently empty for a manager. Reported separately.
 */
function isKnownGracefulFailure(response: Response): boolean {
  const url = response.url();
  const status = response.status();
  if (status === 401 && url.includes('/api/auth/me')) return true;
  if (status === 404 && /\/api\/projects\/[^/]+\/match\/latest$/.test(url)) return true;
  if (status === 409 && /\/api\/applications\/[^/]+\/answers$/.test(url)) return true;
  if (status === 403 && url.includes('/api/admin/users')) return true;
  return false;
}

/**
 * Navigates to `route`, settles the network and any transition, and asserts nothing failed —
 * a screenshot of an error is a finding, not a screenshot (`docs/screens/` must never carry
 * one silently). This checks real `/api/` response status, not rendered CSS classes: several
 * screens legitimately render `mgr-alert-crit` / `role="alert"` for genuine business content
 * (the overview's attention list marks a real gap "critical" on purpose — spec §10), so a
 * text/class heuristic would flag correct screens as errors. A failed request is unambiguous,
 * modulo the known, reported, gracefully-handled cases in `isKnownGracefulFailure` above.
 */
export async function gotoAndSettle(page: Page, route: string): Promise<void> {
  const failed: string[] = [];
  const onResponse = (response: Response) => {
    if (response.url().includes('/api/') && response.status() >= 400 && !isKnownGracefulFailure(response)) {
      failed.push(`${response.status()} ${response.url()}`);
    }
  };
  page.on('response', onResponse);
  try {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    await freezeUi(page);
  } finally {
    page.off('response', onResponse);
  }
  if (failed.length > 0) {
    throw new Error(`${route} had failing API responses, refusing to screenshot it:\n${failed.join('\n')}`);
  }
}

/** Full-page, deterministic capture to the contract path. */
export async function captureScreen(page: Page, slug: string, lang: Lang): Promise<void> {
  await page.screenshot({ path: screenshotPath(slug, lang), fullPage: true });
}

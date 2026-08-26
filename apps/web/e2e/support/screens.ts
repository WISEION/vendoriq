import type { ManagerIds } from './ids';

export interface ScreenEntry {
  /** `docs/SCREENS.md` slug — the screenshot filename stem. */
  slug: string;
  path: string;
}

/** Screens 1–3 (`docs/SCREENS.md`) — public, no session. */
export const PUBLIC_SCREENS: ScreenEntry[] = [
  { slug: 'auth-vendor-signin', path: '/login' },
  { slug: 'auth-staff-signin', path: '/login/staff' },
  { slug: 'auth-vendor-register', path: '/register' },
];

/** Screens 4–14 — the vendor portal, signed in as Wesa. */
export const VENDOR_SCREENS: ScreenEntry[] = [
  { slug: 'vendor-status', path: '/portal' },
  { slug: 'vendor-profile', path: '/portal/profile' },
  { slug: 'vendor-form-a', path: '/portal/application/A' },
  { slug: 'vendor-form-b', path: '/portal/application/B' },
  { slug: 'vendor-form-c', path: '/portal/application/C' },
  { slug: 'vendor-form-d', path: '/portal/application/D' },
  { slug: 'vendor-form-e', path: '/portal/application/E' },
  { slug: 'vendor-form-f', path: '/portal/application/F' },
  { slug: 'vendor-form-g', path: '/portal/application/G' },
  { slug: 'vendor-documents', path: '/portal/documents' },
  { slug: 'vendor-submit', path: '/portal/submit' },
];

/**
 * Screens 15–34 minus `admin-users` — the manager account carries every permission these
 * need. `admin-users` (`listUsers`) is the one screen the manager role cannot open
 * (`docs/SCREENS.md`'s own "who admits today" row for it is `admin` alone — confirmed against
 * `GET /api/auth/me`'s `permissions`), so it is screenshotted separately, signed in as admin.
 */
export function managerScreens(ids: ManagerIds): ScreenEntry[] {
  return [
    { slug: 'manager-overview', path: '/' },
    { slug: 'vendor-register', path: '/vendors' },
    { slug: 'vendor-detail', path: `/vendors/${ids.wesaVendorId}` },
    { slug: 'applications-queue', path: '/applications' },
    { slug: 'evaluation', path: `/applications/${ids.wesaApplicationId}` },
    { slug: 'commission-summary', path: `/applications/${ids.wesaApplicationId}/summary` },
    { slug: 'cycles', path: '/cycles' },
    { slug: 'projects-list', path: '/projects' },
    { slug: 'project-edit', path: `/projects/${ids.tqs238ProjectId}/edit` },
    { slug: 'project-matching', path: `/projects/${ids.tqs238ProjectId}` },
    { slug: 'market-intelligence', path: '/market' },
    { slug: 'scoring-models', path: '/scoring-models' },
    { slug: 'model-editor', path: '/scoring-models/sub-4' },
    { slug: 'data-sources', path: '/integrations' },
    { slug: 'excel-import', path: '/integrations/excel-import' },
    { slug: 'erp-connector', path: '/integrations/adapters/erp_1c' },
    { slug: 'admin-categories', path: '/admin/categories' },
    { slug: 'admin-settings', path: '/admin/settings' },
    { slug: 'admin-audit', path: '/admin/audit' },
  ];
}

/** Screen 32 — `admin-users`, the one screen that needs the admin session. */
export const ADMIN_ONLY_SCREENS: ScreenEntry[] = [{ slug: 'admin-users', path: '/admin/users' }];

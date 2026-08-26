/**
 * The vendor portal — screens 4–14 of `docs/SCREENS.md` (task 2A).
 *
 * Every route below is fixed by `docs/SCREENS.md` and is NOT wired into `apps/web/src/app/
 * routes.tsx` or `navigation.ts` by this task (both are outside task 2A's owned files —
 * see the worker report's change-request list). This module exports what the orchestrator
 * needs to mount each screen at its address:
 *
 *   /portal                    → VendorStatus            (screen 4, already in PAGE_TEXT)
 *   /portal/profile            → VendorProfile            (screen 5, already in PAGE_TEXT)
 *   /portal/application        → redirect to .../A        (not yet a route — needs adding)
 *   /portal/application/A      → VendorFormA               (screen 6 — needs adding)
 *   /portal/application/B      → VendorFormB               (screen 7 — needs adding)
 *   /portal/application/C      → VendorFormC               (screen 8 — needs adding)
 *   /portal/application/D      → VendorFormD               (screen 9 — needs adding)
 *   /portal/application/E      → VendorFormE               (screen 10 — needs adding)
 *   /portal/application/F      → VendorFormF               (screen 11 — needs adding)
 *   /portal/application/G      → VendorFormG               (screen 12 — needs adding)
 *   /portal/documents          → VendorDocuments           (screen 13, already in PAGE_TEXT)
 *   /portal/submit             → VendorSubmit              (screen 14, already in PAGE_TEXT)
 *
 * `/portal`, `/portal/profile`, `/portal/documents` and `/portal/submit` already have routes
 * (auto-generated from `PAGE_TEXT`) and a `<Page route={path} />` component with no children —
 * mounting these four is `<Page route={path}><VendorX /></Page>`. The seven `/portal/
 * application/*` routes do not exist yet and need adding to `routeTree` (plus `PAGE_TEXT`
 * entries and the `/portal/application` → `/portal/application/A` redirect) — see the worker
 * report for the exact change request.
 */
export { VendorStatus } from './VendorStatus';
export { VendorProfile } from './VendorProfile';
export {
  VendorApplicationForm,
  VendorFormA,
  VendorFormB,
  VendorFormC,
  VendorFormD,
  VendorFormE,
  VendorFormF,
  VendorFormG,
} from './VendorApplicationForm';
export { VendorDocuments } from './VendorDocuments';
export { VendorSubmit } from './VendorSubmit';
export { FORM_SECTIONS, FORM_SECTION_KEYS, sectionByKey } from './fieldCatalog';
export type { SectionKey } from './fieldCatalog';

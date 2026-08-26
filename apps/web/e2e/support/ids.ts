import type { APIRequestContext } from '@playwright/test';

/**
 * Record ids the nested screens (`docs/SCREENS.md` — vendor detail, evaluation, commission
 * summary, project edit/matching, model editor, ERP connector) need in their address.
 *
 * Resolved from the API at test time rather than hardcoded: the seed's UUIDs are assigned by
 * `uuid4()` (`vendoriq_api` seed script), not derived from the fixture's `external_ref`, so a
 * reseed between runs would silently break a suite that hardcoded them. Every id below is
 * looked up through a call the manager account already has permission for.
 */
export interface ManagerIds {
  wesaVendorId: string;
  wesaApplicationId: string;
  shieldVendorId: string;
  shieldApplicationId: string;
  tqs238ProjectId: string;
}

async function firstVendorId(request: APIRequestContext, q: string): Promise<string> {
  const response = await request.get(`/api/vendors?q=${encodeURIComponent(q)}`);
  if (!response.ok()) throw new Error(`GET /api/vendors?q=${q} → ${response.status()}`);
  const body = (await response.json()) as { items: { id: string; legal_name: string }[] };
  const item = body.items[0];
  if (!item) throw new Error(`No vendor matched q=${q} — is the seed loaded?`);
  return item.id;
}

async function firstApplicationId(request: APIRequestContext, q: string): Promise<string> {
  const response = await request.get(`/api/applications?q=${encodeURIComponent(q)}`);
  if (!response.ok()) throw new Error(`GET /api/applications?q=${q} → ${response.status()}`);
  const body = (await response.json()) as { items: { id: string }[] };
  const item = body.items[0];
  if (!item) throw new Error(`No application matched q=${q} — is the seed loaded?`);
  return item.id;
}

async function firstProjectId(request: APIRequestContext, q: string): Promise<string> {
  const response = await request.get(`/api/projects?q=${encodeURIComponent(q)}`);
  if (!response.ok()) throw new Error(`GET /api/projects?q=${q} → ${response.status()}`);
  const body = (await response.json()) as { items: { id: string }[] };
  const item = body.items[0];
  if (!item) throw new Error(`No project matched q=${q} — is the seed loaded?`);
  return item.id;
}

/** Fetched once per file via `test.beforeAll` and reused by every screenshot in it. */
export async function resolveManagerIds(request: APIRequestContext): Promise<ManagerIds> {
  const [wesaVendorId, shieldVendorId, wesaApplicationId, shieldApplicationId, tqs238ProjectId] =
    await Promise.all([
      firstVendorId(request, 'Wesa'),
      firstVendorId(request, 'Shield'),
      firstApplicationId(request, 'Wesa'),
      firstApplicationId(request, 'Shield'),
      firstProjectId(request, 'TQS-238'),
    ]);
  return { wesaVendorId, shieldVendorId, wesaApplicationId, shieldApplicationId, tqs238ProjectId };
}

/**
 * `runMatch` (`POST /projects/{id}/match`) needs the CSRF header the browser sends
 * automatically (`api/client.ts` reads it off the readable `vendoriq_csrf` cookie) — an
 * `APIRequestContext` has to do that by hand.
 */
async function csrfTokenFrom(request: APIRequestContext): Promise<string> {
  const state = await request.storageState();
  const cookie = state.cookies.find((c) => c.name === 'vendoriq_csrf');
  if (!cookie) throw new Error('vendoriq_csrf cookie missing — is the request context signed in?');
  return cookie.value;
}

/**
 * So the `project-matching` and `projects-list` screenshots show a real, run coverage number
 * rather than "never matched" — the manager journey exercises the "Run matching" button
 * itself; this gives the screenshot-only spec the same real state without duplicating that
 * click-through. Idempotent: re-running against the same seed data recomputes the same result.
 */
export async function ensureProjectMatch(request: APIRequestContext, projectId: string): Promise<void> {
  const csrf = await csrfTokenFrom(request);
  const response = await request.post(`/api/projects/${projectId}/match`, {
    headers: { 'X-CSRF-Token': csrf },
    data: {},
  });
  if (!response.ok()) {
    throw new Error(`POST /api/projects/${projectId}/match → ${response.status()}`);
  }
}

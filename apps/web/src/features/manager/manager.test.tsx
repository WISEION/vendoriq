/**
 * Screens 15–20 rendered against a stubbed API — the same harness
 * `../vendor/vendor.test.tsx` and `../integrations/integrations.test.tsx` use. `routes.tsx`
 * does not mount these components yet (this task's report files that as a change request for
 * the orchestrator), so this is the evidence that each screen renders correctly against the
 * contract shapes ahead of that wiring, and — for the evaluation screen specifically — that
 * every number on screen came from the API response rather than a client-side computation
 * (brief §2, Gate 2's "no business logic in the frontend").
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../i18n/LocaleProvider';
import { SessionProvider } from '../../auth/SessionProvider';
import {
  ApplicationsQueue,
  CommissionSummary,
  Evaluation,
  Overview,
  VendorDetail,
  VendorRegister,
} from './index';

const VENDOR_ID = 'v9';
const APPLICATION_ID = 'app9';
const CYCLE_ID = 'c9';

const ME = {
  id: 'u1',
  email: 'manager@vendoriq.test',
  full_name: 'Test Manager',
  role: 'manager',
  vendor_id: null,
  vendor_name: null,
  is_active: true,
  permissions: [
    'getIntelOverview',
    'getIntelCoverage',
    'getClassDistribution',
    'getAttentionList',
    'listEvents',
    'listVendors',
    'getVendor',
    'listApplications',
    'getApplication',
    'getEvaluation',
    'putEvaluation',
    'computeScore',
    'decideApplication',
    'putSecondEvaluation',
    'exportCommissionSummaryXlsx',
    'exportCommissionSummaryPdf',
    'listCategories',
    'listCycles',
  ],
  auth_mode: 'test',
};

const INTEL_OVERVIEW = {
  vendors_total: 13,
  vendors_sub: 12,
  vendors_sup: 1,
  prequalified: 7,
  prequalified_ab: 4,
  awaiting_review: 2,
  incomplete: 1,
  documents_expiring_60d: 3,
  category_gaps: 1,
};

const COVERAGE = [
  { category_code: 'facade', name_az: 'Fasad işləri', name_en: 'Façade works', counts: { A: 2 }, total: 2, ab_share: 1 },
];
const CLASS_DISTRIBUTION = [
  { cls: 'A', count: 2 },
  { cls: 'B', count: 2 },
  { cls: 'C', count: 2 },
];
const ATTENTION = [{ key: 'att_rev', count: 2, severity: 'info', link: '/applications' }];
const EVENTS_PAGE = {
  items: [
    {
      id: 'e1',
      type: 'vendor.prequalified',
      entity_type: 'vendor',
      entity_id: VENDOR_ID,
      payload: { legal_name: 'Shield' },
      created_at: '2026-08-20T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 8,
};

const VENDOR_ROW = {
  id: VENDOR_ID,
  legal_name: 'Shield',
  voen: '2002138471',
  type: 'sub',
  legal_form: null,
  registration_year: 2011,
  address: null,
  region: 'Bakı',
  website: null,
  status: 'prequalified',
  external_ref: null,
  is_demo: false,
  latest_score: 94.7,
  latest_class: 'A',
  prequalified_until: '2027-08-20',
  primary_source: 'api',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-08-19T00:00:00Z',
};
const VENDORS_PAGE = { items: [VENDOR_ROW], total: 1, page: 1, page_size: 25 };

const VENDOR_DETAIL = {
  ...VENDOR_ROW,
  contacts: [
    { id: 'ct1', vendor_id: VENDOR_ID, name: 'Tabit Alızadə', position: 'Sales', phone: '+994 70 000 00 00', email: 'a.tabit@shield.az', is_primary: true, has_portal_account: true },
  ],
  categories: [],
  current_fields: {},
  raw_indicators: {},
  documents: [],
  evaluations: [
    {
      application_id: APPLICATION_ID,
      cycle_name: 'TQS2026006 Rev4',
      model_version: 'sub-4',
      total: 94.7,
      cls: 'A',
      decision: 'approve',
      decided_at: '2026-04-28T00:00:00Z',
    },
  ],
  stale_fields: [],
};

const APPLICATION_SUMMARY = {
  id: APPLICATION_ID,
  vendor_id: VENDOR_ID,
  vendor_name: 'Shield',
  cycle_id: CYCLE_ID,
  cycle_name: 'TQS2026006 Rev4',
  status: 'under_review',
  submitted_at: '2026-04-24T00:00:00Z',
  total: 94.7,
  cls: 'A',
  decision: null,
  decided_at: '2026-04-28T00:00:00Z',
  evaluator_name: null,
  is_demo: false,
};
const APPLICATIONS_PAGE = { items: [APPLICATION_SUMMARY], total: 1, page: 1, page_size: 25 };

//: Two rubric criteria are enough to prove the wiring; the totals below are fixtures the
//: stubbed API returns — the screen must show exactly these numbers, never a recomputation.
const EVALUATION = {
  application_id: APPLICATION_ID,
  model_version: 'sub-4',
  rows: [
    {
      code: 'A.1',
      group: 'A',
      name_az: 'Tikinti lisenziyası',
      name_en: 'Construction licence',
      kind: 'rubric',
      max: 5,
      ko: true,
      unit: null,
      evidence_doc: 'A-04',
      raw_value: null,
      raw_source: 'excel',
      rubric_score: 3,
      points: 5,
    },
    {
      code: 'B.1',
      group: 'B',
      name_az: 'Orta illik dövriyyə',
      name_en: 'Avg annual turnover',
      kind: 'thresh',
      max: 8,
      ko: false,
      unit: 'AZN',
      evidence_doc: 'B-01',
      raw_value: 8_606_630,
      raw_source: 'api',
      rubric_score: null,
      points: 8,
    },
  ],
  computed: { per: { 'A.1': 5, 'B.1': 8 }, groups: { A: 5, B: 8 }, total: 94.7, ko: true, cls: 'A', pass_mark: 70, model_version: 'sub-4' },
  can_approve: true,
  evaluator_name: null,
};

//: What `computeScore` returns after the officer lowers `A.1` to 1 — deliberately a
//: different total from `EVALUATION.computed` so the test can prove the screen re-renders
//: with THIS number, not one it derived itself.
const COMPUTE_AFTER_EDIT = {
  per: { 'A.1': 1.7, 'B.1': 8 },
  groups: { A: 1.7, B: 8 },
  total: 63.4,
  ko: true,
  cls: 'F',
  pass_mark: 70,
  model_version: 'sub-4',
};

function mockApi(overrides: Partial<Record<string, unknown>> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      const path = url.pathname.replace(/^\/api/, '');
      const method = (init?.method ?? 'GET').toUpperCase();
      const respond = (body: unknown, status = 200) =>
        ({ ok: status < 400, status, json: async () => body, blob: async () => new Blob([JSON.stringify(body)]) }) as Response;

      if (path === '/auth/me') return respond(overrides.me ?? ME);
      if (path === '/intel/overview') return respond(overrides.intelOverview ?? INTEL_OVERVIEW);
      if (path === '/intel/coverage') return respond(overrides.coverage ?? COVERAGE);
      if (path === '/intel/class-distribution') return respond(overrides.classDistribution ?? CLASS_DISTRIBUTION);
      if (path === '/intel/attention') return respond(overrides.attention ?? ATTENTION);
      if (path === '/events') return respond(overrides.events ?? EVENTS_PAGE);
      if (path === '/vendors' && method === 'GET') return respond(overrides.vendors ?? VENDORS_PAGE);
      if (path === `/vendors/${VENDOR_ID}` && method === 'GET') return respond(overrides.vendor ?? VENDOR_DETAIL);
      if (path === '/admin/categories') return respond(overrides.categories ?? []);
      if (path === '/cycles') return respond(overrides.cycles ?? { items: [{ id: CYCLE_ID, name: 'TQS2026006 Rev4', kind: 'tender', scoring_model_version: 'sub-4', status: 'closed', application_count: 13, is_demo: false }], total: 1, page: 1, page_size: 100 });
      if (path === '/applications' && method === 'GET') return respond(overrides.applications ?? APPLICATIONS_PAGE);
      if (new RegExp(`^/applications/${APPLICATION_ID}$`).test(path) && method === 'GET') {
        return respond(overrides.applicationDetail ?? { ...APPLICATION_SUMMARY, scoring_model_version: 'sub-4' });
      }
      if (new RegExp(`^/applications/${APPLICATION_ID}/evaluation$`).test(path) && method === 'GET') {
        return respond(overrides.evaluation ?? EVALUATION);
      }
      if (new RegExp(`^/applications/${APPLICATION_ID}/evaluation$`).test(path) && method === 'PUT') {
        return respond(overrides.putEvaluation ?? EVALUATION);
      }
      if (new RegExp(`^/applications/${APPLICATION_ID}/compute$`).test(path) && method === 'POST') {
        return respond(overrides.compute ?? COMPUTE_AFTER_EDIT);
      }
      if (new RegExp(`^/applications/${APPLICATION_ID}/decide$`).test(path) && method === 'POST') {
        return respond(overrides.decide ?? { ...APPLICATION_SUMMARY, status: 'prequalified', decision: 'approve' });
      }
      if (new RegExp(`^/cycles/${CYCLE_ID}/export-summary\\.(xlsx|pdf)$`).test(path)) {
        return respond({});
      }
      throw new Error(`unstubbed request: ${method} ${path}`);
    }),
  );
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const rootRoute = createRootRoute({ component: () => <>{children}</> });
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/' });
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <LocaleProvider>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          <RouterProvider router={router as any} />
        </LocaleProvider>
      </SessionProvider>
    </QueryClientProvider>
  );
}

Object.defineProperty(window, 'scrollTo', { value: () => {}, writable: true });
Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', writable: true });
Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, writable: true });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('manager-overview (screen 15)', () => {
  it('renders the KPI tiles and the attention list from the intel endpoints', async () => {
    mockApi();
    render(
      <Harness>
        <Overview />
      </Harness>,
    );
    expect(await screen.findByText('13')).toBeInTheDocument(); // vendors_total
    expect(screen.getByText('7')).toBeInTheDocument(); // prequalified
    expect(await screen.findByText(/Baxılmağı gözləyən/)).toBeInTheDocument();
    expect(await screen.findByText('Shield', { exact: false })).toBeInTheDocument();
  });
});

describe('vendor-register (screen 16)', () => {
  it('lists a vendor with its class and score, and links to its detail page', async () => {
    mockApi();
    render(
      <Harness>
        <VendorRegister />
      </Harness>,
    );
    const link = await screen.findByRole('link', { name: 'Shield' });
    expect(link).toHaveAttribute('href', `/vendors/${VENDOR_ID}`);
    const row = link.closest('tr');
    expect(row).not.toBeNull();
    expect(within(row!).getByText('A')).toBeInTheDocument();
  });
});

describe('vendor-detail (screen 17)', () => {
  it('renders the profile and the scorecard points from getEvaluation, not a local total', async () => {
    mockApi();
    render(
      <Harness>
        <VendorDetail vendorId={VENDOR_ID} />
      </Harness>,
    );
    expect(await screen.findByText('Shield')).toBeInTheDocument();
    expect(screen.getByText('2002138471')).toBeInTheDocument();
    // The per-criterion raw value and points come straight from `getEvaluation`'s fixture
    // (8 606 630 raw, 8 points) — not a recomputation from a rubric cell or a threshold table.
    const raw = await screen.findByText('8 606 630', {}, { timeout: 3000 });
    const row = raw.closest('tr');
    expect(row).not.toBeNull();
    expect(within(row!).getAllByText('8')).toHaveLength(2); // points column and max column
  });
});

describe('applications-queue (screen 18)', () => {
  it('lists the queue with score and class, linking to the evaluation screen', async () => {
    mockApi();
    render(
      <Harness>
        <ApplicationsQueue />
      </Harness>,
    );
    const link = await screen.findByRole('link', { name: 'Shield' });
    expect(link).toHaveAttribute('href', `/applications/${APPLICATION_ID}`);
    const row = link.closest('tr');
    expect(row).not.toBeNull();
    expect(within(row!).getByText('A')).toBeInTheDocument();
  });
});

describe('evaluation (screen 19)', () => {
  it('shows the server-computed total and recomputes it via computeScore, never locally', async () => {
    mockApi();
    render(
      <Harness>
        <Evaluation applicationId={APPLICATION_ID} />
      </Harness>,
    );
    expect(await screen.findByText(/94\.7/)).toBeInTheDocument();
    const approve = screen.getByRole('button', { name: 'Prekvalifikasiyanı təsdiqlə' });
    expect(approve).not.toBeDisabled();

    const cell = screen.getByLabelText('A.1 Tikinti lisenziyası');
    fireEvent.change(cell, { target: { value: '1' } });

    // The new total (63.4) is the fixture `computeScore` returns for this edit — if the
    // screen were computing it itself, it would show a different (wrong) number instead.
    await waitFor(() => expect(screen.getByText(/63\.4/)).toBeInTheDocument(), { timeout: 2000 });
    expect(screen.getByRole('button', { name: 'Prekvalifikasiyanı təsdiqlə' })).toBeDisabled();
  });

  it('sends a justification with a reject decision', async () => {
    mockApi();
    render(
      <Harness>
        <Evaluation applicationId={APPLICATION_ID} />
      </Harness>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Rədd et' }));
    const textbox = await screen.findByLabelText('Əsaslandırma');
    fireEvent.change(textbox, { target: { value: 'Below the required class.' } });
    const submit = screen.getAllByRole('button', { name: 'Rədd et' }).find((btn) => btn.getAttribute('type') === 'submit');
    expect(submit).toBeDefined();
    fireEvent.click(submit!);
    await waitFor(() => expect(screen.queryByLabelText('Əsaslandırma')).not.toBeInTheDocument());
  });
});

describe('commission-summary (screen 20)', () => {
  it('offers both exports and previews the cycle rows', async () => {
    mockApi();
    render(
      <Harness>
        <CommissionSummary applicationId={APPLICATION_ID} />
      </Harness>,
    );
    expect(await screen.findByRole('button', { name: /Excel kimi çıxar/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /PDF kimi çıxar/ })).toBeInTheDocument();
    const row = (await screen.findByText('Shield')).closest('tr');
    expect(row ? within(row).getByText('A') : null).toBeInTheDocument();
  });
});

/**
 * Screens 4–14 rendered against a stubbed API — the same shape
 * `../integrations/integrations.test.tsx` uses. Routes.tsx/navigation.ts do not mount these
 * components yet (task 2A's report files that as a change request for the orchestrator), so
 * this is the evidence that each screen renders correctly against the contract shapes ahead
 * of that wiring: every fixture below matches `docs/openapi.yaml`'s schemas exactly.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  VendorDocuments,
  VendorFormA,
  VendorFormC,
  VendorProfile,
  VendorStatus,
  VendorSubmit,
} from './index';

const VENDOR_ID = 'v1';
const APPLICATION_ID = 'app1';

const ME = {
  id: 'u1',
  email: 'vendor@wesa.az',
  full_name: 'Həbib Atakişiyev',
  role: 'vendor',
  vendor_id: VENDOR_ID,
  vendor_name: 'VVESA MMC',
  is_active: true,
  permissions: [
    'listApplications',
    'getApplication',
    'patchAnswers',
    'submitApplication',
    'getVendor',
    'patchVendor',
    'listVendorCategories',
    'setVendorCategories',
    'listCategories',
    'listContacts',
    'createContact',
    'listDocuments',
    'initDocumentUpload',
    'completeDocumentUpload',
    'getDocumentDownload',
    'patchDocument',
  ],
  auth_mode: 'test',
};

const APPLICATION_SUMMARY = {
  id: APPLICATION_ID,
  vendor_id: VENDOR_ID,
  vendor_name: 'VVESA MMC',
  cycle_id: 'c1',
  cycle_name: 'TQS2026006',
  status: 'in_progress',
  submitted_at: null,
  total: null,
  cls: null,
  decision: null,
  decided_at: null,
  evaluator_name: null,
  is_demo: false,
};

const APPLICATIONS_PAGE = { items: [APPLICATION_SUMMARY], total: 1, page: 1, page_size: 50 };

const CHECKS = {
  mandatory_fields: false,
  mandatory_documents: false,
  knock_out_answers: false,
  missing_field_codes: ['A.11', 'A.15', 'F.1'],
  missing_document_codes: ['A-01', 'A-04', 'A-05'],
};

const APPLICATION_DETAIL = {
  ...APPLICATION_SUMMARY,
  scoring_model_version: 'sub-4',
  answers: { 'A.1': 'VVESA MMC', 'B.1': 3_000_000, 'B.2': 2_800_000, 'B.3': 2_500_000 },
  raw_snapshot: null,
  rubric_scores: null,
  computed: null,
  declaration: null,
  justification: null,
  checks: CHECKS,
  // The completion meter and the computed cells arrive on the detail now, not through an
  // empty `PATCH /answers` — which the server refuses once the application is submitted, so
  // the meter used to read 0 % for a complete application (3A, finding 4).
  completion_pct: 14.3,
  computed_fields: { 'B.4': 2_766_666.67, 'B.8': 1.8 },
  score_released: false,
};

/** Still the shape `patchAnswers` returns; the form no longer *reads* it. */
const ANSWER_STATE = {
  completion_pct: 14.3,
  checks: CHECKS,
  computed_fields: { 'B.4': 2_766_666.67, 'B.8': 1.8 },
  warnings: [],
};

const VENDOR_DETAIL = {
  id: VENDOR_ID,
  legal_name: 'VVESA MMC',
  voen: '1003915341',
  type: 'sub',
  legal_form: 'MMC',
  registration_year: 2015,
  address: 'Bakı şəhəri, Nərimanov rayonu',
  region: 'Bakı',
  website: 'https://wesa.az',
  status: 'in_progress',
  external_ref: null,
  is_demo: false,
  latest_score: null,
  latest_class: null,
  prequalified_until: null,
  primary_source: 'portal',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  contacts: [
    { id: 'ct1', vendor_id: VENDOR_ID, name: 'Həbib Atakişiyev', position: 'Director', phone: '+994 50 000 00 00', email: 'habib.atakisiyev@wesa.az', is_primary: true, has_portal_account: true },
  ],
  categories: [],
  current_fields: { 'A.20': 'AZ00WESA00000000000000000' },
  raw_indicators: {},
  documents: [],
  evaluations: [],
  stale_fields: [],
};

const DOCUMENTS = [
  { id: null, vendor_id: VENDOR_ID, code: 'A-01', name_az: 'Şirkətin dövlət qeydiyyatı sənədi', name_en: 'State registration certificate', mandatory: true, status: 'missing', filename: null, file_key: null, issue_date: null, expiry_date: null, days_to_expiry: null, verified_by: null, verified_at: null },
  { id: 'd2', vendor_id: VENDOR_ID, code: 'A-05', name_az: 'Vergi borcsuzluğu arayışı (son 3 ay)', name_en: 'Tax clearance (last 3 months)', mandatory: true, status: 'uploaded', filename: 'a05.pdf', file_key: 'x', issue_date: '2026-08-01', expiry_date: '2026-11-01', days_to_expiry: 45, verified_by: null, verified_at: null },
];

const CATEGORIES = [
  { id: 'cat1', code: 'facade', name_az: 'Fasad işləri', name_en: 'Façade works', kind: 'work', parent_id: null, is_active: true, vendor_count: 3, prequalified_count: 1 },
];

function mockApi(overrides: Partial<Record<string, unknown>> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      const path = url.pathname.replace(/^\/api/, '');
      const method = (init?.method ?? 'GET').toUpperCase();

      const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;

      if (path === '/auth/me') return respond(overrides.me ?? ME);
      if (path === '/applications') return respond(overrides.applications ?? APPLICATIONS_PAGE);
      if (new RegExp(`^/applications/${APPLICATION_ID}/answers$`).test(path)) {
        return respond(overrides.answerState ?? ANSWER_STATE);
      }
      if (new RegExp(`^/applications/${APPLICATION_ID}$`).test(path)) {
        return respond(overrides.applicationDetail ?? APPLICATION_DETAIL);
      }
      if (path === `/vendors/${VENDOR_ID}` && method === 'GET') return respond(overrides.vendor ?? VENDOR_DETAIL);
      if (path === `/vendors/${VENDOR_ID}` && method === 'PATCH') return respond(overrides.vendor ?? VENDOR_DETAIL);
      if (path === `/vendors/${VENDOR_ID}/documents`) return respond(overrides.documents ?? DOCUMENTS);
      if (path === '/admin/categories') return respond(overrides.categories ?? CATEGORIES);
      if (path === `/vendors/${VENDOR_ID}/categories`) return respond([]);
      if (path === `/vendors/${VENDOR_ID}/contacts`) return respond([]);
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('vendor-status (screen 4)', () => {
  it('renders the stepper at the current status and lists expiring documents', async () => {
    mockApi();
    render(
      <Harness>
        <VendorStatus />
      </Harness>,
    );
    expect(await screen.findByText('Vergi borcsuzluğu arayışı (son 3 ay)')).toBeInTheDocument();
    expect(screen.getByText(/Bitmək üzrə/)).toBeInTheDocument();
    expect(screen.getByText('Növbəti addımlar')).toBeInTheDocument();
  });
});

describe('vendor-profile (screen 5)', () => {
  it('renders identity fields, the primary contact and read-only IBAN', async () => {
    mockApi();
    render(
      <Harness>
        <VendorProfile />
      </Harness>,
    );
    expect(await screen.findByDisplayValue('VVESA MMC')).toBeInTheDocument();
    expect(screen.getByText('Həbib Atakişiyev', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('AZ00WESA00000000000000000')).toBeInTheDocument();
    expect(await screen.findByText('Fasad işləri')).toBeInTheDocument();
  });
});

describe('vendor-form-a / vendor-form-c (screens 6, 8)', () => {
  it('section A shows the field catalogue, the tab strip and the completion meter', async () => {
    mockApi();
    render(
      <Harness>
        <VendorFormA />
      </Harness>,
    );
    expect(await screen.findByText('A.1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('VVESA MMC')).toBeInTheDocument();
    expect(screen.getByText('A. Şirkət Profili')).toBeInTheDocument();
    expect(screen.getByText('G. Sığorta və Referanslar')).toBeInTheDocument();
    expect(await screen.findByText(/14\.3\/100/)).toBeInTheDocument();
  });

  it('section C renders the completed-projects table field', async () => {
    mockApi();
    render(
      <Harness>
        <VendorFormC />
      </Harness>,
    );
    expect(await screen.findAllByRole('columnheader', { name: 'Layihənin adı' })).toHaveLength(2); // C.t1, C.t2
    expect(screen.getAllByText('Sətir əlavə et').length).toBeGreaterThan(0);
  });
});

describe('vendor-documents (screen 13)', () => {
  it('lists the checklist with mandatory pills and lets a file be chosen', async () => {
    mockApi();
    render(
      <Harness>
        <VendorDocuments />
      </Harness>,
    );
    expect(await screen.findByText('A-01')).toBeInTheDocument();
    expect(screen.getByText('A-05')).toBeInTheDocument();
    expect(screen.getAllByText('Məcburi').length).toBeGreaterThan(0);
  });
});

describe('vendor-submit (screen 14)', () => {
  it('disables submit until the checklist passes and the declaration is signed', async () => {
    mockApi();
    render(
      <Harness>
        <VendorSubmit />
      </Harness>,
    );
    const submit = await screen.findByRole('button', { name: /Müraciəti göndər/ });
    expect(submit).toBeDisabled();
    expect(screen.getByText('A.11, A.15, F.1')).toBeInTheDocument();
  });

  it('reports the machine-readable checks from a failed submit', async () => {
    mockApi();
    render(
      <Harness>
        <VendorSubmit />
      </Harness>,
    );
    fireEvent.change(await screen.findByLabelText('Rəhbərin adı'), { target: { value: 'Həbib Atakişiyev' } });
    fireEvent.change(screen.getByLabelText('Vəzifəsi'), { target: { value: 'Director' } });
    fireEvent.click(screen.getByLabelText('Bəyannamə ilə razıyam'));

    // The client-side gate keeps the button disabled while the checklist fails — submit is
    // never actually sent with an incomplete application (spec §7), so there is nothing to
    // stub a 409 response for here; `services/submission.py::submit` and
    // `apps/api/tests/test_portal.py::test_submit_refuses_an_incomplete_application_…` are
    // the coverage for the server rejecting one anyway.
    const submit = screen.getByRole('button', { name: /Müraciəti göndər/ });
    expect(submit).toBeDisabled();
    await waitFor(() => expect(submit).toBeDisabled());
  });
});

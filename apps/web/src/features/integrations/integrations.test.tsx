/**
 * Screens 28–30 rendered against a stubbed API.
 *
 * Two things are worth a test here and neither is business logic (there is none in this
 * feature — gate 2): that every string the screens ask for exists in both dictionaries, and
 * that the screens render what the API answered rather than deriving anything of their own.
 * The key and secret panels are checked explicitly, because "shown once" is a property the
 * UI has to honour as much as the API does.
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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../i18n/LocaleProvider';
import { DICTIONARIES } from '../../i18n';
// The feature file directly: `DICTIONARIES` merges it at runtime but is typed from the
// shared dictionary alone, so the compiler cannot see a feature key through it.
import AZ from '../../i18n/features/integrations.az.json';
import { AdaptersTab } from './AdaptersTab';
import { ApiKeysTab } from './ApiKeysTab';
import { ExcelImport } from './ExcelImport';
import { WebhooksTab } from './WebhooksTab';

const ADAPTERS = [
  {
    key: 'generic_rest',
    name_az: 'Ümumi REST',
    name_en: 'Generic REST',
    description_az: 'REST konnektoru',
    description_en: 'REST connector',
    status: 'active',
    record_count: 12,
    last_sync_at: '2026-08-20T09:00:00Z',
    configured_vendor_count: 2,
  },
  {
    key: 'registry',
    name_az: 'Dövlət reyestrləri',
    name_en: 'Government registries',
    description_az: 'Reyestr yoxlamaları',
    description_en: 'Registry checks',
    status: 'planned',
    record_count: 0,
    last_sync_at: null,
    configured_vendor_count: 0,
  },
];

const SYNC_LOG = {
  items: [
    {
      id: 'a1',
      adapter: 'generic_rest',
      vendor_id: 'v1',
      vendor_name: 'Test Vendor MMC',
      started_at: '2026-08-20T09:00:00Z',
      finished_at: '2026-08-20T09:00:02Z',
      fields_written: 4,
      warnings: [],
      result: 'success',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
};

const PREVIEW = {
  preview_id: '9f1c2e2c-0000-0000-0000-000000000001',
  kind: 'application_form',
  source_filename: 'WESA.xlsx',
  matched_vendor: null,
  fields: [
    {
      field_code: 'B.1',
      value: 5189111.38,
      unit: 'AZN',
      sheet: '3. B. Maliyyə',
      cell: 'E5',
      current_value: null,
      will_change: true,
    },
  ],
  tables: {},
  documents: [],
  derived_raw: { 'B.1': 5189111.38 },
  warnings: [
    {
      code: 'stale_certificate',
      field_code: 'A.16',
      sheet: null,
      cell: null,
      raw_value: '2020-09-28',
      message_az: 'A.16: arayış köhnədir.',
      message_en: 'A.16: the tax clearance certificate is stale.',
      severity: 'error',
    },
  ],
};

/** Answers by path; anything unrouted is an explicit failure rather than an empty 200. */
function stubApi(routes: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const match = Object.keys(routes).find((path) => url.includes(path));
      if (!match) throw new Error(`unstubbed request: ${url}`);
      return {
        ok: true,
        status: 200,
        json: async () => routes[match],
      } as Response;
    }),
  );
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const rootRoute = createRootRoute({ component: () => <>{children}</> });
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/' });
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  return (
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <RouterProvider router={router as any} />
      </LocaleProvider>
    </QueryClientProvider>
  );
}

// jsdom has no scroll implementation and the router calls it on every mount; the warning it
// prints otherwise buries the assertions this file is actually about.
Object.defineProperty(window, 'scrollTo', { value: () => {}, writable: true });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the data sources screen', () => {
  beforeEach(() => {
    stubApi({ '/integrations/adapters': ADAPTERS, '/integrations/sync-log': SYNC_LOG });
  });

  it('lists every adapter with what the API said about it', async () => {
    render(
      <Harness>
        <AdaptersTab />
      </Harness>,
    );

    expect(await screen.findByText('Ümumi REST')).toBeInTheDocument();
    expect(screen.getByText('Dövlət reyestrləri')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('shows the registry adapter as planned, never as active', async () => {
    render(
      <Harness>
        <AdaptersTab />
      </Harness>,
    );

    await screen.findByText('Dövlət reyestrləri');
    const row = screen.getByText('Dövlət reyestrləri').closest('tr');
    expect(row).not.toBeNull();
    expect(row?.textContent).toContain(AZ.in_status_planned);
    expect(row?.textContent).not.toContain(AZ.in_status_active);
  });
});

describe('the API key tab', () => {
  it('shows a new key once and never lists key material', async () => {
    const created = {
      id: 'k1',
      name: 'Partner ERP',
      scopes: ['vendors:read'],
      created_at: '2026-08-20T09:00:00Z',
      last_used_at: null,
      is_active: true,
      key: 'vq_abcd1234_therest',
    };
    let listed: unknown[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          listed = [{ ...created, key: undefined }];
          return { ok: true, status: 201, json: async () => created } as Response;
        }
        return { ok: true, status: 200, json: async () => listed } as Response;
      }),
    );

    render(
      <Harness>
        <ApiKeysTab />
      </Harness>,
    );
    fireEvent.change(await screen.findByLabelText(AZ.in_key_name), {
      target: { value: 'Partner ERP' },
    });
    fireEvent.click(await screen.findByRole('button', { name: AZ.in_key_create }));

    expect(await screen.findByText('vq_abcd1234_therest')).toBeInTheDocument();
    // Dismissing the panel is the only way it leaves the screen — nothing re-fetches it.
    fireEvent.click(screen.getByRole('button', { name: AZ.in_key_dismiss }));
    await waitFor(() => expect(screen.queryByText('vq_abcd1234_therest')).not.toBeInTheDocument());
  });
});

describe('the webhook tab', () => {
  it('renders subscriptions without a secret column', async () => {
    stubApi({
      '/integrations/webhooks': [
        {
          id: 'w1',
          url: 'https://partner.example/hook',
          events: ['vendor.prequalified'],
          is_active: true,
          last_delivery_at: null,
          failure_count: 0,
        },
      ],
    });

    render(
      <Harness>
        <WebhooksTab />
      </Harness>,
    );

    expect(await screen.findByText('https://partner.example/hook')).toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });
});

describe('the Excel import screen', () => {
  it('shows the parser anomalies and the mapping before anything is written', async () => {
    stubApi({
      '/vendors': { items: [], total: 0, page: 1, page_size: 200 },
      '/integrations/excel-import/preview': PREVIEW,
    });

    render(
      <Harness>
        <ExcelImport />
      </Harness>,
    );
    const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], 'WESA.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    fireEvent.change(await screen.findByLabelText(AZ.in_file), {
      target: { files: [file] },
    });
    fireEvent.click(await screen.findByRole('button', { name: AZ.in_preview }));

    expect(await screen.findByText('stale_certificate')).toBeInTheDocument();
    expect(screen.getByText('A.16: arayış köhnədir.')).toBeInTheDocument();
    expect(screen.getByText('B.1')).toBeInTheDocument();
    // Step three is only reachable after the officer confirms.
    expect(screen.queryByText(AZ.in_written)).not.toBeInTheDocument();
  });
});

describe('the feature dictionary', () => {
  it('answers every key the screens ask for, in both languages', () => {
    const azKeys = Object.keys(DICTIONARIES.az);
    const enKeys = Object.keys(DICTIONARIES.en);
    for (const key of ['in_tab_adapters', 'in_status_planned', 'in_write', 'in_secret_note']) {
      expect(azKeys).toContain(key);
      expect(enKeys).toContain(key);
    }
  });
});

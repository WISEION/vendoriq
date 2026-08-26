import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LocaleProvider } from '../../i18n/LocaleProvider';
import { ProjectsListScreen } from './ProjectsListScreen';

vi.mock('@tanstack/react-router', () => ({
  // The router is not wired for these screens yet (task 2C's report: change request to the
  // orchestrator) — a plain anchor is a faithful enough stand-in for what `Link` renders.
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('../../api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue({
    items: [
      {
        id: 'p1',
        code: 'TQS-238',
        name: 'Gənclik Bahar Residence',
        client: 'Uni Ko QSC',
        stage: 'tender',
        estimated_value: 14700000,
        deadline: '2026-12-01',
        external_ref: null,
        is_demo: false,
        package_count: 7,
        coverage_pct: 76,
        match_state: 'nogo',
        last_matched_at: '2026-08-24T10:00:00Z',
      },
    ],
    total: 1,
    page: 1,
    page_size: 100,
  }),
}));

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <ProjectsListScreen />
      </LocaleProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('ProjectsListScreen', () => {
  it('renders a project row with its coverage, package count and the go/no-go pill as text', async () => {
    renderScreen();

    await waitFor(() => expect(screen.getByText('TQS-238')).toBeInTheDocument());
    expect(screen.getByText('Gənclik Bahar Residence')).toBeInTheDocument();
    expect(screen.getByText('76%')).toBeInTheDocument();
    // The go/no-go state is text, not colour alone (brief §2C accessibility rule).
    expect(screen.getByText('NO-GO')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === '7 paket')).toBeInTheDocument();
  });
});

import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router';
import type { QueryClient } from '@tanstack/react-query';
import { sessionQueryOptions, homeRouteFor } from '../auth/session';
import { StaffSignIn } from '../features/auth/StaffSignIn';
import { VendorRegister as VendorSelfRegistration } from '../features/auth/VendorRegister';
import { VendorSignIn } from '../features/auth/VendorSignIn';
import {
  ApplicationsQueue,
  CommissionSummary,
  Evaluation,
  Overview,
  VendorDetail,
  VendorRegister,
} from '../features/manager';
import { CyclesScreen } from '../features/projects/CyclesScreen';
import { ProjectEditScreen } from '../features/projects/ProjectEditScreen';
import { ProjectMatchingScreen } from '../features/projects/ProjectMatchingScreen';
import { ProjectsListScreen } from '../features/projects/ProjectsListScreen';
import { DataSources, ErpConnector, ExcelImport } from '../features/integrations';
import {
  VendorApplicationForm,
  VendorDocuments,
  VendorProfile,
  VendorStatus,
  VendorSubmit,
} from '../features/vendor';
import { FORM_SECTION_KEYS } from '../features/vendor/fieldCatalog';
import type { SectionKey } from '../features/vendor/fieldCatalog';
import { AppShell } from './AppShell';
import { Page } from './Page';
import { PAGE_TEXT } from './navigation';
import { VENDOR_HOME_PATH, VENDOR_LOGIN_PATH } from './paths';
import { queryClient } from './queryClient';

interface RouterContext {
  queryClient: QueryClient;
}

interface RedirectSearch {
  /** The page a signed-out visit was headed to, so login can return there. */
  redirect?: string;
}

function validateRedirectSearch(search: Record<string, unknown>): RedirectSearch {
  return typeof search.redirect === 'string' ? { redirect: search.redirect } : {};
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
});

/** `/login`, `/login/staff`, `/register` — no rail, no topbar, no session required. */
const publicLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'public',
  component: () => <Outlet />,
});

const vendorSignInRoute = createRoute({
  getParentRoute: () => publicLayoutRoute,
  path: '/login',
  validateSearch: validateRedirectSearch,
  component: VendorSignIn,
});

const staffSignInRoute = createRoute({
  getParentRoute: () => publicLayoutRoute,
  path: '/login/staff',
  validateSearch: validateRedirectSearch,
  component: StaffSignIn,
});

const vendorRegisterRoute = createRoute({
  getParentRoute: () => publicLayoutRoute,
  path: '/register',
  component: VendorSelfRegistration,
});

/**
 * Every screen behind a session. `beforeLoad` resolves `/auth/me` from the same query the
 * rest of the app reads (`../auth/session`) — a signed-out visit is redirected to the vendor
 * sign-in screen with `redirect` carrying the page it was headed to, so login can return
 * there; a vendor is confined to `/portal/*` (spec §7 — the workspace switch is a staff-only
 * convenience, not a vendor capability).
 */
const protectedLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'protected',
  beforeLoad: async ({ context, location }) => {
    const principal = await context.queryClient.ensureQueryData(sessionQueryOptions);
    if (!principal) {
      throw redirect({ to: VENDOR_LOGIN_PATH, search: { redirect: location.href } });
    }
    if (principal.role === 'vendor' && !location.pathname.startsWith(VENDOR_HOME_PATH)) {
      throw redirect({ to: VENDOR_HOME_PATH });
    }
    return { principal };
  },
  component: AppShell,
});

/**
 * The screens of `docs/SCREENS.md`, at the addresses that document fixes.
 *
 * A screen that has a component is mounted with it; one whose feature has not landed yet
 * renders the empty `<Page>` its `PAGE_TEXT` entry describes, so every address in the map
 * resolves from the day it is written rather than 404-ing until its owner finishes.
 */
const SCREENS: { path: string; component: () => JSX.Element }[] = [
  // manager — screens 15, 16, 18
  { path: '/', component: () => <Page route="/">{<Overview />}</Page> },
  { path: '/vendors', component: () => <Page route="/vendors">{<VendorRegister />}</Page> },
  {
    path: '/applications',
    component: () => <Page route="/applications">{<ApplicationsQueue />}</Page>,
  },
  // projects & cycles — screens 21, 22. These two render their own page head, so they are
  // mounted bare: wrapping them in <Page> put the same heading on screen twice.
  { path: '/cycles', component: () => <CyclesScreen /> },
  { path: '/projects', component: () => <ProjectsListScreen /> },
  // integrations — screen 28
  { path: '/integrations', component: () => <Page route="/integrations">{<DataSources />}</Page> },
  // vendor portal — screens 4, 5, 13, 14
  { path: '/portal', component: () => <Page route="/portal">{<VendorStatus />}</Page> },
  {
    path: '/portal/profile',
    component: () => <Page route="/portal/profile">{<VendorProfile />}</Page>,
  },
  {
    path: '/portal/documents',
    component: () => <Page route="/portal/documents">{<VendorDocuments />}</Page>,
  },
  {
    path: '/portal/submit',
    component: () => <Page route="/portal/submit">{<VendorSubmit />}</Page>,
  },
];

/**
 * Paths a route below already owns, and which must therefore NOT also get a generated
 * placeholder. `/portal/application` is the one that bites: `PAGE_TEXT` describes it because
 * the rail links to it, and the redirect route owns it because it is not a screen of its own.
 * Registering both made TanStack throw "Duplicate routes found" at router construction — a
 * blank page in every browser, while typecheck, lint, vitest and the build all stayed green.
 */
const CLAIMED_PATHS = new Set(['/portal/application']);

/** Addresses whose feature has not landed yet — still reachable, still headed and described. */
const PENDING_SCREENS = Object.keys(PAGE_TEXT).filter(
  (path) => !CLAIMED_PATHS.has(path) && !SCREENS.some((screen) => screen.path === path),
);

const screenRoutes = [
  ...SCREENS.map((screen) =>
    createRoute({
      getParentRoute: () => protectedLayoutRoute,
      path: screen.path,
      component: screen.component,
    }),
  ),
  ...PENDING_SCREENS.map((path) =>
    createRoute({
      getParentRoute: () => protectedLayoutRoute,
      path,
      component: () => <Page route={path} />,
    }),
  ),
];

/**
 * Screens reached from a parent rather than the rail (`docs/SCREENS.md` names the seven).
 * Each takes its parameter as a prop, so the component knows nothing about the router.
 */
const vendorDetailRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/vendors/$vendorId',
  component: function VendorDetailRoute() {
    const { vendorId } = vendorDetailRoute.useParams();
    return <VendorDetail vendorId={vendorId} />;
  },
});

const evaluationRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/applications/$applicationId',
  component: function EvaluationRoute() {
    const { applicationId } = evaluationRoute.useParams();
    return <Evaluation applicationId={applicationId} />;
  },
});

const commissionSummaryRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/applications/$applicationId/summary',
  component: function CommissionSummaryRoute() {
    const { applicationId } = commissionSummaryRoute.useParams();
    return <CommissionSummary applicationId={applicationId} />;
  },
});

const projectCreateRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/projects/new',
  component: () => <ProjectEditScreen />,
});

const projectMatchingRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/projects/$projectId',
  component: function ProjectMatchingRoute() {
    const { projectId } = projectMatchingRoute.useParams();
    return <ProjectMatchingScreen projectId={projectId} />;
  },
});

const projectEditRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/projects/$projectId/edit',
  component: function ProjectEditRoute() {
    const { projectId } = projectEditRoute.useParams();
    return <ProjectEditScreen projectId={projectId} />;
  },
});

const excelImportRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/integrations/excel-import',
  component: () => <ExcelImport />,
});

const erpConnectorRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/integrations/adapters/$adapter',
  component: function ErpConnectorRoute() {
    const { adapter } = erpConnectorRoute.useParams();
    return <ErpConnector adapter={adapter} />;
  },
});

/**
 * Sections A–G of the application form: seven addresses, one component.
 * `/portal/application` alone redirects to A rather than showing an eighth, empty thing.
 */
const applicationRedirectRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/portal/application',
  beforeLoad: () => {
    throw redirect({ to: '/portal/application/$section', params: { section: 'A' } });
  },
});

const applicationSectionRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '/portal/application/$section',
  parseParams: (params: Record<string, string>) => {
    // An unknown letter is not a section; sending it to A beats rendering an empty form.
    const section = params.section?.toUpperCase() ?? 'A';
    return {
      section: (FORM_SECTION_KEYS.includes(section as SectionKey) ? section : 'A') as SectionKey,
    };
  },
  component: function ApplicationSectionRoute() {
    const { section } = applicationSectionRoute.useParams();
    return (
      <Page route="/portal/application">
        <VendorApplicationForm section={section} />
      </Page>
    );
  },
});

const nestedRoutes = [
  vendorDetailRoute,
  evaluationRoute,
  commissionSummaryRoute,
  projectCreateRoute,
  projectMatchingRoute,
  projectEditRoute,
  excelImportRoute,
  erpConnectorRoute,
  applicationRedirectRoute,
  applicationSectionRoute,
];

const notFoundRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '$',
  component: () => <Page route="/" />,
});

export const routeTree = rootRoute.addChildren([
  publicLayoutRoute.addChildren([vendorSignInRoute, staffSignInRoute, vendorRegisterRoute]),
  protectedLayoutRoute.addChildren([...screenRoutes, ...nestedRoutes, notFoundRoute]),
]);

export { homeRouteFor };

// The same `QueryClient` instance `<QueryClientProvider>` uses in `App.tsx` (`./queryClient.ts`)
// — the router is created once, at module load, outside React, so it cannot read it from context.
export const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

export { Outlet };

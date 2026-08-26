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
import { VendorRegister } from '../features/auth/VendorRegister';
import { VendorSignIn } from '../features/auth/VendorSignIn';
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
  component: VendorRegister,
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

/** One route per rail entry; nested screens are added by the feature teams under these. */
const screenRoutes = Object.keys(PAGE_TEXT).map((path) =>
  createRoute({
    getParentRoute: () => protectedLayoutRoute,
    path,
    component: () => <Page route={path} />,
  }),
);

const notFoundRoute = createRoute({
  getParentRoute: () => protectedLayoutRoute,
  path: '$',
  component: () => <Page route="/" />,
});

export const routeTree = rootRoute.addChildren([
  publicLayoutRoute.addChildren([vendorSignInRoute, staffSignInRoute, vendorRegisterRoute]),
  protectedLayoutRoute.addChildren([...screenRoutes, notFoundRoute]),
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

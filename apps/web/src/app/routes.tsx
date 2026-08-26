import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router';
import { AppShell } from './AppShell';
import { Page } from './Page';
import { PAGE_TEXT } from './navigation';

const rootRoute = createRootRoute({ component: AppShell });

/** One route per rail entry; nested screens are added by the feature teams under these. */
const screenRoutes = Object.keys(PAGE_TEXT).map((path) =>
  createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: () => <Page route={path} />,
  }),
);

const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '$',
  component: () => <Page route="/" />,
});

export const routeTree = rootRoute.addChildren([...screenRoutes, notFoundRoute]);

export const router = createRouter({ routeTree, defaultPreload: 'intent' });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

export { Outlet };

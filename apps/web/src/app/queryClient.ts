import { QueryClient } from '@tanstack/react-query';

/**
 * One instance, shared between the React tree (`App.tsx`) and the router (`routes.tsx`):
 * route guards call `queryClient.ensureQueryData(sessionQueryOptions)` to decide whether a
 * visit needs a redirect to a login screen, and that must hit the same cache the rest of the
 * app reads session state from — a second `QueryClient` would just re-fetch and disagree.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
  },
});

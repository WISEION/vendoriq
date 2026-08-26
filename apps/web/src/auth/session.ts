import { queryOptions } from '@tanstack/react-query';
import { getMe } from '../api/auth';
import { ApiError } from '../api/client';
import type { Success } from '../api/http';

/** `GET /auth/me` — the identity, its role and the operation ids it may call (openapi.yaml `Me`). */
export type Principal = Success<'getMe'>;

async function fetchPrincipal(): Promise<Principal | null> {
  try {
    return await getMe();
  } catch (error) {
    // No session is a normal, expected outcome for a first visit — not a query failure.
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/**
 * Shared between `SessionProvider` (reads it for the whole tree) and the router's
 * `beforeLoad` guards (call `queryClient.ensureQueryData` with it) so both agree on one cache
 * entry instead of racing two independent fetches of `/auth/me`.
 */
export const sessionQueryOptions = queryOptions({
  queryKey: ['session', 'me'] as const,
  queryFn: fetchPrincipal,
  staleTime: 60_000,
  retry: false,
});

/**
 * Where a signed-in identity lands: vendors get the portal, every staff role gets the
 * dashboard. Takes just the role so it works for both `Me` (`/auth/me`) and `Session.user`
 * (the login endpoints) — the two shapes the login screens see it on.
 */
export function homeRouteFor(identity: { role: Principal['role'] }): string {
  return identity.role === 'vendor' ? '/portal' : '/';
}

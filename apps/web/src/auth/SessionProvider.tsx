import { createContext, useCallback, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { sessionQueryOptions } from './session';
import type { Principal } from './session';

export type Session =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; principal: Principal };

interface SessionContextValue {
  session: Session;
  /** Re-reads `/auth/me` — call after login and logout so every consumer sees the new identity. */
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

/** The one place that knows the session lives in a TanStack Query cache entry (spec: state-decouple-implementation). */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery(sessionQueryOptions);

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: sessionQueryOptions.queryKey });
  }, [queryClient]);

  const session: Session = useMemo(() => {
    if (isPending) return { status: 'loading' };
    if (!data) return { status: 'anonymous' };
    return { status: 'authenticated', principal: data };
  }, [isPending, data]);

  const value = useMemo<SessionContextValue>(() => ({ session, refresh }), [session, refresh]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}

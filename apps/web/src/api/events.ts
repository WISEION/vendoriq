/**
 * The domain event log.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call } from './http';
import type { Query } from './http';

/** The domain event log */
export const listEvents = (query?: Query<'listEvents'>) =>
  call<'listEvents'>('get', '/events', { query });

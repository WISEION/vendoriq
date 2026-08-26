/**
 * Qualification cycles and invitations.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call } from './http';
import type { Body, PathParams, Query } from './http';

/** Qualification cycles */
export const listCycles = (query?: Query<'listCycles'>) =>
  call<'listCycles'>('get', '/cycles', { query });

/** Create a cycle */
export const createCycle = (body: Body<'createCycle'>) =>
  call<'createCycle'>('post', '/cycles', { body });

/** Cycle detail with application counts by status */
export const getCycle = (params: PathParams<'getCycle'>) =>
  call<'getCycle'>('get', '/cycles/{cycle_id}', { params });

/** Update a cycle */
export const patchCycle = (params: PathParams<'patchCycle'>, body: Body<'patchCycle'>) =>
  call<'patchCycle'>('patch', '/cycles/{cycle_id}', { params, body });

/** Delete a draft cycle */
export const deleteCycle = (params: PathParams<'deleteCycle'>) =>
  call<'deleteCycle'>('delete', '/cycles/{cycle_id}', { params });

/** Bulk-invite vendors to the cycle */
export const inviteToCycle = (params: PathParams<'inviteToCycle'>, body: Body<'inviteToCycle'>) =>
  call<'inviteToCycle'>('post', '/cycles/{cycle_id}/invite', { params, body });

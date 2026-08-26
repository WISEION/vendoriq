/**
 * Versioned criteria sets; immutable once used.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call } from './http';
import type { Body, PathParams, Query } from './http';

/** All model versions */
export const listScoringModels = (query?: Query<'listScoringModels'>) =>
  call<'listScoringModels'>('get', '/scoring-models', { query });

/** Create a draft from an existing version */
export const createScoringModelDraft = (body: Body<'createScoringModelDraft'>) =>
  call<'createScoringModelDraft'>('post', '/scoring-models', { body });

/** Full criteria set of one version */
export const getScoringModel = (params: PathParams<'getScoringModel'>) =>
  call<'getScoringModel'>('get', '/scoring-models/{version}', { params });

/** Edit an unlocked draft */
export const patchScoringModelDraft = (
  params: PathParams<'patchScoringModelDraft'>,
  body: Body<'patchScoringModelDraft'>,
) => call<'patchScoringModelDraft'>('patch', '/scoring-models/{version}', { params, body });

/** Re-score a past cycle with this draft */
export const testRescore = (params: PathParams<'testRescore'>, body: Body<'testRescore'>) =>
  call<'testRescore'>('post', '/scoring-models/{version}/test-rescore', { params, body });

/** Publish a draft */
export const publishScoringModel = (
  params: PathParams<'publishScoringModel'>,
  body: Body<'publishScoringModel'>,
) => call<'publishScoringModel'>('post', '/scoring-models/{version}/publish', { params, body });

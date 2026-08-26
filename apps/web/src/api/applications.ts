/**
 * Cycle-bound applications, evaluation, decisions and commission exports.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call, callBinary } from './http';
import type { Body, PathParams, Query } from './http';

/** The evaluation queue */
export const listApplications = (query?: Query<'listApplications'>) =>
  call<'listApplications'>('get', '/applications', { query });

/** Application detail */
export const getApplication = (params: PathParams<'getApplication'>) =>
  call<'getApplication'>('get', '/applications/{application_id}', { params });

/** Autosave form answers */
export const patchAnswers = (params: PathParams<'patchAnswers'>, body: Body<'patchAnswers'>) =>
  call<'patchAnswers'>('patch', '/applications/{application_id}/answers', { params, body });

/** Sign the declaration and submit */
export const submitApplication = (
  params: PathParams<'submitApplication'>,
  body: Body<'submitApplication'>,
) => call<'submitApplication'>('post', '/applications/{application_id}/submit', { params, body });

/** The evaluation sheet */
export const getEvaluation = (params: PathParams<'getEvaluation'>) =>
  call<'getEvaluation'>('get', '/applications/{application_id}/evaluation', { params });

/** Save the officer's rubric scores */
export const putEvaluation = (params: PathParams<'putEvaluation'>, body: Body<'putEvaluation'>) =>
  call<'putEvaluation'>('put', '/applications/{application_id}/evaluation', { params, body });

/** Score without saving */
export const computeScore = (params: PathParams<'computeScore'>, body: Body<'computeScore'>) =>
  call<'computeScore'>('post', '/applications/{application_id}/compute', { params, body });

/** Approve, reject or request information */
export const decideApplication = (
  params: PathParams<'decideApplication'>,
  body: Body<'decideApplication'>,
) => call<'decideApplication'>('post', '/applications/{application_id}/decide', { params, body });

/** Record the second evaluator's rubric set */
export const putSecondEvaluation = (
  params: PathParams<'putSecondEvaluation'>,
  body: Body<'putSecondEvaluation'>,
) =>
  call<'putSecondEvaluation'>('put', '/applications/{application_id}/second-evaluator', {
    params,
    body,
  });

/** Commission summary for signature (Excel) */
export const exportCommissionSummaryXlsx = (params: PathParams<'exportCommissionSummaryXlsx'>) =>
  callBinary<'exportCommissionSummaryXlsx'>('get', '/cycles/{cycle_id}/export-summary.xlsx', {
    params,
  });

/** Commission summary for signature (PDF) */
export const exportCommissionSummaryPdf = (params: PathParams<'exportCommissionSummaryPdf'>) =>
  callBinary<'exportCommissionSummaryPdf'>('get', '/cycles/{cycle_id}/export-summary.pdf', {
    params,
  });

/**
 * Market intelligence views (spec §12).
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call } from './http';
import type { Query } from './http';

/** Dashboard KPI tiles */
export const getIntelOverview = () => call<'getIntelOverview'>('get', '/intel/overview');

/** Category × class coverage matrix */
export const getIntelCoverage = (query?: Query<'getIntelCoverage'>) =>
  call<'getIntelCoverage'>('get', '/intel/coverage', { query });

/** How many vendors sit in each class */
export const getClassDistribution = (query?: Query<'getClassDistribution'>) =>
  call<'getClassDistribution'>('get', '/intel/class-distribution', { query });

/** Aggregate capacity per category */
export const getIntelCapacity = () => call<'getIntelCapacity'>('get', '/intel/capacity');

/** Certification and insurance penetration */
export const getIntelCertification = () =>
  call<'getIntelCertification'>('get', '/intel/certification');

/** Data-source split and stale-profile count */
export const getIntelSources = () => call<'getIntelSources'>('get', '/intel/sources');

/** Documents expiring within N days */
export const getExpiringDocuments = (query?: Query<'getExpiringDocuments'>) =>
  call<'getExpiringDocuments'>('get', '/intel/expiring-documents', { query });

/** Categories with no prequalified vendor */
export const getMarketGaps = () => call<'getMarketGaps'>('get', '/intel/gaps');

/** What needs a human today */
export const getAttentionList = () => call<'getAttentionList'>('get', '/intel/attention');

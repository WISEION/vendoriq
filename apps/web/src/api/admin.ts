/**
 * Categories, users, settings and the audit log.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call, callBinary } from './http';
import type { Body, PathParams, Query } from './http';

/** The category taxonomy */
export const listCategories = (query?: Query<'listCategories'>) =>
  call<'listCategories'>('get', '/admin/categories', { query });

/** Add a category */
export const createCategory = (body: Body<'createCategory'>) =>
  call<'createCategory'>('post', '/admin/categories', { body });

/** Rename or re-parent a category */
export const patchCategory = (params: PathParams<'patchCategory'>, body: Body<'patchCategory'>) =>
  call<'patchCategory'>('patch', '/admin/categories/{category_id}', { params, body });

/** Deactivate a category */
export const deleteCategory = (params: PathParams<'deleteCategory'>) =>
  call<'deleteCategory'>('delete', '/admin/categories/{category_id}', { params });

/** Accounts */
export const listUsers = (query?: Query<'listUsers'>) =>
  call<'listUsers'>('get', '/admin/users', { query });

/** Create an account */
export const createUser = (body: Body<'createUser'>) =>
  call<'createUser'>('post', '/admin/users', { body });

/** Update an account */
export const patchUser = (params: PathParams<'patchUser'>, body: Body<'patchUser'>) =>
  call<'patchUser'>('patch', '/admin/users/{user_id}', { params, body });

/** Deactivate an account */
export const deactivateUser = (params: PathParams<'deactivateUser'>) =>
  call<'deactivateUser'>('delete', '/admin/users/{user_id}', { params });

/** Change a role */
export const putUserRole = (params: PathParams<'putUserRole'>, body: Body<'putUserRole'>) =>
  call<'putUserRole'>('put', '/admin/users/{user_id}/role', { params, body });

/** All organisation settings */
export const getSettings = () => call<'getSettings'>('get', '/admin/settings');

/** Update settings */
export const putSettings = (body: Body<'putSettings'>) =>
  call<'putSettings'>('put', '/admin/settings', { body });

/** The audit log */
export const listAuditEvents = (query?: Query<'listAuditEvents'>) =>
  call<'listAuditEvents'>('get', '/admin/audit', { query });

/** Export the audit log for committee minutes */
export const exportAuditLog = (query?: Query<'exportAuditLog'>) =>
  callBinary<'exportAuditLog'>('get', '/admin/audit/export.xlsx', { query });

/**
 * Projects, work packages and matching runs.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call, callBinary } from './http';
import type { Body, PathParams, Query } from './http';

/** Project list with coverage and go/no-go */
export const listProjects = (query?: Query<'listProjects'>) =>
  call<'listProjects'>('get', '/projects', { query });

/** Create a project */
export const createProject = (body: Body<'createProject'>) =>
  call<'createProject'>('post', '/projects', { body });

/** Project detail with its packages */
export const getProject = (params: PathParams<'getProject'>) =>
  call<'getProject'>('get', '/projects/{project_id}', { params });

/** Update a project */
export const patchProject = (params: PathParams<'patchProject'>, body: Body<'patchProject'>) =>
  call<'patchProject'>('patch', '/projects/{project_id}', { params, body });

/** Delete a project and its packages */
export const deleteProject = (params: PathParams<'deleteProject'>) =>
  call<'deleteProject'>('delete', '/projects/{project_id}', { params });

/** Work and material packages */
export const listPackages = (params: PathParams<'listPackages'>) =>
  call<'listPackages'>('get', '/projects/{project_id}/packages', { params });

/** Add a package */
export const createPackage = (params: PathParams<'createPackage'>, body: Body<'createPackage'>) =>
  call<'createPackage'>('post', '/projects/{project_id}/packages', { params, body });

/** Update a package */
export const patchPackage = (params: PathParams<'patchPackage'>, body: Body<'patchPackage'>) =>
  call<'patchPackage'>('patch', '/projects/{project_id}/packages/{package_id}', { params, body });

/** Remove a package */
export const deletePackage = (params: PathParams<'deletePackage'>) =>
  call<'deletePackage'>('delete', '/projects/{project_id}/packages/{package_id}', { params });

/** Run matching and persist the result */
export const runMatch = (params: PathParams<'runMatch'>, body: Body<'runMatch'>) =>
  call<'runMatch'>('post', '/projects/{project_id}/match', { params, body });

/** The most recent matching run */
export const getLatestMatch = (params: PathParams<'getLatestMatch'>) =>
  call<'getLatestMatch'>('get', '/projects/{project_id}/match/latest', { params });

/** Export packages and the latest matching result */
export const exportProject = (params: PathParams<'exportProject'>) =>
  callBinary<'exportProject'>('get', '/projects/{project_id}/export.xlsx', { params });

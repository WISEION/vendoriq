/**
 * Adapters, Excel import, API keys and webhooks.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call, callMultipart } from './http';
import type { Body, PathParams, Query } from './http';

/** Available adapters with status and last sync */
export const listAdapters = () => call<'listAdapters'>('get', '/integrations/adapters');

/** Per-vendor connector configuration */
export const getAdapterConfig = (params: PathParams<'getAdapterConfig'>) =>
  call<'getAdapterConfig'>('get', '/integrations/adapters/{adapter}/vendors/{vendor_id}/config', {
    params,
  });

/** Configure the connector for one vendor */
export const putAdapterConfig = (
  params: PathParams<'putAdapterConfig'>,
  body: Body<'putAdapterConfig'>,
) =>
  call<'putAdapterConfig'>('put', '/integrations/adapters/{adapter}/vendors/{vendor_id}/config', {
    params,
    body,
  });

/** Run an adapter now */
export const runSync = (params: PathParams<'runSync'>, body: Body<'runSync'>) =>
  call<'runSync'>('post', '/integrations/adapters/{adapter}/sync', { params, body });

/** Adapter run history */
export const listSyncLog = (query?: Query<'listSyncLog'>) =>
  call<'listSyncLog'>('get', '/integrations/sync-log', { query });

/** Parse an uploaded workbook and show the mapping */
export const previewExcelImport = (
  file: File,
  fields: { kind?: 'application_form' | 'scoring_workbook'; vendor_id?: string } = {},
) => {
  const formData = new FormData();
  formData.append('file', file);
  if (fields.kind) formData.append('kind', fields.kind);
  if (fields.vendor_id) formData.append('vendor_id', fields.vendor_id);
  return callMultipart<'previewExcelImport'>(
    'post',
    '/integrations/excel-import/preview',
    formData,
  );
};

/** Write a confirmed preview into the register */
export const createExcelImportRun = (body: Body<'createExcelImportRun'>) =>
  call<'createExcelImportRun'>('post', '/integrations/excel-import/runs', { body });

/** API keys */
export const listApiKeys = () => call<'listApiKeys'>('get', '/integrations/api-keys');

/** Create an API key */
export const createApiKey = (body: Body<'createApiKey'>) =>
  call<'createApiKey'>('post', '/integrations/api-keys', { body });

/** Rename a key or change its scopes */
export const patchApiKey = (params: PathParams<'patchApiKey'>, body: Body<'patchApiKey'>) =>
  call<'patchApiKey'>('patch', '/integrations/api-keys/{api_key_id}', { params, body });

/** Revoke a key */
export const revokeApiKey = (params: PathParams<'revokeApiKey'>) =>
  call<'revokeApiKey'>('delete', '/integrations/api-keys/{api_key_id}', { params });

/** Webhook subscriptions */
export const listWebhooks = () => call<'listWebhooks'>('get', '/integrations/webhooks');

/** Subscribe to domain events */
export const createWebhook = (body: Body<'createWebhook'>) =>
  call<'createWebhook'>('post', '/integrations/webhooks', { body });

/** Update a subscription */
export const patchWebhook = (params: PathParams<'patchWebhook'>, body: Body<'patchWebhook'>) =>
  call<'patchWebhook'>('patch', '/integrations/webhooks/{webhook_id}', { params, body });

/** Remove a subscription */
export const deleteWebhook = (params: PathParams<'deleteWebhook'>) =>
  call<'deleteWebhook'>('delete', '/integrations/webhooks/{webhook_id}', { params });

/** Send a signed test delivery */
export const testWebhook = (params: PathParams<'testWebhook'>) =>
  call<'testWebhook'>('post', '/integrations/webhooks/{webhook_id}/test', { params });

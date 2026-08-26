/**
 * The integration screens' data access — TanStack Query options and mutations.
 *
 * Nothing here decides anything. Every field the screens show (an adapter's status, whether a
 * value will change, why a sync failed) is computed by the API and read from the response;
 * the web app transports and renders (brief §2, gate 2).
 */
import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import type { UseMutationResult } from '@tanstack/react-query';
import { listEvents } from '../../api/events';
import {
  createApiKey,
  createExcelImportRun,
  createWebhook,
  deleteWebhook,
  getAdapterConfig,
  listAdapters,
  listApiKeys,
  listSyncLog,
  listWebhooks,
  patchApiKey,
  previewExcelImport,
  putAdapterConfig,
  revokeApiKey,
  runSync,
  testWebhook,
} from '../../api/integrations';
import { listVendors } from '../../api/vendors';
import type { Body, PathParams, Success } from '../../api/http';

export type Adapter = Success<'listAdapters'>[number];
export type AdapterConfig = Success<'getAdapterConfig'>;
export type SyncLogEntry = Success<'listSyncLog'>['items'][number];
export type ImportPreview = Success<'previewExcelImport'>;
export type ImportWarning = NonNullable<ImportPreview['warnings']>[number];
/**
 * An adapter run reports transport failures, not workbook cells, so the contract gives it its
 * own shape with its own code vocabulary (`SyncWarning`). Both reach the same row component,
 * so the component takes the union; `severity` is required on both, which is what a client
 * should branch on.
 */
export type SyncWarning = NonNullable<SyncLogEntry['warnings']>[number];
export type AnyWarning = ImportWarning | SyncWarning;
export type PreviewFieldRow = NonNullable<ImportPreview['fields']>[number];
export type ApiKeyRow = Success<'listApiKeys'>[number];
export type ApiKeyCreated = Success<'createApiKey'>;
export type WebhookRow = Success<'listWebhooks'>[number];
export type WebhookCreated = Success<'createWebhook'>;
export type WebhookDelivery = Success<'testWebhook'>;
export type EventRow = Success<'listEvents'>['items'][number];
export type VendorRow = Success<'listVendors'>['items'][number];
export type Scope = NonNullable<ApiKeyRow['scopes']>[number];
export type EventType = NonNullable<WebhookRow['events']>[number];

/** Every scope the contract publishes, in the order the key form lists them. */
export const SCOPES: readonly Scope[] = [
  'vendors:read',
  'vendors:write',
  'applications:read',
  'applications:write',
  'projects:read',
  'projects:write',
  'intel:read',
  'integrations:read',
  'integrations:write',
  'admin:read',
  'admin:write',
];

/** The four domain events brief §4.2 names, first; the rest of the log after them. */
export const EVENT_TYPES: readonly EventType[] = [
  'vendor.prequalified',
  'application.submitted',
  'document.expiring',
  'project.matched',
  'vendor.registered',
  'vendor.invited',
  'vendor.rejected',
  'vendor.suspended',
  'application.decided',
  'document.uploaded',
  'model.published',
  'sync.completed',
];

export const adaptersQuery = queryOptions({
  queryKey: ['integrations', 'adapters'],
  queryFn: () => listAdapters(),
});

export const apiKeysQuery = queryOptions({
  queryKey: ['integrations', 'api-keys'],
  queryFn: () => listApiKeys(),
});

export const webhooksQuery = queryOptions({
  queryKey: ['integrations', 'webhooks'],
  queryFn: () => listWebhooks(),
});

export const syncLogQuery = (adapter?: string) =>
  queryOptions({
    queryKey: ['integrations', 'sync-log', adapter ?? 'all'],
    queryFn: () => listSyncLog(adapter ? { adapter } : undefined),
  });

export const eventLogQuery = queryOptions({
  queryKey: ['integrations', 'events'],
  queryFn: () => listEvents({ page_size: 50 }),
});

export const vendorPickerQuery = queryOptions({
  queryKey: ['integrations', 'vendor-picker'],
  queryFn: () => listVendors({ page_size: 200 }),
});

export const adapterConfigQuery = (adapter: string, vendorId: string | null) =>
  queryOptions({
    queryKey: ['integrations', 'adapter-config', adapter, vendorId],
    queryFn: () =>
      getAdapterConfig({ adapter, vendor_id: vendorId ?? '' } as PathParams<'getAdapterConfig'>),
    enabled: Boolean(vendorId),
  });

/** Invalidate everything an adapter run can have changed. */
function useInvalidate() {
  const queryClient = useQueryClient();
  return (keys: string[][]) =>
    Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export function useRunSync(): UseMutationResult<
  SyncLogEntry,
  Error,
  { adapter: string; vendorId?: string }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ adapter, vendorId }) =>
      runSync({ adapter } as PathParams<'runSync'>, vendorId ? { vendor_id: vendorId } : {}),
    onSuccess: () =>
      invalidate([
        ['integrations', 'adapters'],
        ['integrations', 'sync-log'],
      ]),
  });
}

export function useSaveAdapterConfig(): UseMutationResult<
  AdapterConfig,
  Error,
  { adapter: string; vendorId: string; body: Body<'putAdapterConfig'> }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ adapter, vendorId, body }) =>
      putAdapterConfig({ adapter, vendor_id: vendorId } as PathParams<'putAdapterConfig'>, body),
    onSuccess: () =>
      invalidate([
        ['integrations', 'adapter-config'],
        ['integrations', 'adapters'],
      ]),
  });
}

export function useCreateApiKey(): UseMutationResult<ApiKeyCreated, Error, Body<'createApiKey'>> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => createApiKey(body),
    onSuccess: () => invalidate([['integrations', 'api-keys']]),
  });
}

export function usePatchApiKey(): UseMutationResult<
  ApiKeyRow,
  Error,
  { id: string; body: Body<'patchApiKey'> }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }) =>
      patchApiKey({ api_key_id: id } as PathParams<'patchApiKey'>, body),
    onSuccess: () => invalidate([['integrations', 'api-keys']]),
  });
}

export function useRevokeApiKey(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id) => revokeApiKey({ api_key_id: id } as PathParams<'revokeApiKey'>),
    onSuccess: () => invalidate([['integrations', 'api-keys']]),
  });
}

export function useCreateWebhook(): UseMutationResult<
  WebhookCreated,
  Error,
  Body<'createWebhook'>
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => createWebhook(body),
    onSuccess: () => invalidate([['integrations', 'webhooks']]),
  });
}

export function useDeleteWebhook(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id) => deleteWebhook({ webhook_id: id } as PathParams<'deleteWebhook'>),
    onSuccess: () => invalidate([['integrations', 'webhooks']]),
  });
}

export function useTestWebhook(): UseMutationResult<WebhookDelivery, Error, string> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id) => testWebhook({ webhook_id: id } as PathParams<'testWebhook'>),
    onSuccess: () => invalidate([['integrations', 'webhooks']]),
  });
}

export function usePreviewImport(): UseMutationResult<
  ImportPreview,
  Error,
  { file: File; kind: 'application_form' | 'scoring_workbook'; vendorId?: string }
> {
  return useMutation({
    mutationFn: ({ file, kind, vendorId }) =>
      previewExcelImport(file, { kind, ...(vendorId ? { vendor_id: vendorId } : {}) }),
  });
}

export function useCreateImportRun(): UseMutationResult<
  SyncLogEntry,
  Error,
  Body<'createExcelImportRun'>
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => createExcelImportRun(body),
    onSuccess: () =>
      invalidate([
        ['integrations', 'sync-log'],
        ['integrations', 'adapters'],
      ]),
  });
}

/**
 * Data access for screens 31–34 — TanStack Query options and mutations over `api/admin.ts`.
 *
 * Transport only: every value a screen shows (a category's vendor count, whether a role
 * change is refused, a setting's current value) is read straight from the response. Nothing
 * here evaluates a threshold or a role rule (brief §2, gate 2).
 */
import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import type { UseMutationResult } from '@tanstack/react-query';
import {
  createCategory,
  createUser,
  deactivateUser,
  deleteCategory,
  exportAuditLog,
  getSettings,
  listAuditEvents,
  listCategories,
  listUsers,
  patchCategory,
  patchUser,
  putSettings,
  putUserRole,
} from '../../api/admin';
import { listVendors } from '../../api/vendors';
import type { Body, PathParams, Query, Success } from '../../api/http';

export type CategoryRow = Success<'listCategories'>[number];
export type UserRow = Success<'listUsers'>['items'][number];
export type UserCreated = Success<'createUser'>;
export type SettingsShape = Success<'getSettings'>;
export type AuditEventRow = Success<'listAuditEvents'>['items'][number];
export type VendorOption = Success<'listVendors'>['items'][number];

export const CATEGORIES_KEY = ['admin', 'categories'] as const;
export const USERS_KEY = ['admin', 'users'] as const;
export const SETTINGS_KEY = ['admin', 'settings'] as const;
export const AUDIT_KEY = ['admin', 'audit'] as const;

export const categoriesQuery = (query?: Query<'listCategories'>) =>
  queryOptions({
    queryKey: [...CATEGORIES_KEY, query ?? {}],
    queryFn: () => listCategories(query),
  });

export const usersQuery = (query: Query<'listUsers'>) =>
  queryOptions({
    queryKey: [...USERS_KEY, query],
    queryFn: () => listUsers(query),
  });

/** For the "which vendor does this account belong to" picker on a `vendor`-role account. */
export const vendorPickerQuery = queryOptions({
  queryKey: ['admin', 'vendor-picker'],
  queryFn: () => listVendors({ page_size: 200 }),
});

export const settingsQuery = queryOptions({
  queryKey: SETTINGS_KEY,
  queryFn: () => getSettings(),
});

export const auditQuery = (query: Query<'listAuditEvents'>) =>
  queryOptions({
    queryKey: [...AUDIT_KEY, query],
    queryFn: () => listAuditEvents(query),
  });

function useInvalidate() {
  const queryClient = useQueryClient();
  return (keys: readonly (readonly unknown[])[]) =>
    Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey: [...queryKey] })));
}

// ── categories ───────────────────────────────────────────────────────────────
export function useCreateCategory(): UseMutationResult<
  CategoryRow,
  Error,
  Body<'createCategory'>
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => createCategory(body),
    onSuccess: () => invalidate([CATEGORIES_KEY]),
  });
}

export function usePatchCategory(): UseMutationResult<
  CategoryRow,
  Error,
  { id: string; body: Body<'patchCategory'> }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }) =>
      patchCategory({ category_id: id } as PathParams<'patchCategory'>, body),
    onSuccess: () => invalidate([CATEGORIES_KEY]),
  });
}

export function useDeleteCategory(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id) => deleteCategory({ category_id: id } as PathParams<'deleteCategory'>),
    onSuccess: () => invalidate([CATEGORIES_KEY]),
  });
}

// ── users ────────────────────────────────────────────────────────────────────
export function useCreateUser(): UseMutationResult<UserCreated, Error, Body<'createUser'>> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => createUser(body),
    onSuccess: () => invalidate([USERS_KEY]),
  });
}

export function usePatchUser(): UseMutationResult<
  UserRow,
  Error,
  { id: string; body: Body<'patchUser'> }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }) => patchUser({ user_id: id } as PathParams<'patchUser'>, body),
    onSuccess: () => invalidate([USERS_KEY]),
  });
}

export function useDeactivateUser(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id) => deactivateUser({ user_id: id } as PathParams<'deactivateUser'>),
    onSuccess: () => invalidate([USERS_KEY]),
  });
}

export function useSetUserRole(): UseMutationResult<
  UserRow,
  Error,
  { id: string; role: Body<'putUserRole'>['role'] }
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, role }) =>
      putUserRole({ user_id: id } as PathParams<'putUserRole'>, { role }),
    onSuccess: () => invalidate([USERS_KEY]),
  });
}

// ── settings ─────────────────────────────────────────────────────────────────
export function usePutSettings(): UseMutationResult<
  SettingsShape,
  Error,
  Body<'putSettings'>
> {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body) => putSettings(body),
    onSuccess: () => invalidate([SETTINGS_KEY]),
  });
}

// ── audit export ─────────────────────────────────────────────────────────────
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function useExportAuditLog(): UseMutationResult<Blob, Error, Query<'exportAuditLog'>> {
  return useMutation({
    mutationFn: (query) => exportAuditLog(query),
  });
}

/**
 * Data access for the vendor portal screens — thin `useQuery`/`useMutation` wrappers over
 * `src/api/applications.ts` and `src/api/vendors.ts`. No business rule lives here: completion,
 * the pre-submission check and the computed cells all come back from the server response
 * (`AnswerState`, `ApplicationDetail`) exactly as it was returned — this module never derives
 * them itself (brief: "no business logic in the frontend").
 */
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Success } from '../../api/http';
import { getApplication, listApplications, patchAnswers, submitApplication } from '../../api/applications';
import { getVendor, listDocuments } from '../../api/vendors';
import { useSession } from '../../auth/SessionProvider';

export type ApplicationSummary = Success<'listApplications'>['items'][number];
export type ApplicationDetail = Success<'getApplication'>;
export type AnswerState = Success<'patchAnswers'>;
export type VendorDetail = Success<'getVendor'>;
export type DocumentRow = Success<'listDocuments'>[number];

/** The signed-in vendor's own id — every hook below is scoped to it, server-side, already;
 * this is only what the screens need to build a query key or a `vendor_id` path param. */
export function useVendorId(): string | undefined {
  const { session } = useSession();
  return session.status === 'authenticated' ? (session.principal.vendor_id ?? undefined) : undefined;
}

const applicationsKey = ['vendor', 'applications'] as const;
const applicationKey = (id: string) => ['vendor', 'application', id] as const;
const answerStateKey = (id: string) => ['vendor', 'application', id, 'answer-state'] as const;
const vendorKey = (id: string) => ['vendor', 'profile', id] as const;
const documentsKey = (id: string) => ['vendor', 'documents', id] as const;

/** Every application the caller may see — for a vendor identity that is exactly its own
 * (`listApplications` is vendor-scoped server-side, spec §13). */
export function useMyApplications() {
  return useQuery({
    queryKey: applicationsKey,
    queryFn: () => listApplications({ page_size: 50 }),
  });
}

/**
 * The application the portal screens work against. `listApplications` orders newest first
 * (`services/submission.list_page`), and a vendor normally has one application open at a
 * time, so the newest row is "the" current one; older, decided applications stay reachable
 * through the same list if a re-qualification cycle is ever added.
 */
export function useCurrentApplication() {
  const query = useMyApplications();
  const current = useMemo<ApplicationSummary | null>(() => query.data?.items[0] ?? null, [query.data]);
  return { ...query, current };
}

export function useApplicationDetail(applicationId: string | undefined) {
  return useQuery({
    queryKey: applicationKey(applicationId ?? 'none'),
    queryFn: () => getApplication({ application_id: applicationId ?? '' }),
    enabled: Boolean(applicationId),
  });
}

/**
 * The completion meter, the pre-submission checklist and the server-computed cells (B.4
 * average turnover, B.8 current ratio, the project/reference counts).
 *
 * These come from `getApplication`, which carries them all. They used to be fetched with an
 * *empty* `patchAnswers` — a read performed through a write, which worked only while the
 * application was still editable. The server correctly refuses that patch once an
 * application is submitted or decided, so the form showed "Completion 0 / 100" for a
 * complete, prequalified application and every computed cell came back blank (3A, finding 4).
 * A screen that cannot read its own state without changing it has the wrong endpoint.
 *
 * No separate request: `useApplicationDetail` is already loaded by every caller, so this
 * reads the same cache entry and stays in step with saves for free.
 */
export function useAnswerState(applicationId: string | undefined) {
  const detail = useApplicationDetail(applicationId);
  return {
    ...detail,
    data: detail.data
      ? {
          completion_pct: detail.data.completion_pct ?? 0,
          computed_fields: detail.data.computed_fields ?? {},
          checks: detail.data.checks,
        }
      : undefined,
  };
}

/** Autosave one patch of answers, then refresh the detail so computed cells and the
 * pre-submission checklist stay in step with what was just saved. */
export function useSaveAnswers(applicationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (answers: Record<string, unknown>) => {
      if (!applicationId) throw new Error('No application to save against.');
      return patchAnswers({ application_id: applicationId }, { answers });
    },
    onSuccess: (data) => {
      if (applicationId) {
        void queryClient.invalidateQueries({ queryKey: applicationKey(applicationId) });
        queryClient.setQueryData(answerStateKey(applicationId), data);
      }
      void queryClient.invalidateQueries({ queryKey: applicationsKey });
    },
  });
}

export function useSubmitApplication(applicationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (declaration: Parameters<typeof submitApplication>[1]) => {
      if (!applicationId) throw new Error('No application to submit.');
      return submitApplication({ application_id: applicationId }, declaration);
    },
    onSuccess: () => {
      if (applicationId) {
        void queryClient.invalidateQueries({ queryKey: applicationKey(applicationId) });
      }
      void queryClient.invalidateQueries({ queryKey: applicationsKey });
    },
  });
}

export function useVendorProfile(vendorId: string | undefined) {
  return useQuery({
    queryKey: vendorKey(vendorId ?? 'none'),
    queryFn: () => getVendor({ vendor_id: vendorId ?? '' }),
    enabled: Boolean(vendorId),
  });
}

export function useVendorDocuments(vendorId: string | undefined) {
  return useQuery({
    queryKey: documentsKey(vendorId ?? 'none'),
    queryFn: () => listDocuments({ vendor_id: vendorId ?? '' }),
    enabled: Boolean(vendorId),
  });
}

export { answerStateKey, applicationKey, applicationsKey, documentsKey, vendorKey };

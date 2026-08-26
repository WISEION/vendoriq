/**
 * Screen 18 — applications queue (`/applications`), spec §8.
 *
 * Queue by cycle and status. A row opens the evaluation screen (19). Filtering is server-side
 * (`listApplications`'s own query parameters) — the queue never re-sorts or re-filters a page
 * it already has.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { listApplications } from '../../api/applications';
import { listCycles } from '../../api/cycles';
import { useLocale } from '../../i18n/LocaleProvider';
import {
  Card,
  ClassPill,
  ErrorCard,
  LoadingCard,
  StatusPill,
  applicationPath,
  formatAmount,
  formatDate,
} from './shared';
import './manager.css';

const STATUSES = [
  'invited',
  'in_progress',
  'submitted',
  'under_review',
  'information_requested',
  'prequalified',
  'rejected',
  'withdrawn',
] as const;

const PAGE_SIZE = 25;

export function ApplicationsQueue() {
  const { t } = useLocale();
  const [cycleId, setCycleId] = useState('');
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);

  const cycles = useQuery({ queryKey: ['cycles', 'all'], queryFn: () => listCycles({ page_size: 100 }) });

  const query = {
    page,
    page_size: PAGE_SIZE,
    ...(cycleId ? { cycle_id: cycleId } : {}),
    ...(status ? { status: [status as (typeof STATUSES)[number]] } : {}),
    ...(q ? { q } : {}),
  } as const;

  const applications = useQuery({
    queryKey: ['applications', 'queue', query],
    queryFn: () => listApplications(query),
  });

  const totalPages = applications.data
    ? Math.max(1, Math.ceil(applications.data.total / PAGE_SIZE))
    : 1;

  return (
    <Card bodyClassName="mgr-card-bd-tight">
      <div className="mgr-card-hd" style={{ flexWrap: 'wrap', gap: 10 }}>
        <div className="mgr-filters">
          <select
            aria-label={t('th_cycle')}
            value={cycleId}
            onChange={(event) => {
              setCycleId(event.target.value);
              setPage(1);
            }}
          >
            <option value="">
              {t('th_cycle')}: {t('f_all')}
            </option>
            {(cycles.data?.items ?? []).map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.name}
              </option>
            ))}
          </select>
          <select
            aria-label={t('th_status')}
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">
              {t('th_status')}: {t('f_all')}
            </option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`st_${value}`) === `st_${value}` ? value : t(`st_${value}`)}
              </option>
            ))}
          </select>
          <input
            type="text"
            aria-label={t('f_search')}
            placeholder={t('f_search')}
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            style={{ width: 220 }}
          />
        </div>
        <span className="muted small">{applications.data?.total ?? 0}</span>
      </div>

      {applications.isLoading ? (
        <LoadingCard />
      ) : applications.isError ? (
        <ErrorCard message={String(applications.error)} />
      ) : applications.data && applications.data.items.length > 0 ? (
        <div className="mgr-table-wrap">
          <table className="mgr-table">
            <thead>
              <tr>
                <th>{t('th_vendor')}</th>
                <th>{t('th_cycle')}</th>
                <th>{t('th_submitted')}</th>
                <th>{t('th_status')}</th>
                <th className="mgr-r">{t('th_score')}</th>
                <th>{t('th_decision')}</th>
                <th>{t('th_evaluator')}</th>
              </tr>
            </thead>
            <tbody>
              {applications.data.items.map((application) => (
                <tr key={application.id} className="mgr-row-link">
                  <td>
                    <Link to={applicationPath(application.id)}>
                      <b>{application.vendor_name ?? '—'}</b>
                    </Link>
                  </td>
                  <td className="mono small">{application.cycle_name ?? '—'}</td>
                  <td className="mono small">{formatDate(application.submitted_at)}</td>
                  <td>
                    <StatusPill status={application.status} />
                  </td>
                  <td className="mgr-r mono">
                    {application.total != null ? formatAmount(application.total) : '—'}
                  </td>
                  <td>
                    {application.cls ? (
                      <ClassPill cls={application.cls} />
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="small muted">{application.evaluator_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mgr-empty">{t('none')}</div>
      )}

      {applications.data && totalPages > 1 ? (
        <div className="mgr-pager">
          <button
            type="button"
            className="mgr-btn mgr-btn-sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ←
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="mgr-btn mgr-btn-sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            →
          </button>
        </div>
      ) : null}
    </Card>
  );
}

/**
 * Screen 20 — commission summary (`/applications/$applicationId/summary`), spec §8.
 *
 * The export is cycle-scoped in the contract (`GET /cycles/{cycle_id}/export-summary.*`) —
 * this screen is reached from one application, so it resolves that application's cycle first,
 * then offers the same two files a commission chair signs, plus a read-only preview of the
 * rows they contain. Nothing on this screen totals, classifies or decides anything; every
 * number in the preview is the `total`/`cls`/`decision` the queue already carries.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
  exportCommissionSummaryPdf,
  exportCommissionSummaryXlsx,
  getApplication,
  listApplications,
} from '../../api/applications';
import { useLocale } from '../../i18n/LocaleProvider';
import type { Locale } from '../../i18n/LocaleProvider';
import { Card, ClassPill, ErrorCard, LoadingCard, applicationPath, formatAmount } from './shared';
import './manager.css';

const DECISION_KEY: Record<string, string> = {
  approve: 'ev_approved',
  reject: 'ev_rejected',
  request_info: 'ev_info_sent',
};

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function CommissionSummary({ applicationId }: { applicationId: string }) {
  const { t, locale } = useLocale();
  const [exportingFormat, setExportingFormat] = useState<'xlsx' | 'pdf' | null>(null);

  const application = useQuery({
    queryKey: ['application', applicationId],
    queryFn: () => getApplication({ application_id: applicationId }),
  });

  const cycleId = application.data?.cycle_id ?? null;

  const cycleApplications = useQuery({
    queryKey: ['applications', 'cycle-summary', cycleId],
    queryFn: () => listApplications({ cycle_id: cycleId!, page_size: 200 }),
    enabled: !!cycleId,
  });

  async function handleExport(format: 'xlsx' | 'pdf') {
    if (!cycleId) return;
    setExportingFormat(format);
    try {
      const blob =
        format === 'xlsx'
          ? await exportCommissionSummaryXlsx({ cycle_id: cycleId }, { locale: locale as Locale })
          : await exportCommissionSummaryPdf({ cycle_id: cycleId }, { locale: locale as Locale });
      const name = `${application.data?.cycle_name ?? 'commission-summary'}.${format}`;
      downloadBlob(blob, name);
    } finally {
      setExportingFormat(null);
    }
  }

  if (application.isLoading) return <LoadingCard />;
  if (application.isError || !application.data) return <ErrorCard message={String(application.error)} />;

  return (
    <>
      <Link to={applicationPath(applicationId)} className="mgr-btn mgr-btn-sm">
        {t('back')}
      </Link>
      <div className="page-head" style={{ marginTop: 12 }}>
        <div>
          <div className="mgr-eyebrow">{application.data.cycle_name ?? '—'}</div>
          <h2 style={{ fontSize: 22 }}>{t('cs_title')}</h2>
          <p>{t('cs_sub')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="mgr-btn mgr-btn-primary"
            disabled={exportingFormat !== null}
            onClick={() => handleExport('xlsx')}
          >
            {exportingFormat === 'xlsx' ? `${t('cs_export_xlsx')}…` : t('cs_export_xlsx')}
          </button>
          <button
            type="button"
            className="mgr-btn"
            disabled={exportingFormat !== null}
            onClick={() => handleExport('pdf')}
          >
            {exportingFormat === 'pdf' ? `${t('cs_export_pdf')}…` : t('cs_export_pdf')}
          </button>
        </div>
      </div>

      <Card bodyClassName="mgr-card-bd-tight">
        {cycleApplications.isLoading ? (
          <LoadingCard />
        ) : cycleApplications.data && cycleApplications.data.items.length > 0 ? (
          <div className="mgr-table-wrap">
            <table className="mgr-table">
              <thead>
                <tr>
                  <th>{t('th_vendor')}</th>
                  <th className="mgr-r">{t('th_score')}</th>
                  <th>{t('th_class')}</th>
                  <th>{t('th_decision')}</th>
                </tr>
              </thead>
              <tbody>
                {cycleApplications.data.items.map((row) => (
                  <tr key={row.id} style={row.id === applicationId ? { background: 'var(--accent-soft)' } : undefined}>
                    <td>{row.vendor_name ?? '—'}</td>
                    <td className="mgr-r mono">{row.total != null ? formatAmount(row.total) : '—'}</td>
                    <td>{row.cls ? <ClassPill cls={row.cls} /> : <span className="muted">—</span>}</td>
                    <td>{row.decision ? t(DECISION_KEY[row.decision] ?? row.decision) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mgr-empty">{t('none')}</div>
        )}
      </Card>
    </>
  );
}

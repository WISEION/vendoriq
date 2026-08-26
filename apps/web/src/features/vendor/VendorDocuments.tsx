import { useId, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  completeDocumentUpload,
  getDocumentDownload,
  initDocumentUpload,
  patchDocument,
} from '../../api/vendors';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import './vendor.css';
import { documentsKey, useVendorDocuments, useVendorId } from './hooks';
import type { DocumentRow } from './hooks';

const ACCEPT_PDF = 'application/pdf';

function tone(doc: DocumentRow): 'good' | 'warn' | 'crit' | 'neutral' {
  if (doc.status !== 'uploaded') return doc.status === 'missing' ? 'neutral' : 'warn';
  if (doc.days_to_expiry == null) return 'good';
  if (doc.days_to_expiry < 0) return 'crit';
  if (doc.days_to_expiry <= 60) return 'warn';
  return 'good';
}

function statusKey(doc: DocumentRow): string {
  if (doc.status === 'uploaded') {
    if (doc.days_to_expiry != null && doc.days_to_expiry < 0) return 'doc_expired';
    if (doc.days_to_expiry != null && doc.days_to_expiry <= 60) return 'doc_expiring';
    return 'vd_ready';
  }
  return doc.status === 'in_preparation' ? 'vd_prep' : doc.status === 'not_applicable' ? 'vd_na' : 'vd_missing';
}

/** Screen 13 (`docs/SCREENS.md`): the 38-item checklist, PDF-only upload, expiry state. */
export function VendorDocuments() {
  const { t } = useLocale();
  const vendorId = useVendorId();
  const documents = useVendorDocuments(vendorId);

  if (documents.isLoading) return <div className="card vp-empty">{t('vp_loading')}</div>;
  if (documents.isError || !documents.data) {
    return (
      <div className="card form-error" role="alert">
        {t(localisedErrorKey(documents.error))}
      </div>
    );
  }

  const rows = documents.data;
  const mandatory = rows.filter((row) => row.mandatory);
  const ready = mandatory.filter((row) => row.status === 'uploaded').length;

  return (
    <div className="vp-stack">
      <div className="card">
        <div className="vp-card-head">
          <div>
            <div className="small muted">
              {t('vd_progress')}: <b className="mono">{ready}/{mandatory.length}</b>
            </div>
            <div className="vp-bar" style={{ width: 200, marginTop: 4 }}>
              <i style={{ width: mandatory.length ? `${(ready / mandatory.length) * 100}%` : '0%' }} />
            </div>
          </div>
        </div>
        <div className="vp-doc-row" style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600 }}>
          <span className="mono">{t('va_col_code')}</span>
          <span>{t('vd_title')}</span>
          <span>{t('vd_status')}</span>
          <span>{t('vd_exp')}</span>
          <span>{t('field_issue_date')} / {t('field_expiry_date')}</span>
          <span />
        </div>
        {rows.map((row) => (
          <DocumentRowItem key={row.code} vendorId={vendorId!} doc={row} />
        ))}
      </div>
    </div>
  );
}

function DocumentRowItem({ vendorId, doc }: { vendorId: string; doc: DocumentRow }) {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();
  const inputId = useId();
  const issueId = useId();
  const expiryId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const [issueDate, setIssueDate] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: documentsKey(vendorId) });

  const statusPatch = useMutation({
    mutationFn: (status: 'in_preparation' | 'not_applicable') =>
      patchDocument({ vendor_id: vendorId, document_id: doc.id ?? '' }, { status }),
    onSuccess: refresh,
  });

  const download = useMutation({
    mutationFn: () => getDocumentDownload({ vendor_id: vendorId, document_id: doc.id ?? '' }),
    onSuccess: (ticket) => window.open(ticket.url, '_blank', 'noopener'),
  });

  const handleFile = async (file: File) => {
    setError(null);
    setBusy(true);
    try {
      const ticket = await initDocumentUpload(
        { vendor_id: vendorId },
        { code: doc.code, filename: file.name, content_type: 'application/pdf', size: file.size },
      );
      const response = await fetch(ticket.url, {
        method: ticket.method,
        headers: ticket.headers,
        body: file,
      });
      if (!response.ok) throw new Error('upload_failed');
      await completeDocumentUpload(
        { vendor_id: vendorId },
        {
          upload_id: ticket.upload_id,
          code: doc.code,
          issue_date: issueDate || null,
          expiry_date: expiryDate || null,
        },
      );
      refresh();
    } catch {
      setError(t('vd_upload_failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="vp-doc-row">
      <span className="mono muted">{doc.code}</span>
      <span className="vp-doc-name">
        {locale === 'az' ? doc.name_az : doc.name_en}
        <span className="vp-pill" data-tone={doc.mandatory ? 'crit' : 'neutral'} style={{ marginLeft: 8 }}>
          {doc.mandatory ? t('vd_req') : t('vd_opt')}
        </span>
      </span>
      <span className="vp-pill" data-tone={tone(doc)}>
        {t(statusKey(doc))}
      </span>
      <span className="vp-doc-expiry">{doc.expiry_date ?? (doc.status === 'uploaded' ? t('doc_perm') : '—')}</span>
      <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <label htmlFor={issueId} className="vp-sr-only">
          {t('field_issue_date')}
        </label>
        <input
          id={issueId}
          type="date"
          value={issueDate}
          onChange={(event) => setIssueDate(event.target.value)}
          style={{ width: 128, height: 28, fontSize: 12 }}
          aria-label={t('field_issue_date')}
        />
        <label htmlFor={expiryId} className="vp-sr-only">
          {t('field_expiry_date')}
        </label>
        <input
          id={expiryId}
          type="date"
          value={expiryDate}
          onChange={(event) => setExpiryDate(event.target.value)}
          style={{ width: 128, height: 28, fontSize: 12 }}
          aria-label={t('field_expiry_date')}
        />
      </span>
      <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <label htmlFor={inputId} className="vp-sr-only">
          {t('vd_upload')} — {locale === 'az' ? doc.name_az : doc.name_en}
        </label>
        <input
          id={inputId}
          ref={fileRef}
          type="file"
          accept={ACCEPT_PDF}
          className="vp-sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
            event.target.value = '';
          }}
        />
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? `${t('vd_upload')}…` : t('vd_upload')}
        </button>
        {doc.id ? (
          <>
            <button type="button" className="btn-link" onClick={() => download.mutate()}>
              {t('vd_download')}
            </button>
            {doc.status !== 'uploaded' ? null : (
              <>
                <button
                  type="button"
                  className="btn-link"
                  disabled={statusPatch.isPending}
                  onClick={() => statusPatch.mutate('in_preparation')}
                >
                  {t('vd_prep')}
                </button>
                <button
                  type="button"
                  className="btn-link"
                  disabled={statusPatch.isPending}
                  onClick={() => statusPatch.mutate('not_applicable')}
                >
                  {t('vd_na')}
                </button>
              </>
            )}
          </>
        ) : null}
      </span>
      {error ? (
        <span className="form-error" role="alert" style={{ gridColumn: '1 / -1', fontSize: 12 }}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

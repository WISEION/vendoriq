/**
 * Screen 29 — `/integrations/excel-import`. Upload → mapping preview with anomaly warnings →
 * write.
 *
 * The two steps are two API calls and the screen makes that visible, because the split is
 * the safety property: `previewExcelImport` parses and writes nothing, and only
 * `createExcelImportRun` with the returned `preview_id` puts anything in the register. The
 * anomalies below come from the parser (brief §1.11) — the WESA form reports eight, among
 * them a tax-clearance certificate 66 months old and a sheet header that says USD over
 * figures that are AZN.
 */
import { useState } from 'react';
import type { ChangeEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { EmptyRow, ErrorText, Pill, STATUS_TONE, WarningRow } from './shared';
import { useCreateImportRun, usePreviewImport, vendorPickerQuery } from './queries';
import type { ImportPreview, PreviewFieldRow, SyncLogEntry } from './queries';
import './integrations.css';

type Kind = 'application_form' | 'scoring_workbook';

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? '✓' : '✗';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function ExcelImport() {
  const { t } = useLocale();
  const vendors = useQuery(vendorPickerQuery);
  const preview = usePreviewImport();
  const run = useCreateImportRun();

  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<Kind>('application_form');
  const [vendorId, setVendorId] = useState('');
  const [parsed, setParsed] = useState<ImportPreview | null>(null);
  const [written, setWritten] = useState<SyncLogEntry | null>(null);
  const [rejected, setRejected] = useState<Set<string>>(new Set());

  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setParsed(null);
    setWritten(null);
    setRejected(new Set());
    preview.reset();
    run.reset();
  };

  const startPreview = () => {
    if (!file) return;
    preview.reset();
    preview.mutate(
      { file, kind, ...(vendorId ? { vendorId } : {}) },
      { onSuccess: (result) => setParsed(result) },
    );
  };

  const toggleField = (code: string) =>
    setRejected((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  const confirm = () => {
    if (!parsed) return;
    const accepted = (parsed.fields ?? [])
      .map((item) => item.field_code as string)
      .filter((code) => !rejected.has(code));
    run.reset();
    run.mutate(
      {
        preview_id: parsed.preview_id,
        ...(vendorId ? { vendor_id: vendorId } : {}),
        ...(rejected.size ? { accept_field_codes: accepted } : {}),
      },
      {
        onSuccess: (result) => {
          setWritten(result);
          setParsed(null);
        },
      },
    );
  };

  const step = written ? 3 : parsed ? 2 : 1;

  return (
    <div className="iq-stack">
      <div className="iq-steps">
        <span data-active={step === 1}>1 · {t('in_step_upload')}</span>
        <span>→</span>
        <span data-active={step === 2}>2 · {t('in_step_preview')}</span>
        <span>→</span>
        <span data-active={step === 3}>3 · {t('in_step_write')}</span>
      </div>

      <section className="card">
        <h3 className="iq-section-title">{t('in_step_upload')}</h3>
        <p className="iq-note">{t('in_upload_note')}</p>
        <div className="iq-toolbar">
          <label className="iq-inline-field">
            <span>{t('in_file')}</span>
            <input type="file" accept=".xlsx" onChange={chooseFile} />
          </label>
          <label className="iq-inline-field">
            <span>{t('in_kind')}</span>
            <select value={kind} onChange={(event) => setKind(event.target.value as Kind)}>
              <option value="application_form">{t('in_kind_form')}</option>
              <option value="scoring_workbook">{t('in_kind_workbook')}</option>
            </select>
          </label>
          <label className="iq-inline-field">
            <span>{t('in_vendor')}</span>
            <select value={vendorId} onChange={(event) => setVendorId(event.target.value)}>
              <option value="">{t('in_vendor_auto')}</option>
              {(vendors.data?.items ?? []).map((vendor) => (
                <option key={vendor.id} value={vendor.id}>
                  {vendor.legal_name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={!file || preview.isPending}
            onClick={startPreview}
          >
            {t('in_preview')}
          </button>
        </div>
        <ErrorText error={preview.error} />
      </section>

      {parsed ? (
        <>
          <section className="card">
            <h3 className="iq-section-title">{t('in_anomalies')}</h3>
            <p className="iq-note">{t('in_anomalies_note')}</p>
            {(parsed.warnings ?? []).length === 0 ? (
              <p className="iq-empty">{t('in_no_anomalies')}</p>
            ) : (
              (parsed.warnings ?? []).map((warning, index) => (
                <WarningRow key={`${warning.code}-${index}`} warning={warning} />
              ))
            )}
          </section>

          <section className="card">
            <h3 className="iq-section-title">{t('in_mapping')}</h3>
            <p className="iq-note">
              {t('in_mapping_note')}
              {parsed.matched_vendor ? ` · ${parsed.matched_vendor.legal_name}` : ''}
            </p>
            <div className="iq-table-wrap">
              <table className="iq-table">
                <thead>
                  <tr>
                    <th>{t('in_col_import')}</th>
                    <th>{t('in_col_field')}</th>
                    <th>{t('in_col_new_value')}</th>
                    <th>{t('in_col_current_value')}</th>
                    <th>{t('in_col_where')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(parsed.fields ?? []).map((row: PreviewFieldRow) => (
                    <tr key={row.field_code}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={row.field_code}
                          checked={!rejected.has(row.field_code as string)}
                          onChange={() => toggleField(row.field_code as string)}
                        />
                      </td>
                      <td className="mono">{row.field_code}</td>
                      <td className={row.will_change ? 'iq-changed' : undefined}>
                        {renderValue(row.value)}
                        {row.unit ? <span className="muted"> {row.unit}</span> : null}
                      </td>
                      <td className="muted">{renderValue(row.current_value)}</td>
                      <td className="muted mono" style={{ fontSize: 11 }}>
                        {[row.sheet, row.cell].filter(Boolean).join(' · ') || '—'}
                      </td>
                    </tr>
                  ))}
                  {(parsed.fields ?? []).length === 0 ? (
                    <EmptyRow columns={5} text={t('in_no_fields')} />
                  ) : null}
                </tbody>
              </table>
            </div>
            <div className="iq-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn-primary"
                disabled={run.isPending || (parsed.fields ?? []).length === 0}
                onClick={confirm}
              >
                {t('in_write')}
              </button>
            </div>
            <ErrorText error={run.error} />
          </section>
        </>
      ) : null}

      {written ? (
        <section className="card">
          <h3 className="iq-section-title">{t('in_written')}</h3>
          <p className="iq-note">
            <Pill tone={STATUS_TONE[written.result ?? 'failed'] ?? 'mute'}>
              {t(`in_result_${written.result}`)}
            </Pill>{' '}
            {t('in_fields_written')}: {written.fields_written}
          </p>
        </section>
      ) : null}
    </div>
  );
}

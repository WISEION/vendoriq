import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import { AnswerControl } from './AnswerControl';
import { ApplicationTabs } from './ApplicationTabs';
import { sectionByKey } from './fieldCatalog';
import type { SectionKey } from './fieldCatalog';
import { ProjectTable } from './ProjectTable';
import './vendor.css';
import { useAnswerState, useApplicationDetail, useCurrentApplication, useSaveAnswers } from './hooks';

/** Table fields that mirror the Excel form's own minimum row count (spec §7). */
const MIN_ROWS: Record<string, number> = { 'C.t1': 3, 'G.t1': 3 };

const EDITABLE_STATUSES = new Set(['invited', 'in_progress', 'information_requested']);

/**
 * Screens 6–12 (`docs/SCREENS.md`): sections A–G of the application form, one tab strip, one
 * shared renderer. Each row shows code, question, format, the answer control and the
 * required document code (spec §7); autosave writes through `patchAnswers` per field.
 */
export function VendorApplicationForm({ section }: { section: SectionKey }) {
  const { t, locale } = useLocale();
  const applications = useCurrentApplication();
  const applicationId = applications.current?.id;
  const detail = useApplicationDetail(applicationId);
  const answerState = useAnswerState(applicationId);
  const save = useSaveAnswers(applicationId);

  if (applications.isLoading || (applicationId && detail.isLoading)) {
    return <div className="card vp-empty">{t('vp_loading')}</div>;
  }
  if (!applications.current) {
    return <div className="card vp-empty">{t('vh_none')}</div>;
  }
  if (detail.isError || !detail.data) {
    return (
      <div className="card form-error" role="alert">
        {t(localisedErrorKey(detail.error))}
      </div>
    );
  }

  const sectionDef = sectionByKey(section);
  if (!sectionDef) return null;

  const answers = detail.data.answers ?? {};
  const computedFields = answerState.data?.computed_fields ?? {};
  const completion = answerState.data?.completion_pct ?? 0;
  const editable = EDITABLE_STATUSES.has(detail.data.status);

  return (
    <div className="vp-stack">
      <div className="card">
        <ApplicationTabs active={section} />
        <div className="vp-card-head">
          <div>
            <div className="small muted">
              {t('va_progress')}: <b className="mono">{completion}{t('of100')}</b>
            </div>
            <div className="vp-bar" style={{ width: 200, marginTop: 4 }}>
              <i style={{ width: `${completion}%` }} />
            </div>
          </div>
        </div>

        {!editable ? <p className="vp-table-hint" data-ok="false">{t('va_locked')}</p> : null}

        <div className="vp-row-head" aria-hidden="true">
          <span>№</span>
          <span>{t('va_col_q')}</span>
          <span>{t('va_col_unit')}</span>
          <span>{t('va_col_a')}</span>
          <span>{t('va_col_doc')}</span>
        </div>

        {sectionDef.rows.map((row, index) => {
          if (row.kind === 'header') {
            return (
              <div key={`h-${index}`} className="vp-row-header">
                {locale === 'az' ? row.az : row.en}
              </div>
            );
          }
          if (row.type === 'table') {
            return (
              <ProjectTable
                key={row.code}
                row={row}
                value={answers[row.code]}
                minRows={MIN_ROWS[row.code] ?? 0}
                disabled={!editable}
                onSave={(code, rows) => save.mutate({ [code]: rows })}
              />
            );
          }
          return (
            <AnswerControl
              key={row.code}
              row={row}
              value={answers[row.code]}
              computedValue={computedFields[row.code]}
              disabled={!editable}
              onSave={(code, value) => save.mutate({ [code]: value })}
            />
          );
        })}

        {save.isError ? (
          <p className="form-error" role="alert">
            {t(localisedErrorKey(save.error))}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function VendorFormA() {
  return <VendorApplicationForm section="A" />;
}
export function VendorFormB() {
  return <VendorApplicationForm section="B" />;
}
export function VendorFormC() {
  return <VendorApplicationForm section="C" />;
}
export function VendorFormD() {
  return <VendorApplicationForm section="D" />;
}
export function VendorFormE() {
  return <VendorApplicationForm section="E" />;
}
export function VendorFormF() {
  return <VendorApplicationForm section="F" />;
}
export function VendorFormG() {
  return <VendorApplicationForm section="G" />;
}

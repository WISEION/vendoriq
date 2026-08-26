import { useId, useState } from 'react';
import { ApiError } from '../../api/client';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import './vendor.css';
import { useApplicationDetail, useCurrentApplication, useSubmitApplication } from './hooks';

/** Screen 14 (`docs/SCREENS.md`): declaration, the pre-submission checklist, submit. */
export function VendorSubmit() {
  const { t } = useLocale();
  const applications = useCurrentApplication();
  const applicationId = applications.current?.id;
  const detail = useApplicationDetail(applicationId);
  const submit = useSubmitApplication(applicationId);

  const nameId = useId();
  const positionId = useId();
  const agreeId = useId();
  const [signatoryName, setSignatoryName] = useState('');
  const [signatoryPosition, setSignatoryPosition] = useState('');
  const [agreed, setAgreed] = useState(false);

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

  const application = detail.data;
  const alreadySubmitted = application.status !== 'invited' && application.status !== 'in_progress' && application.status !== 'information_requested';
  const checks = application.checks;
  const canSubmit = Boolean(
    checks?.mandatory_fields && checks?.mandatory_documents && checks?.knock_out_answers && agreed && signatoryName.trim() && signatoryPosition.trim(),
  );

  const serverChecks =
    submit.error instanceof ApiError ? (submit.error.details.checks as Record<string, boolean> | undefined) : undefined;
  const serverMissingFields =
    submit.error instanceof ApiError ? (submit.error.details.missing_field_codes as string[] | undefined) : undefined;
  const serverMissingDocs =
    submit.error instanceof ApiError ? (submit.error.details.missing_document_codes as string[] | undefined) : undefined;

  return (
    <div className="vp-stack">
      {alreadySubmitted ? (
        <div className="card">
          <p className="form-success">{t('vs_sent')}</p>
        </div>
      ) : (
        <div className="card">
          <div className="vp-card-head">
            <h3>{t('vs_title')}</h3>
          </div>
          <p className="muted" style={{ marginTop: -8 }}>
            {t('vs_sub')}
          </p>

          <div className="vp-declaration-text">{t('vs_decl')}</div>

          <div className="vp-grid-2" style={{ marginTop: 16 }}>
            <div className="field">
              <label htmlFor={nameId}>{t('vs_name')}</label>
              <input id={nameId} value={signatoryName} onChange={(event) => setSignatoryName(event.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor={positionId}>{t('vs_pos')}</label>
              <input
                id={positionId}
                value={signatoryPosition}
                onChange={(event) => setSignatoryPosition(event.target.value)}
                required
              />
            </div>
          </div>

          <label className="vp-agree" htmlFor={agreeId} style={{ marginTop: 16 }}>
            <input id={agreeId} type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
            <span>{t('vs_agree')}</span>
          </label>

          <div className="vp-card-head" style={{ marginTop: 20 }}>
            <h3>{t('vs_check')}</h3>
          </div>
          <ul className="vp-check-list">
            <CheckItem ok={checks?.mandatory_fields ?? false} label={t('vs_c1')} missing={checks?.missing_field_codes} />
            <CheckItem ok={checks?.mandatory_documents ?? false} label={t('vs_c2')} missing={checks?.missing_document_codes} />
            <CheckItem ok={checks?.knock_out_answers ?? false} label={t('vs_c3')} />
          </ul>

          {submit.isError ? (
            <div className="form-error" role="alert" style={{ marginTop: 12 }}>
              <p>{t(localisedErrorKey(submit.error))}</p>
              {serverChecks ? (
                <ul className="vp-missing-codes">
                  {!serverChecks.mandatory_fields && serverMissingFields?.length
                    ? serverMissingFields.map((code) => <li key={`f-${code}`}>{code}</li>)
                    : null}
                  {!serverChecks.mandatory_documents && serverMissingDocs?.length
                    ? serverMissingDocs.map((code) => <li key={`d-${code}`}>{code}</li>)
                    : null}
                </ul>
              ) : null}
            </div>
          ) : null}

          <button
            type="button"
            className="btn-primary"
            style={{ marginTop: 16 }}
            disabled={!canSubmit || submit.isPending}
            onClick={() =>
              submit.mutate({
                signatory_name: signatoryName,
                signatory_position: signatoryPosition,
                agreed: true,
              })
            }
          >
            {submit.isPending ? `${t('vs_send')}…` : t('vs_send')}
          </button>
        </div>
      )}
    </div>
  );
}

function CheckItem({ ok, label, missing }: { ok: boolean; label: string; missing?: string[] }) {
  return (
    <li className="vp-check-item" data-ok={ok ? 'true' : 'false'}>
      <span className="vp-check-icon" aria-hidden="true">
        {ok ? '✓' : '!'}
      </span>
      <span>
        {label}
        {!ok && missing && missing.length > 0 ? (
          <span className="vp-missing-codes" style={{ display: 'block', marginLeft: 0 }}>
            {missing.join(', ')}
          </span>
        ) : null}
      </span>
    </li>
  );
}

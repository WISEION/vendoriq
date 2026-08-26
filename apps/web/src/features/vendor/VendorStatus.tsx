import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import './vendor.css';
import { useApplicationDetail, useCurrentApplication, useVendorDocuments, useVendorId } from './hooks';

/** Application status → the stepper position it renders as (spec §7, §9). */
const STEP_ORDER = ['registered', 'invited', 'filling', 'submitted', 'review', 'decision'] as const;
type Step = (typeof STEP_ORDER)[number];

const STEP_LABEL_KEY: Record<Step, string> = {
  registered: 'step_reg',
  invited: 'step_inv',
  filling: 'step_app',
  submitted: 'step_sub',
  review: 'step_rev',
  decision: 'step_dec',
};

function stepFor(status: string | undefined): Step {
  switch (status) {
    case 'invited':
      return 'invited';
    case 'in_progress':
    case 'information_requested':
      return 'filling';
    case 'submitted':
      return 'submitted';
    case 'under_review':
      return 'review';
    case 'prequalified':
    case 'rejected':
    case 'withdrawn':
      return 'decision';
    default:
      return 'registered';
  }
}

/** The three knock-out fields (spec Appendix A) — used only to name which one a released KO
 * decision failed. The pass/fail verdict itself (`computed.ko`) always comes from the server. */
const KO_FIELDS: { code: string; az: string; en: string }[] = [
  { code: 'A.1', az: 'Tikinti lisenziyası', en: 'Construction licence' },
  { code: 'A.4', az: 'Vergi borcsuzluğu arayışı', en: 'Tax clearance' },
  { code: 'F.1', az: 'SƏTƏMM siyasəti', en: 'HSE policy' },
];

/** Mirrors `vendoriq_api.catalog.DEFAULT_EXPIRING_WINDOW_DAYS` (spec §12) — a display window
 * for the "next steps" list, not a rule with consequences; expiry itself is server-computed. */
const EXPIRY_REMINDER_WINDOW_DAYS = 60;

export function VendorStatus() {
  const { t, locale } = useLocale();
  const vendorId = useVendorId();
  const applications = useCurrentApplication();
  const detail = useApplicationDetail(applications.current?.id);
  const documents = useVendorDocuments(vendorId);

  if (applications.isLoading) {
    return <div className="card vp-empty">{t('vp_loading')}</div>;
  }
  if (applications.isError) {
    return (
      <div className="card form-error" role="alert">
        {t(localisedErrorKey(applications.error))}
      </div>
    );
  }

  const application = applications.current;
  const step = stepFor(application?.status);
  const released = detail.data?.score_released ?? false;
  const computed = detail.data?.computed;
  const snapshot = detail.data?.raw_snapshot;
  const failedKo = KO_FIELDS.filter((field) => (snapshot?.[field.code] ?? 1) <= 0);
  const expiring = (documents.data ?? [])
    .filter(
      (doc) =>
        doc.status === 'uploaded' &&
        doc.days_to_expiry != null &&
        doc.days_to_expiry <= EXPIRY_REMINDER_WINDOW_DAYS,
    )
    .sort((a, b) => (a.days_to_expiry ?? 0) - (b.days_to_expiry ?? 0));

  return (
    <div className="vp-stack">
      <div className="card">
        <ol className="vp-stepper">
          {STEP_ORDER.map((candidate, index) => {
            const currentIndex = STEP_ORDER.indexOf(step);
            const state =
              application?.status === 'rejected' && candidate === 'decision'
                ? 'rejected'
                : index < currentIndex
                  ? 'done'
                  : index === currentIndex
                    ? 'current'
                    : 'upcoming';
            return (
              <li key={candidate} className="vp-step" data-state={state}>
                <span className="vp-step-dot" aria-hidden="true">
                  {state === 'done' ? '✓' : index + 1}
                </span>
                <span>{t(STEP_LABEL_KEY[candidate])}</span>
                {index < STEP_ORDER.length - 1 ? <span className="vp-step-sep" aria-hidden="true" /> : null}
              </li>
            );
          })}
        </ol>

        {!application ? (
          <p className="muted">{t('vh_none')}</p>
        ) : released ? (
          <div className="vp-grid-2">
            <div className="vp-field-static">
              <dt>{t('vh_result')}</dt>
              <dd style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="vp-class-badge">{computed?.cls ?? '—'}</span>
                <span className="mono">
                  {computed?.total ?? '—'} {t('of100')}
                </span>
              </dd>
            </div>
            <div className="vp-field-static">
              <dt>{t('pass_mark')}</dt>
              <dd>{computed?.pass_mark ?? 70}</dd>
            </div>
            {application.status === 'rejected' ? (
              <div className="vp-field-static" style={{ gridColumn: '1 / -1' }}>
                <dt>{t('ko_fail')}</dt>
                <dd>
                  {failedKo.length > 0 ? (
                    <ul className="vp-next-list">
                      {failedKo.map((field) => (
                        <li key={field.code} className="vp-next-item">
                          <span>
                            <span className="mono muted">{field.code}</span>{' '}
                            {locale === 'az' ? field.az : field.en}
                          </span>
                          <span className="vp-pill" data-tone="crit">
                            {t('ko_failed')}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted">{t('none')}</span>
                  )}
                </dd>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="muted">{t('vh_pending')}</p>
        )}
      </div>

      <div className="card">
        <div className="vp-card-head">
          <h3>{t('vh_next')}</h3>
        </div>
        {expiring.length === 0 ? (
          <p className="vp-empty">{t('vh_no_next')}</p>
        ) : (
          <ul className="vp-next-list">
            {expiring.map((doc) => (
              <li key={doc.code} className="vp-next-item">
                <span>
                  <span className="mono muted">{doc.code}</span>{' '}
                  {locale === 'az' ? doc.name_az : doc.name_en}
                </span>
                <span className="vp-pill" data-tone={doc.days_to_expiry! < 0 ? 'crit' : 'warn'}>
                  {doc.days_to_expiry! < 0 ? t('doc_expired') : t('doc_expiring')} ·{' '}
                  {doc.expiry_date}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

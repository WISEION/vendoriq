/**
 * Screen 17 — vendor detail (`/vendors/$vendorId`), spec §8.
 *
 * Profile, scorecard (per-criterion raw value and points), project history, documents with
 * expiry state, and the evaluation history across cycles. The history table and the choice of
 * which application to score comes straight from `getVendor`'s own `evaluations` field
 * (`routers/vendors.py`) — this screen used to fetch `listApplications` itself as a
 * workaround while that field was hardcoded to `[]`; now that it is populated server-side,
 * there is one fewer request and one fewer place this data could disagree with itself. The
 * scorecard's points still come from `getEvaluation` — this screen never scores anything.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { getVendor } from '../../api/vendors';
import { getEvaluation } from '../../api/applications';
import { useLocale } from '../../i18n/LocaleProvider';
import {
  Bar,
  Card,
  ClassPill,
  ErrorCard,
  LoadingCard,
  StatusPill,
  VENDORS_PATH,
  formatAmount,
  formatDate,
} from './shared';
import './manager.css';

type ExpiryTone = 'good' | 'warn' | 'crit' | 'neutral';

//: Presentational only — mirrors the badges the checklist already carries (doc_valid /
//: doc_expiring / doc_expired / doc_missing / doc_perm); the 60-day window matches the
//: server's own `DEFAULT_EXPIRING_WINDOW_DAYS` (spec §12), not a rule invented here.
function expiryBadge(
  status: string,
  daysToExpiry: number | null | undefined,
): { key: string; tone: ExpiryTone } {
  if (status !== 'uploaded') return { key: 'doc_missing', tone: 'neutral' };
  if (daysToExpiry === null || daysToExpiry === undefined) return { key: 'doc_perm', tone: 'good' };
  if (daysToExpiry < 0) return { key: 'doc_expired', tone: 'crit' };
  if (daysToExpiry <= 60) return { key: 'doc_expiring', tone: 'warn' };
  return { key: 'doc_valid', tone: 'good' };
}

interface ProjectRow {
  [index: number]: unknown;
}

export function VendorDetail({ vendorId }: { vendorId: string }) {
  const { t, locale } = useLocale();

  const vendor = useQuery({ queryKey: ['vendor', vendorId], queryFn: () => getVendor({ vendor_id: vendorId }) });
  const evaluations = vendor.data?.evaluations ?? [];

  const latestDecided = useMemo(() => {
    const decided = evaluations.filter((row) => row.decided_at);
    decided.sort((a, b) => (b.decided_at ?? '').localeCompare(a.decided_at ?? ''));
    return decided[0] ?? null;
  }, [evaluations]);

  const evaluation = useQuery({
    queryKey: ['evaluation', latestDecided?.application_id],
    queryFn: () => getEvaluation({ application_id: latestDecided!.application_id! }),
    enabled: !!latestDecided,
  });

  if (vendor.isLoading) return <LoadingCard />;
  if (vendor.isError || !vendor.data) return <ErrorCard message={String(vendor.error)} />;
  const v = vendor.data;
  const contacts = v.contacts ?? [];
  const currentFields = v.current_fields ?? {};
  const categories = v.categories ?? [];
  const documents = v.documents ?? [];
  const primaryContact = contacts.find((c) => c.is_primary) ?? contacts[0] ?? null;
  const completed = (currentFields['C.t1'] as ProjectRow[] | undefined) ?? [];
  const ongoing = (currentFields['C.t2'] as ProjectRow[] | undefined) ?? [];

  return (
    <>
      <Link to={VENDORS_PATH} className="mgr-btn mgr-btn-sm">
        {t('back')}
      </Link>
      <div
        className="page-head"
        style={{ marginTop: 12, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}
      >
        <div>
          <div className="mgr-eyebrow">
            {t(`type_${v.type}`)} · {v.voen ?? '—'}
          </div>
          <h2 style={{ fontSize: 22 }}>{v.legal_name}</h2>
          <div className="mgr-chips" style={{ marginTop: 6 }}>
            {categories.map((c) => (
              <span className="mgr-chip" key={c.category.code}>
                {locale === 'az' ? c.category.name_az : c.category.name_en}
              </span>
            ))}
            <StatusPill status={v.status} />
          </div>
        </div>
        <div className="mgr-gauge">
          <div
            className="mgr-ring"
            style={{
              background: `conic-gradient(var(--c${v.latest_class ?? 'NA'}) ${
                v.latest_score ? Math.round(v.latest_score * 3.6) : 0
              }deg, var(--line-2) 0)`,
            }}
          >
            <span>{v.latest_score != null ? formatAmount(v.latest_score) : 'NA'}</span>
          </div>
          <div>
            <div className="mgr-eyebrow">{t('total_score')}</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
              <ClassPill cls={v.latest_class} />
            </div>
            <div className="small muted" style={{ marginTop: 2 }}>
              {t('pass_mark')}
            </div>
          </div>
        </div>
      </div>

      <div className="mgr-grid mgr-g32">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card
            title={t('v_scores')}
            right={<span className="muted small">{evaluation.data?.model_version ?? '—'}</span>}
          >
            {!latestDecided ? (
              <div className="mgr-empty">{t('none')}</div>
            ) : evaluation.isLoading ? (
              <LoadingCard />
            ) : evaluation.data ? (
              <>
                <div className="mgr-bars">
                  {Object.entries(evaluation.data.computed.groups).map(([group, points]) => (
                    <div className="mgr-b" key={group}>
                      <span>{group}</span>
                      <Bar value={points} max={Math.max(points, 1)} />
                      <span className="mono" style={{ textAlign: 'right' }}>
                        {points}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mgr-table-wrap" style={{ marginTop: 14 }}>
                  <table className="mgr-table">
                    <thead>
                      <tr>
                        <th>{t('ev_crit')}</th>
                        <th className="mgr-r">{t('ev_raw')}</th>
                        <th className="mgr-r">{t('ev_pts')}</th>
                        <th className="mgr-r">{t('ev_max')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluation.data.rows.map((row) => (
                        <tr key={row.code}>
                          <td>
                            <span className="mono muted">{row.code}</span>{' '}
                            {locale === 'az' ? row.name_az : row.name_en}
                            {row.ko ? <span className="mgr-req"> KO</span> : null}
                          </td>
                          <td className="mgr-r mono">
                            {row.kind === 'rubric'
                              ? `${row.rubric_score ?? '—'} / 3`
                              : formatAmount(row.raw_value)}
                          </td>
                          <td
                            className="mgr-r mono"
                            style={{ color: row.points === 0 ? 'var(--crit)' : undefined }}
                          >
                            {row.points}
                          </td>
                          <td className="mgr-r mono muted">{row.max}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </Card>

          {completed.length > 0 || ongoing.length > 0 ? (
            <Card title={t('v_projects')}>
              <div className="mgr-table-wrap">
                <table className="mgr-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{locale === 'az' ? 'Layihə' : 'Project'}</th>
                      <th>{t('th_client')}</th>
                      <th className="mgr-r">{t('th_value')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {completed.map((row, index) => (
                      <tr key={`c-${index}`}>
                        <td className="mono muted">{index + 1}</td>
                        <td>{String(row[0] ?? '—')}</td>
                        <td>{String(row[1] ?? '—')}</td>
                        <td className="mgr-r mono">{formatAmount(Number(row[4]) || null)}</td>
                      </tr>
                    ))}
                    {ongoing.map((row, index) => (
                      <tr key={`o-${index}`} style={{ background: 'var(--accent-soft)' }}>
                        <td className="mono muted">▶</td>
                        <td>{String(row[0] ?? '—')}</td>
                        <td>{String(row[1] ?? '—')}</td>
                        <td className="mgr-r mono">{formatAmount(Number(row[5]) || null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : null}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card title={t('v_profile')}>
            <dl className="mgr-two">
              <dt>{t('d_voen')}</dt>
              <dd className="mono">{v.voen ?? '—'}</dd>
              <dt>{t('d_reg')}</dt>
              <dd>{v.registration_year ?? '—'}</dd>
              <dt>{t('d_contact')}</dt>
              <dd>{primaryContact?.name ?? '—'}</dd>
              <dt>{t('d_phone')}</dt>
              <dd className="mono">{primaryContact?.phone ?? '—'}</dd>
              <dt>{t('d_email')}</dt>
              <dd style={{ wordBreak: 'break-all' }}>{primaryContact?.email ?? '—'}</dd>
              <dt>{t('d_web')}</dt>
              <dd>{v.website ?? '—'}</dd>
              <dt>{t('d_source')}</dt>
              <dd>{v.primary_source ? t(`src_${v.primary_source}`) : '—'}</dd>
              <dt>{t('d_updated')}</dt>
              <dd className="mono">{formatDate(v.updated_at)}</dd>
              <dt style={{ gridColumn: '1 / -1' }}>{t('d_addr')}</dt>
              <dd style={{ gridColumn: '1 / -1' }}>{v.address ?? v.region ?? '—'}</dd>
            </dl>
          </Card>

          <Card title={t('v_docs')}>
            <div className="mgr-table-wrap" style={{ maxHeight: 420, overflow: 'auto' }}>
              <table className="mgr-table">
                <thead>
                  <tr>
                    <th>Kod</th>
                    <th>{t('ev_evidence')}</th>
                    <th>{t('vd_status')}</th>
                    <th>{t('vd_exp')}</th>
                  </tr>
                </thead>
                <tbody>
                  {documents
                    .filter((d) => !d.code.startsWith('H'))
                    .map((doc) => {
                      const badge = expiryBadge(doc.status, doc.days_to_expiry);
                      return (
                        <tr key={doc.code}>
                          <td className="mono">{doc.code}</td>
                          <td>
                            {locale === 'az' ? doc.name_az : doc.name_en}
                            {doc.mandatory ? <span className="mgr-req"> *</span> : null}
                          </td>
                          <td>
                            <span className={`mgr-pill mgr-pill-${badge.tone}`}>{t(badge.key)}</span>
                          </td>
                          <td className="mono small">
                            {doc.expiry_date ? formatDate(doc.expiry_date) : doc.status === 'uploaded' ? t('doc_perm') : '—'}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title={t('v_history')}>
            {evaluations.length > 0 ? (
              <div className="mgr-timeline">
                {evaluations.map((row) => (
                  <div key={row.application_id}>
                    <span className="mgr-d">{formatDate(row.decided_at)}</span>
                    <span>
                      {row.cycle_name ?? '—'} —{' '}
                      <b className="mono">{row.total != null ? formatAmount(row.total) : '—'}</b>{' '}
                      {row.cls ? <ClassPill cls={row.cls} /> : null}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mgr-empty">{t('none')}</div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

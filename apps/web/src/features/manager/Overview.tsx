/**
 * Screen 15 — manager overview (`/`), spec §8.
 *
 * KPI tiles, coverage by category with A/B share, class distribution, the attention list and
 * the recent activity feed. Every number is read straight from `/intel/*` and `/events` —
 * nothing here derives a count or a share the server did not already compute.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { getAttentionList, getClassDistribution, getIntelCoverage, getIntelOverview } from '../../api/intel';
import { listEvents } from '../../api/events';
import { useLocale } from '../../i18n/LocaleProvider';
import { Bar, Card, ErrorCard, LoadingCard } from './shared';
import './manager.css';

const CLASS_ORDER = ['A', 'B', 'C', 'D', 'F', 'KO'] as const;

const ATTENTION_TONE: Record<string, 'good' | 'warn' | 'crit' | 'accent'> = {
  info: 'accent',
  warn: 'warn',
  crit: 'crit',
};

const ATTENTION_LINK: Record<string, string> = {
  att_exp: '/vendors',
  att_rev: '/applications',
  att_inc: '/applications',
  att_gap: '/market',
};

const EVENT_LABEL_KEY: Record<string, string> = {
  'vendor.registered': 'act_vendor_registered',
  'vendor.invited': 'act_vendor_invited',
  'vendor.prequalified': 'act_vendor_prequalified',
  'vendor.rejected': 'act_vendor_rejected',
  'vendor.suspended': 'act_vendor_suspended',
  'application.submitted': 'act_application_submitted',
  'application.decided': 'act_application_decided',
  'document.uploaded': 'act_document_uploaded',
  'document.expiring': 'act_document_expiring',
  'project.matched': 'act_project_matched',
  'model.published': 'act_model_published',
  'sync.completed': 'act_sync_completed',
};

function eventSubject(payload: Record<string, unknown>): string | null {
  const candidate = payload.legal_name ?? payload.vendor_name ?? payload.name ?? null;
  return typeof candidate === 'string' ? candidate : null;
}

export function Overview() {
  const { t } = useLocale();

  const overview = useQuery({ queryKey: ['intel', 'overview'], queryFn: getIntelOverview });
  const coverage = useQuery({ queryKey: ['intel', 'coverage'], queryFn: () => getIntelCoverage() });
  const classes = useQuery({
    queryKey: ['intel', 'class-distribution'],
    queryFn: () => getClassDistribution(),
  });
  const attention = useQuery({ queryKey: ['intel', 'attention'], queryFn: getAttentionList });
  const activity = useQuery({
    queryKey: ['events', 'recent'],
    queryFn: () => listEvents({ page: 1, page_size: 8 }),
  });

  if (overview.isLoading) return <LoadingCard />;
  if (overview.isError) return <ErrorCard message={String(overview.error)} />;
  const kpis = overview.data;

  const classCounts = new Map((classes.data ?? []).map((row) => [row.cls, row.count]));
  const maxClassCount = Math.max(1, ...CLASS_ORDER.map((cls) => classCounts.get(cls) ?? 0));
  const maxCoverage = Math.max(1, ...(coverage.data ?? []).map((row) => row.total ?? 0));

  return (
    <>
      <div className="mgr-grid mgr-g4">
        <Card>
          <div className="mgr-kpi">
            <div className="mgr-kpi-lbl">{t('k_total')}</div>
            <div className="mgr-kpi-val">{kpis?.vendors_total ?? '—'}</div>
            <div className="mgr-kpi-sub">
              {kpis?.vendors_sub ?? 0} {t('k_sub')} · {kpis?.vendors_sup ?? 0} {t('k_sup')}
            </div>
          </div>
        </Card>
        <Card>
          <div className="mgr-kpi">
            <div className="mgr-kpi-lbl">{t('k_preq')}</div>
            <div className="mgr-kpi-val">{kpis?.prequalified ?? '—'}</div>
            <div className="mgr-kpi-sub">
              {kpis?.prequalified_ab ?? 0} {t('k_classAB')}
            </div>
          </div>
        </Card>
        <Card>
          <div className="mgr-kpi">
            <div className="mgr-kpi-lbl">{t('k_pending')}</div>
            <div className="mgr-kpi-val">{kpis?.awaiting_review ?? '—'}</div>
            <div className="mgr-kpi-sub">
              {kpis?.incomplete ?? 0} {t('k_needs')}
            </div>
          </div>
        </Card>
        <Card>
          <div className="mgr-kpi">
            <div className="mgr-kpi-lbl">{t('k_exp')}</div>
            <div
              className="mgr-kpi-val"
              style={{ color: (kpis?.documents_expiring_60d ?? 0) > 0 ? 'var(--warn)' : undefined }}
            >
              {kpis?.documents_expiring_60d ?? 0}
            </div>
            <div className="mgr-kpi-sub">
              {kpis?.category_gaps ?? 0} {t('mk_gap').toLowerCase()}
            </div>
          </div>
        </Card>
      </div>

      <div className="mgr-grid mgr-g32" style={{ marginTop: 16 }}>
        <Card
          title={t('h_cover')}
          right={
            <span className="mgr-legend">
              <span>
                <i style={{ background: 'var(--accent)' }} />
                {t('f_all')}
              </span>
              <span>
                <i style={{ background: 'var(--good)' }} />
                A/B
              </span>
            </span>
          }
        >
          {coverage.isLoading ? (
            <LoadingCard />
          ) : coverage.data && coverage.data.length > 0 ? (
            <div className="mgr-bars">
              {coverage.data.map((row) => (
                <div className="mgr-b" key={row.category_code}>
                  <span>{(row as { name_az?: string }).name_az ?? row.category_code}</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <Bar value={row.total ?? 0} max={maxCoverage} tone="accent" />
                    <Bar
                      value={Math.round((row.total ?? 0) * (row.ab_share ?? 0))}
                      max={maxCoverage}
                      tone="good"
                    />
                  </div>
                  <span className="mono" style={{ textAlign: 'right' }}>
                    {row.total ?? 0}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="mgr-empty">{t('none')}</div>
          )}
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card title={t('h_classes')}>
            <div className="mgr-bars">
              {CLASS_ORDER.map((cls) => (
                <div className="mgr-b" key={cls}>
                  <span className={`mgr-cls mgr-cls-${cls}`}>{cls}</span>
                  <Bar
                    value={classCounts.get(cls) ?? 0}
                    max={maxClassCount}
                    tone={
                      cls === 'A' || cls === 'B'
                        ? 'good'
                        : cls === 'F' || cls === 'KO'
                          ? 'crit'
                          : 'accent'
                    }
                  />
                  <span className="mono" style={{ textAlign: 'right' }}>
                    {classCounts.get(cls) ?? 0}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card title={t('h_attention')}>
            {attention.isLoading ? (
              <LoadingCard />
            ) : attention.data && attention.data.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {attention.data.map((item) => (
                  <Link
                    key={item.key}
                    to={item.link ?? ATTENTION_LINK[item.key] ?? '/'}
                    className={`mgr-alert mgr-alert-${ATTENTION_TONE[item.severity ?? 'info']}`}
                    style={{ display: 'block' }}
                  >
                    <b>{item.count}</b> {t(item.key)}
                  </Link>
                ))}
              </div>
            ) : (
              <div className="mgr-empty">{t('none')}</div>
            )}
          </Card>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title={t('h_recent')}>
          {activity.isLoading ? (
            <LoadingCard />
          ) : activity.data && activity.data.items.length > 0 ? (
            <div className="mgr-timeline">
              {activity.data.items.map((event) => {
                const subject = eventSubject(event.payload);
                const labelKey = EVENT_LABEL_KEY[event.type] ?? null;
                return (
                  <div key={event.id}>
                    <span className="mgr-d">{event.created_at.slice(0, 10)}</span>
                    <span>
                      {subject ? `${subject} — ` : ''}
                      {labelKey ? t(labelKey) : event.type}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="mgr-empty">{t('none')}</div>
          )}
        </Card>
      </div>
    </>
  );
}

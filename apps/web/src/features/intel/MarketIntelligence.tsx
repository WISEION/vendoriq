/**
 * Screen 25 — market intelligence (`/market`), spec §12.
 *
 * The six views: the category × class matrix, capacity per category, certification and
 * insurance penetration among prequalified subcontractors, the data-source split with its
 * staleness counter, documents expiring inside the window, and the category gaps.
 *
 * Every number arrives computed from `/intel/*`. Spec §12's claim for these views is that they
 * are "as honest as the freshness counter beside them", so a category with no vendors is shown
 * as a gap rather than omitted, and a figure the server did not send renders as an em dash
 * rather than a zero — an unknown and a zero are different facts.
 */
import { useQuery } from '@tanstack/react-query';
import {
  getExpiringDocuments,
  getIntelCapacity,
  getIntelCertification,
  getIntelCoverage,
  getIntelSources,
  getMarketGaps,
} from '../../api/intel';
import { useLocale } from '../../i18n/LocaleProvider';
import {
  Card,
  ClassPill,
  Empty,
  ErrorCard,
  LoadingCard,
  formatAmount,
  formatDate,
} from '../manager/shared';
import type { ScoreClass } from '../manager/shared';
import '../manager/manager.css';

const CLASS_ORDER: ScoreClass[] = ['A', 'B', 'C', 'D', 'F', 'KO'];

/** `—` rather than `0`: the server sending nothing is not the server sending zero. */
function count(value: number | null | undefined): string {
  return typeof value === 'number' ? String(value) : '—';
}

function percent(share: number | null | undefined): string {
  return typeof share === 'number' ? `${Math.round(share * 100)}%` : '—';
}

export function MarketIntelligence() {
  const { t, locale } = useLocale();
  const name = (row: { name_az?: string; name_en?: string; category_code?: string }) =>
    (locale === 'az' ? row.name_az : row.name_en) || row.category_code || '';

  const coverage = useQuery({ queryKey: ['intel', 'coverage'], queryFn: () => getIntelCoverage() });
  const capacity = useQuery({ queryKey: ['intel', 'capacity'], queryFn: getIntelCapacity });
  const certification = useQuery({
    queryKey: ['intel', 'certification'],
    queryFn: getIntelCertification,
  });
  const sources = useQuery({ queryKey: ['intel', 'sources'], queryFn: getIntelSources });
  const gaps = useQuery({ queryKey: ['intel', 'gaps'], queryFn: getMarketGaps });
  const expiring = useQuery({
    queryKey: ['intel', 'expiring'],
    queryFn: () => getExpiringDocuments(),
  });

  return (
    <div className="mgr-grid mgr-g32">
      <Card title={t('mk_heat')}>
        {coverage.isLoading ? (
          <LoadingCard />
        ) : coverage.isError ? (
          <ErrorCard message={t('in_failed')} />
        ) : !coverage.data?.length ? (
          <Empty>{t('mk_no_data')}</Empty>
        ) : (
          <div className="mgr-table-wrap">
            <table className="mgr-table">
              <thead>
                <tr>
                  <th scope="col">{t('th_category')}</th>
                  {CLASS_ORDER.map((cls) => (
                    <th scope="col" key={cls} className="mgr-r">
                      {cls}
                    </th>
                  ))}
                  <th scope="col" className="mgr-r">
                    {t('th_total')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {coverage.data.map((row) => (
                  <tr key={row.category_code}>
                    <th scope="row">{name(row)}</th>
                    {CLASS_ORDER.map((cls) => (
                      <td key={cls} className="mgr-r mono">
                        {count(row.counts?.[cls])}
                      </td>
                    ))}
                    <td className="mgr-r mono">{count(row.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t('mk_cap')}>
        {capacity.isLoading ? (
          <LoadingCard />
        ) : capacity.isError ? (
          <ErrorCard message={t('in_failed')} />
        ) : !capacity.data?.length ? (
          <Empty>{t('mk_no_data')}</Empty>
        ) : (
          <div className="mgr-table-wrap">
            <table className="mgr-table">
              <thead>
                <tr>
                  <th scope="col">{t('th_category')}</th>
                  <th scope="col" className="mgr-r">
                    {t('mk_vend')}
                  </th>
                  <th scope="col" className="mgr-r">
                    {t('mk_turn')}
                  </th>
                  <th scope="col" className="mgr-r">
                    {t('mk_eng')}
                  </th>
                  <th scope="col" className="mgr-r">
                    {t('mk_ongoing')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {capacity.data.map((row) => (
                  <tr key={row.category_code}>
                    <th scope="row">{name(row)}</th>
                    <td className="mgr-r mono">{count(row.vendor_count)}</td>
                    <td className="mgr-r mono">{formatAmount(row.total_turnover)}</td>
                    <td className="mgr-r mono">{count(row.engineers)}</td>
                    <td className="mgr-r mono">{count(row.ongoing_projects)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mgr-two">
        <Card title={t('mk_cert')}>
          {certification.isLoading ? (
            <LoadingCard />
          ) : certification.isError ? (
            <ErrorCard message={t('in_failed')} />
          ) : !certification.data?.length ? (
            <Empty>{t('mk_no_data')}</Empty>
          ) : (
            <dl className="mgr-bars">
              {certification.data.map((row) => (
                <div className="mgr-b" key={row.key}>
                  <span>{t(row.key)}</span>
                  <span className="mono">
                    {percent(row.share)} · {count(row.count)}/{count(row.total)}
                  </span>
                </div>
              ))}
            </dl>
          )}
        </Card>

        <Card title={t('mk_src')}>
          {sources.isLoading ? (
            <LoadingCard />
          ) : sources.isError ? (
            <ErrorCard message={t('in_failed')} />
          ) : !sources.data ? (
            <Empty>{t('mk_no_data')}</Empty>
          ) : (
            <>
              <dl className="mgr-bars">
                {sources.data.by_source.map((row) => (
                  <div className="mgr-b" key={row.source}>
                    <span>{t(`src_${row.source}`)}</span>
                    <span className="mono">
                      {percent(row.share)} · {count(row.count)}
                    </span>
                  </div>
                ))}
              </dl>
              <p className="mgr-src">
                {t('mk_fresh')}: {count(sources.data.stale_profiles)} {t('mk_fresh_txt')}
              </p>
            </>
          )}
        </Card>
      </div>

      <Card title={t('mk_exp')}>
        {expiring.isLoading ? (
          <LoadingCard />
        ) : expiring.isError ? (
          <ErrorCard message={t('in_failed')} />
        ) : !expiring.data?.items.length ? (
          <Empty>{t('mk_no_expiring')}</Empty>
        ) : (
          <div className="mgr-table-wrap">
            <table className="mgr-table">
              <thead>
                <tr>
                  <th scope="col">{t('th_vendor')}</th>
                  <th scope="col">{t('th_document')}</th>
                  <th scope="col">{t('th_expires')}</th>
                </tr>
              </thead>
              <tbody>
                {expiring.data.items.map((doc) => (
                  <tr key={doc.id}>
                    <th scope="row">{doc.vendor_name}</th>
                    <td className="mono">{doc.code}</td>
                    <td className="mono">{formatDate(doc.expiry_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t('mk_gap')}>
        {gaps.isLoading ? (
          <LoadingCard />
        ) : gaps.isError ? (
          <ErrorCard message={t('in_failed')} />
        ) : !gaps.data?.length ? (
          <Empty>{t('mk_no_gaps')}</Empty>
        ) : (
          <>
            <p className="small muted">{t('mk_gap_txt')}</p>
            <dl className="mgr-bars">
              {gaps.data.map((gap) => (
                <div className="mgr-b" key={gap.category_code}>
                  <span>{name(gap)}</span>
                  <span className="mono">
                    {t('mk_registered')}: {count(gap.registered_vendors)}
                  </span>
                </div>
              ))}
            </dl>
          </>
        )}
      </Card>

      <Card title={t('mk_classes')}>
        <div className="mgr-chips">
          {CLASS_ORDER.map((cls) => (
            <ClassPill key={cls} cls={cls} />
          ))}
        </div>
      </Card>
    </div>
  );
}

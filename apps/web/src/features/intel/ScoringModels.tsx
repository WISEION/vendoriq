/**
 * Screen 26 — scoring model versions (`/scoring-models`), spec §10.3.
 *
 * A read-only list. `status` and `is_locked` are shown as the two separate facts they are
 * (ADR-014, ADR-017): `status` is the commission's editorial judgement — the supplier model
 * ships "proposed" until the commission freezes it — while `is_locked` is the mechanical fact
 * that an application has been scored with the version, which is what makes its definition
 * immutable. A version can be locked and still proposed; showing one label for both would
 * lose that.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { listScoringModels } from '../../api/scoring-models';
import { useLocale } from '../../i18n/LocaleProvider';
import { Card, Empty, ErrorCard, LoadingCard } from '../manager/shared';
import '../manager/manager.css';

export function modelPath(version: string): string {
  return `/scoring-models/${version}`;
}

export function ScoringModels() {
  const { t, locale } = useLocale();
  const models = useQuery({ queryKey: ['scoring-models'], queryFn: () => listScoringModels() });

  if (models.isLoading) return <LoadingCard />;
  if (models.isError) return <ErrorCard message={t('in_failed')} />;
  if (!models.data?.length) return <Empty>{t('mo_none')}</Empty>;

  return (
    <Card title={t('mo_title')}>
      <div className="mgr-table-wrap">
        <table className="mgr-table">
          <thead>
            <tr>
              <th scope="col">{t('th_version')}</th>
              <th scope="col">{t('th_model_name')}</th>
              <th scope="col">{t('th_vendor_type')}</th>
              <th scope="col">{t('th_status')}</th>
              <th scope="col" className="mgr-r">
                {t('th_pass_mark')}
              </th>
              <th scope="col" className="mgr-r">
                {t('mo_applications')}
              </th>
              <th scope="col">{t('mo_locked')}</th>
            </tr>
          </thead>
          <tbody>
            {models.data.map((model) => (
              <tr key={model.version}>
                <th scope="row" className="mono">
                  <Link to={modelPath(model.version)}>{model.version}</Link>
                </th>
                <td>{locale === 'az' ? model.name_az : model.name_en}</td>
                <td>{t(`vtype_${model.vendor_type}`)}</td>
                <td>
                  <span
                    className={`mgr-pill mgr-pill-${model.status === 'active' ? 'good' : 'neutral'}`}
                  >
                    {t(`mstatus_${model.status}`)}
                  </span>
                </td>
                <td className="mgr-r mono">{model.pass_mark}</td>
                <td className="mgr-r mono">{model.application_count}</td>
                <td>{model.is_locked ? t('mo_locked_yes') : t('mo_locked_no')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

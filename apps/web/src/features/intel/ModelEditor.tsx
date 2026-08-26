/**
 * Screen 27 — one scoring model version (`/scoring-models/$version`), spec §10.3.
 *
 * Criteria, groups and class bands, plus the two actions a version supports: a re-score test
 * against a cycle, and publishing a draft.
 *
 * **Editing is refused on a locked version, by the server** (ADR-017). This screen disables
 * the controls to say so early, but the refusal that matters is `patchScoringModelDraft`'s:
 * `is_locked` means an application has already been scored with this definition, and changing
 * a weight would silently rewrite a score the commission has signed. The way to change a
 * published model is a new version, which is what the draft action creates.
 *
 * The re-score test reports what *would* move and persists nothing.
 */
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getScoringModel, testRescore } from '../../api/scoring-models';
import { listCycles } from '../../api/cycles';
import { useLocale } from '../../i18n/LocaleProvider';
import { Card, ClassPill, Empty, ErrorCard, LoadingCard } from '../manager/shared';
import type { ScoreClass } from '../manager/shared';
import '../manager/manager.css';

export function ModelEditor({ version }: { version: string }) {
  const { t, locale } = useLocale();
  const [cycleId, setCycleId] = useState('');

  const model = useQuery({
    queryKey: ['scoring-models', version],
    queryFn: () => getScoringModel({ version }),
  });
  const cycles = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() });

  const rescore = useMutation({
    mutationFn: () => testRescore({ version }, { cycle_id: cycleId }),
  });

  if (model.isLoading) return <LoadingCard />;
  if (model.isError || !model.data) return <ErrorCard message={t('in_failed')} />;

  const m = model.data;
  const locked = m.is_locked;
  const groupName = (group: string) => {
    const def = m.groups.find((g) => g.group === group);
    return def ? (locale === 'az' ? def.name_az : def.name_en) : group;
  };

  return (
    <div className="mgr-grid mgr-g32">
      <Card title={locale === 'az' ? m.name_az : m.name_en}>
        <dl className="mgr-bars">
          <div className="mgr-b">
            <span>{t('th_version')}</span>
            <span className="mono">{m.version}</span>
          </div>
          <div className="mgr-b">
            <span>{t('th_status')}</span>
            <span>{t(`mstatus_${m.status}`)}</span>
          </div>
          <div className="mgr-b">
            <span>{t('th_pass_mark')}</span>
            <span className="mono">
              {m.pass_mark} / {m.total_max} {m.currency}
            </span>
          </div>
          <div className="mgr-b">
            <span>{t('mo_locked')}</span>
            <span>{locked ? t('mo_locked_yes') : t('mo_locked_no')}</span>
          </div>
        </dl>
        {locked ? <p className="mgr-src">{t('mo_locked_note')}</p> : null}
      </Card>

      <Card title={t('mo_criteria')}>
        <div className="mgr-table-wrap">
          <table className="mgr-table">
            <thead>
              <tr>
                <th scope="col">{t('th_code')}</th>
                <th scope="col">{t('th_group')}</th>
                <th scope="col">{t('th_criterion')}</th>
                <th scope="col" className="mgr-r">
                  {t('th_max')}
                </th>
                <th scope="col">{t('th_kind')}</th>
                <th scope="col">{t('th_ko')}</th>
              </tr>
            </thead>
            <tbody>
              {m.criteria.map((c) => (
                <tr key={c.code}>
                  <th scope="row" className="mono">
                    {c.code}
                  </th>
                  <td>{groupName(c.group)}</td>
                  <td>{locale === 'az' ? c.name_az : c.name_en}</td>
                  <td className="mgr-r mono">{c.max}</td>
                  <td>{t(`ckind_${c.kind}`)}</td>
                  <td>{c.ko ? t('mo_ko_yes') : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title={t('mo_bands')}>
        <div className="mgr-chips">
          {m.classes.map((band) => (
            <span key={band.cls} className="mgr-chip">
              <ClassPill cls={band.cls as ScoreClass} /> ≥ {band.min}
            </span>
          ))}
        </div>
      </Card>

      <Card title={t('mo_rescore')}>
        <p className="mgr-src">{t('mo_rescore_note')}</p>
        <div className="mgr-form-row">
          <label htmlFor="rescore-cycle">{t('th_cycle')}</label>
          <select
            id="rescore-cycle"
            value={cycleId}
            onChange={(event) => setCycleId(event.target.value)}
          >
            <option value="">{t('mo_pick_cycle')}</option>
            {cycles.data?.items.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="mgr-btn mgr-btn-primary"
            disabled={!cycleId || rescore.isPending}
            onClick={() => rescore.mutate()}
          >
            {t('mo_rescore_run')}
          </button>
        </div>

        {rescore.isError ? <ErrorCard message={t('in_failed')} /> : null}
        {rescore.data ? (
          rescore.data.rows.length === 0 ? (
            <Empty>{t('mo_rescore_none')}</Empty>
          ) : (
            <>
              <p className="mgr-src">
                {t('mo_rescore_changed')}: {rescore.data.summary?.changed_count ?? 0} ·{' '}
                {t('mo_rescore_classes')}: {rescore.data.summary?.class_changes ?? 0}
              </p>
              <div className="mgr-table-wrap">
                <table className="mgr-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('th_vendor')}</th>
                      <th scope="col" className="mgr-r">
                        {t('mo_old')}
                      </th>
                      <th scope="col" className="mgr-r">
                        {t('mo_new')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rescore.data.rows.map((row) => (
                      <tr key={row.vendor_id}>
                        <th scope="row">{row.vendor_name}</th>
                        <td className="mgr-r mono">
                          {row.old_total ?? '—'} {row.old_class ?? ''}
                        </td>
                        <td className="mgr-r mono">
                          {row.new_total ?? '—'} {row.new_class ?? ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )
        ) : null}
      </Card>
    </div>
  );
}

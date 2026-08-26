import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { listProjects } from '../../api/projects';
import { useLocale } from '../../i18n/LocaleProvider';
import { formatDate, formatDateTime, formatMoney } from './format';
import { PROJECT_NEW_PATH, projectEditPath, projectMatchingPath } from './paths';
import { StatePill } from './StatePill';
import './projects.css';

const STAGES = ['pipeline', 'go_nogo', 'tender', 'execution'] as const;

/** Screen 22 — `/projects`: value, package count, coverage % and the go/no-go pill. */
export function ProjectsListScreen() {
  const { t, locale } = useLocale();
  const [q, setQ] = useState('');
  const [stage, setStage] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['projects', q, stage],
    queryFn: () =>
      listProjects({
        page_size: 100,
        q: q || undefined,
        stage: stage ? [stage as (typeof STAGES)[number]] : undefined,
      }),
  });

  const items = query.data?.items ?? [];

  return (
    <div>
      <div className="page-head">
        <h2>{t('proj_title')}</h2>
        <p>{t('proj_sub')}</p>
      </div>

      <div className="viq-toolbar">
        <input
          className="viq-search"
          type="search"
          aria-label={t('proj_search_placeholder')}
          placeholder={t('proj_search_placeholder')}
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
        <select aria-label={t('th_stage')} value={stage ?? ''} onChange={(event) => setStage(event.target.value || null)}>
          <option value="">{t('f_all')}</option>
          {STAGES.map((value) => (
            <option key={value} value={value}>
              {t(`stage_${value}`)}
            </option>
          ))}
        </select>
        <div className="viq-toolbar-spacer" />
        <Link to={PROJECT_NEW_PATH} className="btn-primary">
          {t('proj_new')}
        </Link>
      </div>

      <div className="viq-card">
        <div className="viq-card-body viq-tight">
          <div className="viq-table-wrap">
            <table className="viq-table">
              <thead>
                <tr>
                  <th>{t('th_project')}</th>
                  <th>{t('th_client')}</th>
                  <th>{t('th_stage')}</th>
                  <th className="viq-r">{t('th_value')}</th>
                  <th className="viq-r">{t('th_packages')}</th>
                  <th>{t('th_coverage')}</th>
                  <th>{t('th_gonogo')}</th>
                  <th>{t('proj_last_matched')}</th>
                  <th>{t('th_deadline')}</th>
                  <th aria-hidden="true" />
                </tr>
              </thead>
              <tbody>
                {items.map((project) => (
                  <tr key={project.id}>
                    <td>
                      <Link to={projectMatchingPath(project.id)}>
                        <b>{project.name}</b>
                      </Link>
                      <div className="viq-package-meta viq-mono">{project.code}</div>
                    </td>
                    <td>{project.client || '—'}</td>
                    <td>{t(`stage_${project.stage}`)}</td>
                    <td className="viq-r viq-mono">{formatMoney(project.estimated_value, locale)}</td>
                    <td className="viq-r viq-mono">
                      {project.package_count} {t('packages')}
                    </td>
                    <td>
                      {project.coverage_pct === null || project.coverage_pct === undefined ? (
                        '—'
                      ) : (
                        <div className="viq-coverage">
                          <div
                            className={`viq-bar ${
                              project.match_state === 'go'
                                ? 'viq-pill-go'
                                : project.match_state === 'cond'
                                  ? 'viq-pill-cond'
                                  : 'viq-pill-nogo'
                            }`}
                            role="progressbar"
                            aria-valuenow={project.coverage_pct}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={t('th_coverage')}
                          >
                            <i style={{ width: `${project.coverage_pct}%` }} />
                          </div>
                          <span className="viq-mono">{project.coverage_pct}%</span>
                        </div>
                      )}
                    </td>
                    <td>
                      <StatePill state={project.match_state} />
                    </td>
                    <td className="viq-mono">
                      {project.last_matched_at ? formatDateTime(project.last_matched_at, locale) : t('proj_never_matched')}
                    </td>
                    <td className="viq-mono">{formatDate(project.deadline, locale)}</td>
                    <td>
                      <Link to={projectEditPath(project.id)} className="btn-link">
                        {t('pe_edit_title')}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {query.data && items.length === 0 ? <p className="viq-empty">{t('proj_empty')}</p> : null}
        </div>
      </div>
    </div>
  );
}

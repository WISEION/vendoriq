import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/client';
import { exportProject, getLatestMatch, getProject, runMatch } from '../../api/projects';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import { formatDateTime, formatMoney } from './format';
import { ClassBadge, StatePill } from './StatePill';
import './projects.css';

type MatchRun = Awaited<ReturnType<typeof runMatch>>;
type PackageMatch = MatchRun['packages'][number];
type MatchCandidate = PackageMatch['candidates'][number];

const KNOWN_CERTS = new Set(['iso9001', 'iso45001']);

async function fetchLatestMatch(projectId: string): Promise<MatchRun | null> {
  try {
    return await getLatestMatch({ project_id: projectId });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Screen 24 — `/projects/$projectId`: per-package candidates, gap and the recommendation. */
export function ProjectMatchingScreen({ projectId }: { projectId: string }) {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();

  const projectQuery = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject({ project_id: projectId }) });
  const matchQuery = useQuery({
    queryKey: ['project', projectId, 'match', 'latest'],
    queryFn: () => fetchLatestMatch(projectId),
  });

  const [showParams, setShowParams] = useState(false);
  const [strongMin, setStrongMin] = useState('');
  const [capacityRatio, setCapacityRatio] = useState('');
  const [supplierDivisor, setSupplierDivisor] = useState('');

  const runMutation = useMutation({
    mutationFn: () => {
      // `MatchParams` carries a `default` on every field, which the generator (correctly,
      // per its own rule) reads as "always present" — but the contract itself declares no
      // `required` list, and the server treats an omitted field as "use the organisation
      // default" (services/matching.py `resolve_params`). Building the body from only the
      // fields the officer actually typed, then asserting the generated shape, matches the
      // real contract; sending explicit `undefined`s would not typecheck against it.
      const overrides: Record<string, number> = {};
      if (strongMin) overrides.strong_min = Number(strongMin);
      if (capacityRatio) overrides.capacity_ratio = Number(capacityRatio);
      if (supplierDivisor) overrides.supplier_turnover_divisor = Number(supplierDivisor);
      return runMatch(
        { project_id: projectId },
        overrides as unknown as Parameters<typeof runMatch>[1],
      );
    },
    onSuccess: (run) => {
      queryClient.setQueryData(['project', projectId, 'match', 'latest'], run);
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const exportMutation = useMutation({
    // `exportProject` (api/projects.ts, not owned by this task) takes no `query` today, so
    // the `locale` the contract's `LocaleParam` offers cannot reach the request — see the
    // task report's change request. The export renders in the server's default locale (az).
    mutationFn: () => exportProject({ project_id: projectId }),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${projectQuery.data?.code ?? 'project'}-matching.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
  });

  const handleRun = (event: FormEvent) => {
    event.preventDefault();
    runMutation.mutate();
  };

  const project = projectQuery.data;
  const run = runMutation.data ?? matchQuery.data ?? null;
  const packagesById = new Map((run?.packages ?? []).map((pkg) => [pkg.package_id, pkg]));

  return (
    <div>
      <div className="page-head">
        <h2>{project?.name ?? '—'}</h2>
        <p className="viq-mono">
          {project?.code} {project?.client ? `· ${project.client}` : ''}
        </p>
      </div>

      {run ? (
        <>
          <div className="viq-banner">
            <div className="viq-banner-metric">
              <span className="viq-label">{t('th_gonogo')}</span>
              <span className="viq-value">
                <StatePill state={run.state} />
              </span>
            </div>
            <div className="viq-banner-metric">
              <span className="viq-label">{t('th_coverage')}</span>
              <span className="viq-value viq-mono">{run.coverage_pct}%</span>
            </div>
            <div className="viq-banner-metric">
              <span className="viq-label">{t('pm_last_run')}</span>
              <span className="viq-value viq-mono" style={{ fontSize: 14 }}>
                {formatDateTime(run.ran_at, locale)}
              </span>
            </div>
          </div>
          <div
            className={`viq-alert ${
              run.state === 'go' ? 'viq-alert-good' : run.state === 'cond' ? 'viq-alert-warn' : 'viq-alert-crit'
            }`}
          >
            <b>{t('m_recommend')}:</b> {run.recommendation_key ? t(run.recommendation_key) : ''}
          </div>
        </>
      ) : (
        <p className="viq-alert viq-alert-info">{t('pm_never_run')}</p>
      )}

      <form onSubmit={handleRun} noValidate>
        <div className="viq-actions">
          <button type="submit" className="btn-primary" disabled={runMutation.isPending}>
            {runMutation.isPending ? t('pm_running') : t('pm_run')}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending || !run}
          >
            {exportMutation.isPending ? t('pm_exporting') : t('pm_export')}
          </button>
        </div>
        <details className="viq-details" open={showParams} onToggle={(event) => setShowParams(event.currentTarget.open)}>
          <summary>{t('pm_params_title')}</summary>
          <div className="viq-fieldset">
            <div className="field">
              <label htmlFor="pm-strong-min">{t('pm_strong_min')}</label>
              <input
                id="pm-strong-min"
                type="number"
                min={1}
                placeholder={t('pm_use_defaults')}
                value={strongMin}
                onChange={(event) => setStrongMin(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="pm-capacity-ratio">{t('pm_capacity_ratio')}</label>
              <input
                id="pm-capacity-ratio"
                type="number"
                min={0}
                max={1}
                step={0.05}
                placeholder={t('pm_use_defaults')}
                value={capacityRatio}
                onChange={(event) => setCapacityRatio(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="pm-supplier-divisor">{t('pm_supplier_divisor')}</label>
              <input
                id="pm-supplier-divisor"
                type="number"
                min={0.1}
                step={0.5}
                placeholder={t('pm_use_defaults')}
                value={supplierDivisor}
                onChange={(event) => setSupplierDivisor(event.target.value)}
              />
            </div>
          </div>
        </details>
        {runMutation.isError ? (
          <p className="form-error" role="alert">
            {t(localisedErrorKey(runMutation.error))}
          </p>
        ) : null}
        {exportMutation.isError ? (
          <p className="form-error" role="alert">
            {t(localisedErrorKey(exportMutation.error))}
          </p>
        ) : null}
      </form>

      <div className="viq-package-list" style={{ marginTop: 20 }}>
        {(project?.packages ?? []).map((pkg) => {
          const result = packagesById.get(pkg.id);
          return (
            <PackageCard
              key={pkg.id}
              categoryName={locale === 'en' ? pkg.category.name_en : pkg.category.name_az}
              minClass={pkg.min_class}
              requiredCerts={pkg.required_certs ?? []}
              estimatedValue={pkg.estimated_value}
              result={result}
            />
          );
        })}
      </div>
    </div>
  );
}

function PackageCard({
  categoryName,
  minClass,
  requiredCerts,
  estimatedValue,
  result,
}: {
  categoryName: string;
  minClass: string;
  requiredCerts: string[];
  estimatedValue: number;
  result: PackageMatch | undefined;
}) {
  const { t, locale } = useLocale();
  return (
    <div className="viq-card">
      <div className="viq-card-head">
        <div>
          <h3>
            {categoryName} <span className="viq-mono viq-package-meta">{formatMoney(estimatedValue, locale)}</span>
          </h3>
          <p className="viq-package-meta">
            {t('m_min')}: <ClassBadge cls={minClass} />
            {requiredCerts.length > 0 ? ` · ${requiredCerts.map((cert) => (KNOWN_CERTS.has(cert) ? t(cert) : cert)).join(', ')}` : ''}
            {result ? ` · ${t('m_cands')}: ${result.eligible_count ?? 0} · ${t('m_strong')}: ${result.strong_count ?? 0}` : ''}
          </p>
        </div>
        <StatePill state={result?.state} />
      </div>
      <div className="viq-card-body">
        {result?.gap ? <p className="viq-alert viq-alert-warn">{t('m_gap')}: {t(result.gap)}</p> : null}
        {!result || result.candidates.length === 0 ? (
          <p className="viq-empty">{t('pm_candidates_empty')}</p>
        ) : (
          <div className="viq-table-wrap">
            <table className="viq-table">
              <thead>
                <tr>
                  <th>{t('th_vendor')}</th>
                  <th className="viq-r">{t('th_score')}</th>
                  <th>{t('th_class')}</th>
                  <th className="viq-r">{t('pm_capacity_value')}</th>
                  <th>{t('m_fit')}</th>
                  <th>{t('pm_eligible')}</th>
                  <th>{t('pm_reasons')}</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.map((candidate) => (
                  <CandidateRow key={candidate.vendor_id} candidate={candidate} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function CandidateRow({ candidate }: { candidate: MatchCandidate }) {
  const { t, locale } = useLocale();
  return (
    <tr className={candidate.eligible ? undefined : 'viq-candidate-ineligible'}>
      <td>
        <b>{candidate.legal_name}</b>
      </td>
      <td className="viq-r viq-mono">{candidate.total}</td>
      <td>
        <ClassBadge cls={candidate.cls} />
      </td>
      <td className="viq-r viq-mono">{formatMoney(candidate.capacity_value, locale)}</td>
      <td>
        <span className={`viq-pill ${candidate.capacity_fit ? 'viq-pill-go' : 'viq-pill-cond'}`}>
          {candidate.capacity_fit ? t('m_capfit_ok') : t('m_capfit_no')}
        </span>
      </td>
      <td>
        <span className={`viq-pill ${candidate.eligible ? 'viq-pill-go' : 'viq-pill-nogo'}`}>
          {candidate.eligible ? t('pm_eligible') : t(candidate.reasons?.[0] ?? 'not_prequalified')}
        </span>
      </td>
      <td>
        {candidate.reasons && candidate.reasons.length > 0 ? (
          <ul className="viq-reasons">
            {candidate.reasons.map((reason) => (
              <li key={reason}>{t(reason)}</li>
            ))}
          </ul>
        ) : (
          '—'
        )}
      </td>
    </tr>
  );
}

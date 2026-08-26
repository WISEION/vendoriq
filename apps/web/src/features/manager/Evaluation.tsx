/**
 * Screen 19 — evaluation (`/applications/$applicationId`), spec §8, §9, §10.
 *
 * Every criterion with its raw indicator, the evidence document code, an editable 0–3 rubric
 * cell for rubric criteria, live per-criterion points, group totals, the KO check and the
 * class. **The only number this screen ever shows is one `computeScore` or `getEvaluation`
 * returned** — points, group totals, the class and the KO result all come over the wire; nade
 * this file were to add `x / 3 * max` anywhere, that would be exactly the bug the lint rule
 * (brief §2, Gate 2) exists to catch. Approve is disabled below the pass mark or on a
 * knock-out failure, but that is a convenience — `decideApplication` enforces it server-side
 * regardless of what this screen renders.
 */
import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
  computeScore,
  decideApplication,
  getEvaluation,
  putEvaluation,
  putSecondEvaluation,
} from '../../api/applications';
import { ApiError } from '../../api/client';
import { useLocale } from '../../i18n/LocaleProvider';
import { APPLICATIONS_PATH, Card, ClassPill, ErrorCard, LoadingCard, formatAmount } from './shared';
import './manager.css';

type RubricState = Record<string, number | ''>;

function rubricFromRows(
  rows: { code: string; kind: string; rubric_score?: number | null }[],
): RubricState {
  const state: RubricState = {};
  for (const row of rows) {
    if (row.kind === 'rubric') state[row.code] = row.rubric_score ?? '';
  }
  return state;
}

function toRubricScores(state: RubricState): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [code, value] of Object.entries(state)) {
    if (value !== '') out[code] = value;
  }
  return out;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

export function Evaluation({ applicationId }: { applicationId: string }) {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();

  const evaluation = useQuery({
    queryKey: ['evaluation', applicationId],
    queryFn: () => getEvaluation({ application_id: applicationId }),
  });

  const [rubric, setRubric] = useState<RubricState>({});
  const [dirty, setDirty] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState<'reject' | 'request_info' | null>(null);
  const [justification, setJustification] = useState('');
  const [secondMode, setSecondMode] = useState(false);
  const [secondRubric, setSecondRubric] = useState<RubricState>({});

  useEffect(() => {
    if (evaluation.data && !dirty) {
      setRubric(rubricFromRows(evaluation.data.rows));
    }
  }, [evaluation.data, dirty]);

  const live = useMutation({
    mutationFn: (next: RubricState) =>
      computeScore({ application_id: applicationId }, { rubric_scores: toRubricScores(next) }),
  });

  useEffect(() => {
    if (!dirty) return;
    // A light debounce: `computeScore` is a network round trip, and an officer typing a
    // two-digit-adjacent value one keystroke at a time should not fire one request per key.
    const timer = window.setTimeout(() => live.mutate(rubric), 200);
    return () => window.clearTimeout(timer);
  }, [rubric, dirty]);

  const save = useMutation({
    mutationFn: () =>
      putEvaluation({ application_id: applicationId }, { rubric_scores: toRubricScores(rubric) }),
    onSuccess: (data) => {
      queryClient.setQueryData(['evaluation', applicationId], data);
      setDirty(false);
    },
  });

  const decide = useMutation({
    mutationFn: (body: { decision: 'approve' | 'reject' | 'request_info'; justification?: string }) =>
      decideApplication({ application_id: applicationId }, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evaluation', applicationId] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      setDecisionOpen(null);
      setJustification('');
    },
  });

  const secondSave = useMutation({
    mutationFn: () =>
      putSecondEvaluation(
        { application_id: applicationId },
        { rubric_scores: toRubricScores(secondRubric) },
      ),
  });

  const groups = useMemo(() => {
    const seen: string[] = [];
    for (const row of evaluation.data?.rows ?? []) if (!seen.includes(row.group)) seen.push(row.group);
    return seen;
  }, [evaluation.data]);

  if (evaluation.isLoading) return <LoadingCard />;
  if (evaluation.isError || !evaluation.data) return <ErrorCard message={String(evaluation.error)} />;
  const data = evaluation.data;
  const computed = live.data ?? data.computed;
  // Both `ko` and `pass_mark` are numbers the server already computed (`computeScore` /
  // `getEvaluation`); comparing them here gates a button, it does not derive a score.
  const canApprove = live.data
    ? live.data.ko && live.data.pass_mark != null && live.data.total >= live.data.pass_mark
    : data.can_approve;

  function handleCellChange(code: string, raw: string) {
    const value = raw === '' ? '' : Math.max(0, Math.min(3, Number(raw) || 0));
    setRubric((prev) => ({ ...prev, [code]: value }));
    setDirty(true);
  }

  function handleSecondCellChange(code: string, raw: string) {
    const value = raw === '' ? '' : Math.max(0, Math.min(3, Number(raw) || 0));
    setSecondRubric((prev) => ({ ...prev, [code]: value }));
  }

  function handleReset() {
    setRubric(rubricFromRows(data.rows));
    setDirty(false);
    // `computed` below reads `live.data ?? data.computed`, so leaving the last live result
    // in place made Reset restore the *inputs* while the score, class and KO verdict stayed
    // at the abandoned edit — the two halves of the screen disagreeing, with the wrong half
    // being the one an officer approves from.
    live.reset();
  }

  function openDecision(kind: 'reject' | 'request_info') {
    setDecisionOpen(kind);
    setJustification('');
  }

  function submitDecision(event: FormEvent) {
    event.preventDefault();
    if (!decisionOpen) return;
    decide.mutate({ decision: decisionOpen, justification });
  }

  return (
    <>
      <Link to={APPLICATIONS_PATH} className="mgr-btn mgr-btn-sm">
        {t('back')}
      </Link>
      <div className="page-head" style={{ marginTop: 12 }}>
        <div>
          <div className="mgr-eyebrow">
            {t('ev_title')} · {data.model_version}
          </div>
          <h2 style={{ fontSize: 22 }}>{data.evaluator_name ?? t('ev_title')}</h2>
          <p>{t('ev_sub')}</p>
        </div>
      </div>

      <div className="mgr-grid mgr-g32">
        <Card
          title={t('ev_crit')}
          right={
            <div style={{ display: 'flex', gap: 6 }}>
              <button type="button" className="mgr-btn mgr-btn-sm" onClick={handleReset} disabled={!dirty}>
                {t('ev_reset')}
              </button>
              <button
                type="button"
                className="mgr-btn mgr-btn-sm mgr-btn-primary"
                onClick={() => save.mutate()}
                disabled={save.isPending || !dirty}
              >
                {save.isPending ? `${t('ev_save')}…` : t('ev_save')}
              </button>
            </div>
          }
        >
          {save.isError ? <div className="mgr-alert mgr-alert-crit">{errorMessage(save.error)}</div> : null}
          {save.isSuccess ? <div className="mgr-alert mgr-alert-good">{t('ev_saved')}</div> : null}
          <div
            className="mgr-score-row mgr-score-head"
            aria-hidden="true"
            style={{ gridTemplateColumns: '48px 1fr 130px 90px 80px' }}
          >
            <span>Kod</span>
            <span>{t('ev_crit')}</span>
            <span>{t('ev_raw')}</span>
            <span style={{ textAlign: 'right' }}>{t('ev_pts')}</span>
            <span />
          </div>
          {groups.map((group) => {
            const rows = data.rows.filter((row) => row.group === group);
            const groupTotal = computed.groups[group] ?? 0;
            const groupMax = rows.reduce((sum, row) => sum + row.max, 0);
            return (
              <div key={group}>
                <div
                  className="mgr-score-row mgr-grp"
                  style={{ gridTemplateColumns: '48px 1fr 130px 90px 80px' }}
                >
                  <div style={{ gridColumn: '1 / -1' }}>
                    {group}. {t('ev_group')}
                    <span className="muted mono small" style={{ marginLeft: 6 }}>
                      {groupTotal} / {groupMax}
                    </span>
                  </div>
                </div>
                {rows.map((row) => {
                  const points = computed.per[row.code] ?? row.points ?? 0;
                  return (
                    <div
                      key={row.code}
                      className="mgr-score-row"
                      style={{ gridTemplateColumns: '48px 1fr 130px 90px 80px' }}
                    >
                      <span className="mono muted">{row.code}</span>
                      <span>
                        {locale === 'az' ? row.name_az : row.name_en}
                        {row.ko ? <span className="mgr-req"> KO</span> : null}
                        <div className="mgr-src">
                          {row.evidence_doc ?? '—'}
                          {row.unit ? ` · ${row.unit}` : ''}
                        </div>
                      </span>
                      {row.kind === 'rubric' ? (
                        <span>
                          <label className="mgr-sr-only" htmlFor={`rubric-${row.code}`}>
                            {row.code} {locale === 'az' ? row.name_az : row.name_en}
                          </label>
                          <input
                            id={`rubric-${row.code}`}
                            type="number"
                            min={0}
                            max={3}
                            step={1}
                            inputMode="numeric"
                            value={rubric[row.code] ?? ''}
                            onChange={(event) => handleCellChange(row.code, event.target.value)}
                          />
                        </span>
                      ) : (
                        <span className="mono">{formatAmount(row.raw_value)}</span>
                      )}
                      <span
                        className="mgr-r mono"
                        style={{ textAlign: 'right', color: points === 0 ? 'var(--crit)' : undefined }}
                      >
                        <b>{points}</b> <span className="muted">/ {row.max}</span>
                      </span>
                      <span className="mgr-bar" style={{ alignSelf: 'center' }}>
                        <i
                          style={{
                            width: `${(points / row.max) * 100}%`,
                            background: points === 0 ? 'var(--crit)' : 'var(--accent)',
                          }}
                        />
                      </span>
                    </div>
                  );
                })}
              </div>
            );
          })}

          <div style={{ marginTop: 18 }}>
            <button
              type="button"
              className="mgr-btn mgr-btn-sm"
              onClick={() => {
                setSecondMode((v) => !v);
                if (!secondMode) setSecondRubric(rubricFromRows(data.rows));
              }}
            >
              {secondMode ? t('ev_second_hide') : t('ev_second_show')}
            </button>
          </div>

          {secondMode ? (
            <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 12 }}>
              <h3 style={{ fontSize: 14, marginBottom: 8 }}>{t('ev_second_title')}</h3>
              <p className="small muted" style={{ marginBottom: 10 }}>
                {t('ev_second_sub')}
              </p>
              {data.rows
                .filter((row) => row.kind === 'rubric')
                .map((row) => (
                  <div
                    key={`second-${row.code}`}
                    className="mgr-score-row"
                    style={{ gridTemplateColumns: '48px 1fr 130px 90px 80px' }}
                  >
                    <span className="mono muted">{row.code}</span>
                    <span>{locale === 'az' ? row.name_az : row.name_en}</span>
                    <span>
                      <label className="mgr-sr-only" htmlFor={`second-${row.code}`}>
                        {t('ev_second_title')} {row.code}
                      </label>
                      <input
                        id={`second-${row.code}`}
                        type="number"
                        min={0}
                        max={3}
                        step={1}
                        inputMode="numeric"
                        value={secondRubric[row.code] ?? ''}
                        onChange={(event) => handleSecondCellChange(row.code, event.target.value)}
                      />
                    </span>
                    <span />
                    <span />
                  </div>
                ))}
              <button
                type="button"
                className="mgr-btn mgr-btn-primary mgr-btn-sm"
                style={{ marginTop: 10 }}
                onClick={() => secondSave.mutate()}
                disabled={secondSave.isPending}
              >
                {t('ev_second_save')}
              </button>
              {secondSave.isError ? (
                <div className="mgr-alert mgr-alert-crit" style={{ marginTop: 10 }}>
                  {errorMessage(secondSave.error)}
                </div>
              ) : null}
              {secondSave.data ? (
                <div style={{ marginTop: 10 }}>
                  {secondSave.data.divergences.length === 0 ? (
                    <div className="mgr-alert mgr-alert-good">{t('ev_no_divergence')}</div>
                  ) : (
                    <div className="mgr-alert mgr-alert-warn">
                      {t('ev_divergence')}:{' '}
                      {secondSave.data.divergences
                        .map((d) => `${d.code} (${d.first} → ${d.second})`)
                        .join(', ')}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card title={t('ev_decision')}>
            <div className="mgr-bars">
              {Object.entries(computed.groups).map(([group, points]) => (
                <div className="mgr-b" key={group}>
                  <span>{group}</span>
                  <div className="mgr-bar">
                    <i style={{ width: `${Math.min(100, (points / 25) * 100)}%` }} />
                  </div>
                  <span className="mono" style={{ textAlign: 'right' }}>
                    {points}
                  </span>
                </div>
              ))}
            </div>
            <div className={`mgr-alert ${computed.ko ? 'mgr-alert-good' : 'mgr-alert-crit'}`} style={{ marginTop: 14 }}>
              {computed.ko ? (
                <>
                  {t('ko_pass')} · <ClassPill cls={computed.cls} />{' '}
                  <b className="mono">
                    {computed.total}
                    {t('of100')}
                  </b>
                </>
              ) : (
                t('ko_fail')
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
              <button
                type="button"
                className="mgr-btn mgr-btn-good"
                disabled={!canApprove || decide.isPending}
                onClick={() => decide.mutate({ decision: 'approve' })}
              >
                {t('ev_approve')}
              </button>
              <button
                type="button"
                className="mgr-btn"
                disabled={decide.isPending}
                onClick={() => openDecision('request_info')}
              >
                {t('ev_info')}
              </button>
              <button
                type="button"
                className="mgr-btn mgr-btn-crit"
                disabled={decide.isPending}
                onClick={() => openDecision('reject')}
              >
                {t('ev_reject')}
              </button>
            </div>
            {decide.isError ? (
              <div className="mgr-alert mgr-alert-crit" style={{ marginTop: 10 }}>
                {errorMessage(decide.error)}
              </div>
            ) : null}
            {decisionOpen ? (
              <form onSubmit={submitDecision} style={{ marginTop: 12 }}>
                <div className="field">
                  <label htmlFor="justification">{t('ev_justification')}</label>
                  <textarea
                    id="justification"
                    required
                    minLength={3}
                    rows={3}
                    value={justification}
                    onChange={(event) => setJustification(event.target.value)}
                  />
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button type="submit" className="mgr-btn mgr-btn-primary" disabled={decide.isPending}>
                    {decisionOpen === 'reject' ? t('ev_reject') : t('ev_info')}
                  </button>
                  <button type="button" className="mgr-btn" onClick={() => setDecisionOpen(null)}>
                    {t('mgr_cancel')}
                  </button>
                </div>
              </form>
            ) : null}
          </Card>

          <Card title={t('mo_classes')}>
            <table className="mgr-table">
              <tbody>
                <tr>
                  <td>
                    <ClassPill cls="A" />
                  </td>
                  <td>90–100</td>
                </tr>
                <tr>
                  <td>
                    <ClassPill cls="B" />
                  </td>
                  <td>80–89</td>
                </tr>
                <tr>
                  <td>
                    <ClassPill cls="C" />
                  </td>
                  <td>70–79</td>
                </tr>
                <tr>
                  <td>
                    <ClassPill cls="D" />
                  </td>
                  <td>60–69</td>
                </tr>
                <tr>
                  <td>
                    <ClassPill cls="F" />
                  </td>
                  <td>0–59</td>
                </tr>
                <tr>
                  <td>
                    <ClassPill cls="KO" />
                  </td>
                  <td className="small muted">{t('mo_ko')}</td>
                </tr>
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </>
  );
}

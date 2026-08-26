import { useLocale } from '../../i18n/LocaleProvider';

type MatchState = 'go' | 'cond' | 'nogo';

const CLASS_BY_STATE: Record<MatchState, string> = {
  go: 'viq-pill viq-pill-go',
  cond: 'viq-pill viq-pill-cond',
  nogo: 'viq-pill viq-pill-nogo',
};

/**
 * The go/no-go badge — every screen that shows a state uses this, so the rule "text always
 * carries the state, colour is never the only channel" (accessibility, brief §2C) lives in
 * one place. `t(state)` already resolves to the shared `go`/`cond`/`nogo` labels the
 * prototype approved (`docs/design/app.js`).
 */
export function StatePill({ state }: { state: MatchState | null | undefined }) {
  const { t } = useLocale();
  if (!state) return <span className="viq-pill viq-pill-neutral">{t('none')}</span>;
  return <span className={CLASS_BY_STATE[state]}>{t(state)}</span>;
}

/** The class band badge (A–F, KO) — a fixed vocabulary, not translated. */
export function ClassBadge({ cls }: { cls: string | null | undefined }) {
  if (!cls) return <span className="viq-mono">—</span>;
  return <span className="viq-class">{cls}</span>;
}

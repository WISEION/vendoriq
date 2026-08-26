import { useId, useState } from 'react';
import type { ChangeEvent, ReactNode } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';
import type { FieldRow } from './fieldCatalog';

/**
 * One answer cell of the application form — code, question, format, control, evidence
 * document. Saves on blur (and on select change, since a `<select>` has no meaningful
 * "still typing" state), never on every keystroke: the interaction is the save trigger, not
 * an effect watching the draft (react-best-practices `rerender-move-effect-to-event`).
 *
 * `key={row.code}` on the caller's side is what resets the draft when the vendor switches
 * rows or tabs — no `useEffect` re-syncs a prop into state here.
 */
export function AnswerControl({
  row,
  value,
  computedValue,
  disabled,
  onSave,
}: {
  row: FieldRow;
  value: unknown;
  computedValue?: number | null;
  disabled: boolean;
  onSave: (code: string, value: unknown) => void;
}) {
  const { t, locale } = useLocale();
  const id = useId();
  const question = locale === 'az' ? row.az : row.en;
  const [draft, setDraft] = useState(() => toInputValue(row, value));
  const [saved, setSaved] = useState(false);

  const commit = (next: string) => {
    setSaved(false);
    if (next === toInputValue(row, value)) return;
    onSave(row.code, next === '' ? null : fromInputValue(row, next));
    setSaved(true);
  };

  const label = (
    <label htmlFor={id} className="vp-row-label">
      {renderQuestion(question)}
    </label>
  );

  const format =
    row.type === 'yn'
      ? `${t('va_yes')}/${t('va_no')}`
      : row.type === 'calc'
        ? t('va_auto')
        : row.type;

  let control: ReactNode;
  if (row.type === 'calc') {
    control = (
      <input
        id={id}
        type="text"
        value={computedValue == null ? '' : formatNumber(computedValue)}
        disabled
        readOnly
        aria-label={question}
      />
    );
  } else if (row.type === 'yn') {
    control = (
      <select
        id={id}
        value={draft}
        disabled={disabled}
        aria-label={question}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => {
          setDraft(event.target.value);
          commit(event.target.value);
        }}
      >
        <option value=""></option>
        <option value="y">{t('va_yes')}</option>
        <option value="n">{t('va_no')}</option>
      </select>
    );
  } else {
    control = (
      <input
        id={id}
        type={row.type === 'number' ? 'number' : row.type === 'date' ? 'date' : 'text'}
        value={draft}
        disabled={disabled}
        aria-label={question}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={(event) => commit(event.target.value)}
      />
    );
  }

  return (
    <div className="vp-row">
      <span className="mono muted vp-row-format">{row.code}</span>
      {label}
      <span className="vp-row-format">{format}</span>
      {control}
      <span className="mono vp-row-doc">{row.doc ?? '—'}</span>
      {saved ? (
        <span className="vp-sr-only" role="status">
          {t('vp_saved')}
        </span>
      ) : null}
    </div>
  );
}

function renderQuestion(question: string) {
  if (!question.includes('⚠')) return question;
  const [text, marker] = question.split('⚠');
  return (
    <>
      {text}
      <span className="vp-row-req"> ⚠{marker}</span>
    </>
  );
}

function toInputValue(row: FieldRow, value: unknown): string {
  if (value == null) return '';
  if (row.type === 'yn') {
    // Any prior stored token derive_raw reads as "yes" round-trips to the canonical "y".
    const text = String(value).trim().toLowerCase();
    if (['y', 'yes', 'var', 'bəli', 'true', '1'].includes(text)) return 'y';
    if (['n', 'no', 'yoxdur', 'xeyr', 'false', '0'].includes(text)) return 'n';
    return '';
  }
  return String(value);
}

function fromInputValue(row: FieldRow, text: string): string | number {
  if (row.type === 'number') {
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : text;
  }
  return text;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
}

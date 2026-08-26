/**
 * The pieces every integration screen repeats: a status pill, a timestamp, a bilingual
 * warning row, an empty state.
 *
 * Display only. A pill's *tone* is chosen from the status the API already decided; nothing
 * here derives a status, a count or an eligibility (brief §2, gate 2).
 */
import type { ReactNode } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';
import type { AnyWarning } from './queries';

export type Tone = 'good' | 'warn' | 'crit' | 'mute';

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className="iq-pill" data-tone={tone}>
      {children}
    </span>
  );
}

/** Maps the contract's `Adapter.status` and `SyncResult` onto a tone. Presentation only. */
export const STATUS_TONE: Record<string, Tone> = {
  active: 'good',
  needs_configuration: 'warn',
  planned: 'mute',
  success: 'good',
  partial: 'warn',
  failed: 'crit',
};

/** A locale-aware absolute timestamp; an unknown time renders as an em dash, never as "now". */
export function useTimestamp(): (value: string | null | undefined) => string {
  const { locale } = useLocale();
  return (value) => {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleString(locale === 'az' ? 'az-AZ' : 'en-GB', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  };
}

export function EmptyRow({ columns, text }: { columns: number; text: string }) {
  return (
    <tr>
      <td className="iq-empty" colSpan={columns}>
        {text}
      </td>
    </tr>
  );
}

/**
 * One anomaly from the importer or from an adapter run. The message is not translated here:
 * the parser writes both languages and the officer reads the one they are in, so the wording
 * on screen is the wording in the sync log and in the audit trail.
 */
export function WarningRow({ warning }: { warning: AnyWarning }) {
  const { locale } = useLocale();
  const { severity } = warning;
  const message = locale === 'az' ? warning.message_az : warning.message_en;
  return (
    <div className="iq-warning" data-severity={severity}>
      <code>{warning.code}</code>
      <div>
        {message}
        {'sheet' in warning && (warning.sheet || warning.cell) ? (
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {[warning.sheet, warning.cell].filter(Boolean).join(' · ')}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  const { t } = useLocale();
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p className="form-error" role="alert">
      {t('in_failed')}: {message}
    </p>
  );
}

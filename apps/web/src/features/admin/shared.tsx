/**
 * Pieces every admin screen (31–34) reuses: error rendering, an empty-table row, a
 * locale-aware timestamp, and a flattener for an audit event's `before`/`after` image.
 *
 * Display only — nothing here decides who may do what. A screen checks its own action
 * against `permissions` from `GET /api/auth/me` (`useSession().session.principal.permissions`);
 * this module never repeats the server's role matrix (brief §2, gate 2).
 */
import type { ReactNode } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';
import { ApiError } from '../../api/client';

export function ErrorText({ error }: { error: unknown }) {
  const { t } = useLocale();
  if (!error) return null;
  const key = error instanceof ApiError ? `err_${error.code}` : 'err_internal_error';
  return (
    <p className="form-error" role="alert">
      {t(key)}
    </p>
  );
}

export function EmptyRow({ columns, text }: { columns: number; text: string }) {
  return (
    <tr>
      <td className="adm-empty" colSpan={columns}>
        {text}
      </td>
    </tr>
  );
}

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

/**
 * One `key: value` line per changed field — the on-screen equivalent of the export's own
 * flattening (`services/audit_export.py` `_flatten`), so a reader never has to parse a raw
 * JSON blob to see what changed.
 */
export function flattenAuditImage(value: Record<string, unknown> | null | undefined): string[] {
  function walk(input: unknown, prefix: string): string[] {
    if (input === null || input === undefined) return [];
    if (typeof input === 'object' && !Array.isArray(input)) {
      return Object.entries(input as Record<string, unknown>).flatMap(([key, item]) =>
        walk(item, prefix ? `${prefix}.${key}` : key),
      );
    }
    if (Array.isArray(input)) {
      const rendered = input.map((item) => String(item)).join(', ');
      return [prefix ? `${prefix}: [${rendered}]` : `[${rendered}]`];
    }
    return [prefix ? `${prefix}: ${String(input)}` : String(input)];
  }
  return walk(value ?? null, '');
}

export function AuditImage({ value }: { value: Record<string, unknown> | null | undefined }) {
  const lines = flattenAuditImage(value);
  if (lines.length === 0) return <span className="muted">—</span>;
  return (
    <ul className="adm-image">
      {lines.map((line, index) => (
        <li key={`${index}-${line}`}>{line}</li>
      ))}
    </ul>
  );
}

export function Card({
  title,
  note,
  children,
  actions,
}: {
  title: string;
  note?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="adm-card">
      <div className="adm-card-head">
        <div>
          <h3 className="adm-card-title">{title}</h3>
          {note ? <p className="adm-note">{note}</p> : null}
        </div>
        {actions ? <div className="adm-actions">{actions}</div> : null}
      </div>
      <div className="adm-card-body">{children}</div>
    </section>
  );
}

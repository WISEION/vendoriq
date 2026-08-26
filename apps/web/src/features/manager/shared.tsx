/**
 * Small pieces every manager screen reuses: the class/status pills already in the shared
 * dictionary, and the two formatters the prototype's own `fmt()`/date columns use. Nothing
 * here computes a score or a decision — nothing here is even allowed to: nothing imports
 * `vendoriq_scoring` or repeats a threshold, because that stays server-side (brief §2).
 */
import type { ReactNode } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';

/**
 * Nested-screen addresses (`docs/SCREENS.md` — vendor detail, evaluation, commission
 * summary have no rail entry and are not yet in the typed route tree `routes.tsx` builds
 * from `PAGE_TEXT`). `<Link to>` only accepts the tree's own literal union, so every target
 * here is built as a plain, already-widened `string` — exactly how `Rail.tsx` passes
 * `NavItem.path` — rather than a template-literal expression `Link` would reject outright.
 */
export const VENDORS_PATH: string = '/vendors';
export const APPLICATIONS_PATH: string = '/applications';
export function vendorPath(vendorId: string): string {
  return `/vendors/${vendorId}`;
}
export function applicationPath(applicationId: string): string {
  return `/applications/${applicationId}`;
}
export function commissionSummaryPath(applicationId: string): string {
  return `/applications/${applicationId}/summary`;
}

export type ScoreClass = 'A' | 'B' | 'C' | 'D' | 'F' | 'KO';

/** The class badge — colour comes from `--c<class>` in theme/tokens.css. */
export function ClassPill({ cls }: { cls: ScoreClass | null | undefined }) {
  const label = cls ?? 'NA';
  return <span className={`mgr-cls mgr-cls-${label}`}>{label}</span>;
}

const STATUS_KEY: Record<string, string> = {
  registered: 'st_registered',
  invited: 'step_inv',
  in_progress: 'st_incomplete',
  submitted: 'step_sub',
  under_review: 'st_under_review',
  information_requested: 'k_needs',
  prequalified: 'st_prequalified',
  rejected: 'st_rejected',
  suspended: 'st_rejected',
  withdrawn: 'st_rejected',
};

const STATUS_TONE: Record<string, 'good' | 'warn' | 'crit' | 'neutral' | 'accent'> = {
  registered: 'neutral',
  invited: 'accent',
  in_progress: 'warn',
  submitted: 'accent',
  under_review: 'accent',
  information_requested: 'warn',
  prequalified: 'good',
  rejected: 'crit',
  suspended: 'crit',
  withdrawn: 'neutral',
};

/** Status badge for a vendor or an application status value. */
export function StatusPill({ status }: { status: string }) {
  const { t } = useLocale();
  const tone = STATUS_TONE[status] ?? 'neutral';
  const key = STATUS_KEY[status] ?? status;
  return <span className={`mgr-pill mgr-pill-${tone}`}>{t(key)}</span>;
}

/** `1 234 567` — AZN amounts throughout are stored and shown without decimals (spec §16). */
export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US').format(Math.round(value)).replace(/,/g, ' ');
}

/** `YYYY-MM-DD`, the format every screenshot in the prototype uses. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.slice(0, 10);
}

export function Bar({
  value,
  max,
  tone = 'accent',
}: {
  value: number;
  max: number;
  tone?: 'accent' | 'good' | 'warn' | 'crit';
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const cls = tone === 'accent' ? 'mgr-bar' : `mgr-bar mgr-bar-${tone}`;
  return (
    <div className={cls}>
      <i style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Card({
  title,
  right,
  children,
  bodyClassName,
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <div className="mgr-card">
      {title ? (
        <div className="mgr-card-hd">
          <h2>{title}</h2>
          {right}
        </div>
      ) : null}
      <div className={bodyClassName ? `mgr-card-bd ${bodyClassName}` : 'mgr-card-bd'}>
        {children}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="mgr-empty">{children}</div>;
}

export function LoadingCard() {
  const { t } = useLocale();
  return <div className="mgr-empty">{t('mgr_loading')}</div>;
}

export function ErrorCard({ message }: { message: string }) {
  return <div className="mgr-alert mgr-alert-crit">{message}</div>;
}

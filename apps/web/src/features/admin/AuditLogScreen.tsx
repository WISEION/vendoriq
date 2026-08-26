/**
 * Screen 34 — `/admin/audit` (`docs/SCREENS.md`). Filterable, with the Excel export — spec
 * §13: "immutable log of every status change, score edit, decision and integration write;
 * exportable for committee minutes".
 *
 * Immutable means this screen offers nothing that suggests editing: no row click, no inline
 * form, no delete. `before`/`after` are rendered as the same flattened `key: value` lines the
 * xlsx export uses (`AuditImage`, `shared.tsx`) rather than a raw JSON blob, for the same
 * reason the export avoids one — a reader should not have to parse a cell to see what changed.
 *
 * The export takes only `from`/`to`/`locale` (`docs/openapi.yaml` `exportAuditLog`) — a
 * narrower parameter set than this screen's own table filters (`listAuditEvents` also takes
 * `actor_id`/`entity_type`/`entity_id`/`action`). The note under the export button says so,
 * rather than letting a manager believe the file matches every filter on screen.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import type { Locale } from '../../i18n/LocaleProvider';
import { useSession } from '../../auth/SessionProvider';
import { AuditImage, Card, EmptyRow, ErrorText, useTimestamp } from './shared';
import { auditQuery, downloadBlob, useExportAuditLog, usersQuery } from './queries';
import './admin.css';

const PAGE_SIZE = 25;

export function AuditLogScreen() {
  const { t, locale } = useLocale();
  const stamp = useTimestamp();
  const { session } = useSession();
  const canExport =
    session.status === 'authenticated' && session.principal.permissions.includes('exportAuditLog');

  const [actorId, setActorId] = useState('');
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);

  const { session } = useSession();
  const permissions =
    session.status === 'authenticated' ? (session.principal.permissions ?? []) : [];

  const query = {
    page,
    page_size: PAGE_SIZE,
    ...(actorId ? { actor_id: actorId } : {}),
    ...(entityType ? { entity_type: entityType } : {}),
    ...(action ? { action } : {}),
    ...(from ? { from } : {}),
    ...(to ? { to } : {}),
  };
  const events = useQuery(auditQuery(query));
  // Gated on the caller's own permission list, not on a role (ADR-013). `listAuditEvents`
  // admits a manager and `listUsers` does not, so this screen — which a manager may open —
  // was firing a request every manager gets a 403 for, leaving the actor filter silently
  // empty with no indication why (3A, finding 5). Enabled, the dropdown works; disabled, it
  // says the filter needs the user directory rather than pretending nobody has ever acted.
  const canListUsers = permissions.includes('listUsers');
  const actors = useQuery({ ...usersQuery({ page_size: 200 }), enabled: canListUsers });
  const exportMutation = useExportAuditLog();

  const totalPages = events.data ? Math.max(1, Math.ceil(events.data.total / PAGE_SIZE)) : 1;

  const handleExport = () => {
    exportMutation.mutate(
      { ...(from ? { from } : {}), ...(to ? { to } : {}), locale: locale as Locale },
      { onSuccess: (blob) => downloadBlob(blob, 'audit-log.xlsx') },
    );
  };

  return (
    <div>
      <div className="page-head">
        <h2>{t('adm_audit_title')}</h2>
      </div>
      <p className="adm-note">{t('adm_audit_sub')}</p>

      <div className="adm-toolbar">
        <select
          aria-label={t('adm_filter_actor')}
          value={actorId}
          disabled={!canListUsers}
          title={canListUsers ? undefined : t('adm_actor_needs_users')}
          onChange={(event) => {
            setActorId(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{canListUsers ? t('adm_all_actors') : t('adm_actor_needs_users')}</option>
          {(actors.data?.items ?? []).map((user) => (
            <option key={user.id} value={user.id}>
              {user.email}
            </option>
          ))}
        </select>
        <input
          className="adm-search"
          placeholder={t('adm_filter_entity_type')}
          value={entityType}
          onChange={(event) => {
            setEntityType(event.target.value);
            setPage(1);
          }}
        />
        <input
          className="adm-search"
          placeholder={t('adm_filter_action')}
          value={action}
          onChange={(event) => {
            setAction(event.target.value);
            setPage(1);
          }}
        />
        <label className="adm-inline-field">
          {t('adm_from')}
          <input
            type="date"
            value={from}
            onChange={(event) => {
              setFrom(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <label className="adm-inline-field">
          {t('adm_to')}
          <input
            type="date"
            value={to}
            onChange={(event) => {
              setTo(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <div className="adm-toolbar-spacer" />
        {canExport ? (
          <button
            type="button"
            className="btn-secondary"
            disabled={exportMutation.isPending}
            onClick={handleExport}
          >
            {exportMutation.isPending ? `${t('adm_export')}…` : t('adm_export')}
          </button>
        ) : null}
      </div>
      {canExport ? <p className="adm-note">{t('adm_export_note')}</p> : null}
      <ErrorText error={exportMutation.error} />

      <Card title={t('adm_audit_title')}>
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th scope="col">{t('adm_col_timestamp')}</th>
                <th scope="col">{t('adm_col_actor')}</th>
                <th scope="col">{t('adm_col_action')}</th>
                <th scope="col">{t('adm_col_entity')}</th>
                <th scope="col">{t('adm_col_before')}</th>
                <th scope="col">{t('adm_col_after')}</th>
              </tr>
            </thead>
            <tbody>
              {(events.data?.items ?? []).map((event) => (
                <tr key={event.id}>
                  <td className="adm-nowrap">{stamp(event.created_at)}</td>
                  <td>{event.actor_email ?? t('adm_system')}</td>
                  <td className="mono">{event.action}</td>
                  <td>
                    {event.entity_type}
                    {event.entity_id ? (
                      <div className="muted adm-entity-id">{event.entity_id}</div>
                    ) : null}
                  </td>
                  <td>
                    <AuditImage value={event.before} />
                  </td>
                  <td>
                    <AuditImage value={event.after} />
                  </td>
                </tr>
              ))}
              {events.data && events.data.items.length === 0 ? (
                <EmptyRow columns={6} text={t('adm_audit_empty')} />
              ) : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={events.error} />
        {events.data && events.data.total > PAGE_SIZE ? (
          <nav className="adm-pager" aria-label={t('adm_pagination')}>
            <button
              type="button"
              className="btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((current) => current - 1)}
            >
              {t('adm_prev')}
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className="btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => current + 1)}
            >
              {t('adm_next')}
            </button>
          </nav>
        ) : null}
      </Card>
    </div>
  );
}

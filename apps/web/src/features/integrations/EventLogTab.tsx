/**
 * Screen 28, fourth tab: the domain event log.
 *
 * The same stream webhooks deliver. A future product that would rather poll than subscribe
 * reads `GET /events` with an API key and a `since` cursor; this tab is that endpoint with a
 * table around it, so what an integrator will see is visible to the officer too.
 */
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { EmptyRow, ErrorText, useTimestamp } from './shared';
import { eventLogQuery } from './queries';

export function EventLogTab() {
  const { t } = useLocale();
  const stamp = useTimestamp();
  const events = useQuery(eventLogQuery);

  return (
    <section className="card">
      <h3 className="iq-section-title">{t('in_event_log')}</h3>
      <p className="iq-note">{t('in_event_log_note')}</p>
      <div className="iq-table-wrap">
        <table className="iq-table">
          <thead>
            <tr>
              <th>{t('in_col_when')}</th>
              <th>{t('in_col_event')}</th>
              <th>{t('in_col_entity')}</th>
              <th>{t('in_col_payload')}</th>
            </tr>
          </thead>
          <tbody>
            {(events.data?.items ?? []).map((event) => (
              <tr key={event.id}>
                <td>{stamp(event.created_at)}</td>
                <td className="mono">{event.type}</td>
                <td className="mono" style={{ fontSize: 11 }}>
                  {event.entity_type}
                  {event.entity_id ? ` · ${event.entity_id.slice(0, 8)}` : ''}
                </td>
                <td className="mono" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                  {JSON.stringify(event.payload)}
                </td>
              </tr>
            ))}
            {events.data && events.data.items.length === 0 ? (
              <EmptyRow columns={4} text={t('in_no_events')} />
            ) : null}
          </tbody>
        </table>
      </div>
      <ErrorText error={events.error} />
    </section>
  );
}

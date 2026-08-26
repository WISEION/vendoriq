/**
 * Screen 28, first tab: every adapter with its status, what it has written and when it last
 * ran, plus the "run now" action and the recent sync history.
 *
 * The registry row is the one worth looking at: it is listed, it says `planned`, and running
 * it answers 409 with the adapter's own explanation. That refusal is deliberate — registry is
 * the highest-trust source in the system (spec §6.6) and a fabricated tax-clearance pass
 * would knock out or admit a vendor with nothing behind it.
 */
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { EmptyRow, ErrorText, Pill, STATUS_TONE, useTimestamp, WarningRow } from './shared';
import { adaptersQuery, syncLogQuery, useRunSync } from './queries';
import type { Adapter } from './queries';

const CONFIGURABLE = new Set(['generic_rest', 'csv', 'erp_1c', 'erp_sap', 'erp_odoo']);

export function AdaptersTab() {
  const { t, locale } = useLocale();
  const stamp = useTimestamp();
  const adapters = useQuery(adaptersQuery);
  const runs = useQuery(syncLogQuery());
  const run = useRunSync();

  const name = (adapter: Adapter) => (locale === 'az' ? adapter.name_az : adapter.name_en);
  const description = (adapter: Adapter) =>
    locale === 'az' ? adapter.description_az : adapter.description_en;

  return (
    <div className="iq-stack">
      <section className="card">
        <h3 className="iq-section-title">{t('in_adapters')}</h3>
        <p className="iq-note">{t('in_adapters_note')}</p>
        <div className="iq-table-wrap">
          <table className="iq-table">
            <thead>
              <tr>
                <th>{t('in_col_adapter')}</th>
                <th>{t('in_col_status')}</th>
                <th className="iq-num">{t('in_col_records')}</th>
                <th className="iq-num">{t('in_col_vendors')}</th>
                <th>{t('in_col_last_sync')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(adapters.data ?? []).map((adapter) => (
                <tr key={adapter.key}>
                  <td>
                    <strong>{name(adapter)}</strong>
                    <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                      {description(adapter)}
                    </div>
                  </td>
                  <td>
                    <Pill tone={STATUS_TONE[adapter.status ?? 'planned'] ?? 'mute'}>
                      {t(`in_status_${adapter.status}`)}
                    </Pill>
                  </td>
                  <td className="iq-num">{adapter.record_count ?? 0}</td>
                  <td className="iq-num">{adapter.configured_vendor_count ?? 0}</td>
                  <td>{stamp(adapter.last_sync_at)}</td>
                  <td>
                    <div className="iq-actions">
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={run.isPending}
                        onClick={() => run.mutate({ adapter: adapter.key as string })}
                      >
                        {t('in_run_now')}
                      </button>
                      {CONFIGURABLE.has(adapter.key as string) ? (
                        <Link
                          className="btn-link"
                          to={`/integrations/adapters/${adapter.key}` as string}
                        >
                          {t('in_configure')}
                        </Link>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {adapters.data?.length === 0 ? (
                <EmptyRow columns={6} text={t('in_no_adapters')} />
              ) : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={run.error ?? adapters.error} />
        {run.data ? (
          <div style={{ marginTop: 12 }}>
            <Pill tone={STATUS_TONE[run.data.result ?? 'failed'] ?? 'mute'}>
              {t(`in_result_${run.data.result}`)}
            </Pill>{' '}
            <span className="muted">
              {t('in_fields_written')}: {run.data.fields_written}
            </span>
            <div style={{ marginTop: 8 }}>
              {(run.data.warnings ?? []).map((warning, index) => (
                <WarningRow key={`${warning.code}-${index}`} warning={warning} />
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="card">
        <h3 className="iq-section-title">{t('in_sync_log')}</h3>
        <p className="iq-note">{t('in_sync_log_note')}</p>
        <div className="iq-table-wrap">
          <table className="iq-table">
            <thead>
              <tr>
                <th>{t('in_col_started')}</th>
                <th>{t('in_col_adapter')}</th>
                <th>{t('in_col_vendor')}</th>
                <th className="iq-num">{t('in_col_records')}</th>
                <th>{t('in_col_result')}</th>
                <th className="iq-num">{t('in_col_warnings')}</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.items ?? []).map((entry) => (
                <tr key={entry.id}>
                  <td>{stamp(entry.started_at)}</td>
                  <td className="mono">{entry.adapter}</td>
                  <td>{entry.vendor_name ?? '—'}</td>
                  <td className="iq-num">{entry.fields_written}</td>
                  <td>
                    <Pill tone={STATUS_TONE[entry.result ?? 'failed'] ?? 'mute'}>
                      {t(`in_result_${entry.result}`)}
                    </Pill>
                  </td>
                  <td className="iq-num">{entry.warnings?.length ?? 0}</td>
                </tr>
              ))}
              {runs.data && runs.data.items.length === 0 ? (
                <EmptyRow columns={6} text={t('in_no_runs')} />
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

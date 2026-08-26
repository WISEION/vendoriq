/**
 * Screen 30 — `/integrations/adapters/$adapter`. One connector, configured per vendor.
 *
 * The secret field is write-only. The API returns `secret_masked` and never the credential;
 * leaving the field untouched sends the mask back, which the server reads as "keep what is
 * stored" (contract). Clearing it deliberately clears the stored secret. There is no path
 * through this screen — or through the API — that reveals a configured credential.
 *
 * The field map is `remote path → VendorIQ field code`. That is the whole difference between
 * one ERP family and another: the code below is identical for 1C, SAP, Odoo and the generic
 * REST contract, exactly as the adapter classes are.
 */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { ErrorText, Pill, STATUS_TONE, WarningRow } from './shared';
import {
  adapterConfigQuery,
  adaptersQuery,
  useRunSync,
  useSaveAdapterConfig,
  vendorPickerQuery,
} from './queries';
import './integrations.css';

type AuthType = 'none' | 'basic' | 'bearer' | 'api_key';

interface MapRow {
  remote: string;
  code: string;
}

const AUTH_TYPES: readonly AuthType[] = ['none', 'basic', 'bearer', 'api_key'];

export function ErpConnector({ adapter }: { adapter: string }) {
  const { t, locale } = useLocale();
  const adapters = useQuery(adaptersQuery);
  const vendors = useQuery(vendorPickerQuery);
  const save = useSaveAdapterConfig();
  const run = useRunSync();

  const [vendorId, setVendorId] = useState('');
  const config = useQuery(adapterConfigQuery(adapter, vendorId || null));

  const [isEnabled, setIsEnabled] = useState(false);
  const [baseUrl, setBaseUrl] = useState('');
  const [authType, setAuthType] = useState<AuthType>('none');
  const [username, setUsername] = useState('');
  const [secret, setSecret] = useState('');
  const [schedule, setSchedule] = useState('');
  const [rows, setRows] = useState<MapRow[]>([{ remote: '', code: '' }]);

  // The form mirrors the stored configuration whenever a different vendor is selected.
  useEffect(() => {
    const stored = config.data;
    if (!stored) return;
    setIsEnabled(Boolean(stored.is_enabled));
    setBaseUrl(stored.base_url ?? '');
    setAuthType((stored.auth_type ?? 'none') as AuthType);
    setUsername(stored.username ?? '');
    setSecret(stored.secret_masked ?? '');
    setSchedule(stored.schedule_cron ?? '');
    const entries = Object.entries(stored.field_map ?? {});
    setRows(
      entries.length
        ? entries.map(([remote, code]) => ({ remote, code }))
        : [{ remote: '', code: '' }],
    );
  }, [config.data]);

  const meta = (adapters.data ?? []).find((item) => item.key === adapter);

  const submit = () => {
    if (!vendorId) return;
    const fieldMap: Record<string, string> = {};
    for (const row of rows) {
      if (row.remote.trim() && row.code.trim()) fieldMap[row.remote.trim()] = row.code.trim();
    }
    save.reset();
    save.mutate({
      adapter,
      vendorId,
      body: {
        is_enabled: isEnabled,
        base_url: baseUrl,
        auth_type: authType,
        username,
        secret,
        field_map: fieldMap,
        schedule_cron: schedule,
      },
    });
  };

  return (
    <div className="iq-stack">
      <section className="card">
        <h3 className="iq-section-title">
          {meta ? (locale === 'az' ? meta.name_az : meta.name_en) : adapter}
        </h3>
        <p className="iq-note">
          {meta ? (locale === 'az' ? meta.description_az : meta.description_en) : ''}
        </p>
        {meta ? (
          <Pill tone={STATUS_TONE[meta.status ?? 'planned'] ?? 'mute'}>
            {t(`in_status_${meta.status}`)}
          </Pill>
        ) : null}
      </section>

      <section className="card">
        <h3 className="iq-section-title">{t('in_connector_config')}</h3>
        <div className="iq-toolbar">
          <label className="iq-inline-field" style={{ minWidth: 260 }}>
            <span>{t('in_vendor')}</span>
            <select value={vendorId} onChange={(event) => setVendorId(event.target.value)}>
              <option value="">{t('in_pick_vendor')}</option>
              {(vendors.data?.items ?? []).map((vendor) => (
                <option key={vendor.id} value={vendor.id}>
                  {vendor.legal_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {vendorId ? (
          <div className="iq-stack">
            <label className="iq-inline-field" style={{ maxWidth: 240 }}>
              <span>{t('in_enabled')}</span>
              <span>
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={(event) => setIsEnabled(event.target.checked)}
                />
              </span>
            </label>
            <label className="iq-inline-field" style={{ maxWidth: 560 }}>
              <span>{t('in_base_url')}</span>
              <input
                type="url"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="https://erp.example/api/vendors/{vendor}"
              />
            </label>
            <div className="iq-toolbar">
              <label className="iq-inline-field">
                <span>{t('in_auth_type')}</span>
                <select
                  value={authType}
                  onChange={(event) => setAuthType(event.target.value as AuthType)}
                >
                  {AUTH_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="iq-inline-field">
                <span>{t('in_username')}</span>
                <input value={username} onChange={(event) => setUsername(event.target.value)} />
              </label>
              <label className="iq-inline-field">
                <span>{t('in_secret')}</span>
                <input
                  type="password"
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <label className="iq-inline-field">
                <span>{t('in_schedule')}</span>
                <input
                  value={schedule}
                  onChange={(event) => setSchedule(event.target.value)}
                  placeholder="0 3 1 * *"
                />
              </label>
            </div>
            <p className="iq-note">{t('in_secret_note')}</p>

            <div>
              <div className="iq-inline-field">
                <span>{t('in_field_map')}</span>
              </div>
              <p className="iq-note">{t('in_field_map_note')}</p>
              {rows.map((row, index) => (
                <div className="iq-map-row" key={index}>
                  <input
                    value={row.remote}
                    placeholder={t('in_remote_path')}
                    onChange={(event) =>
                      setRows((current) =>
                        current.map((item, position) =>
                          position === index ? { ...item, remote: event.target.value } : item,
                        ),
                      )
                    }
                  />
                  <span className="muted">→</span>
                  <input
                    value={row.code}
                    placeholder={t('in_field_code')}
                    onChange={(event) =>
                      setRows((current) =>
                        current.map((item, position) =>
                          position === index ? { ...item, code: event.target.value } : item,
                        ),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="btn-link"
                    onClick={() =>
                      setRows((current) =>
                        current.length === 1
                          ? [{ remote: '', code: '' }]
                          : current.filter((_, position) => position !== index),
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn-link"
                onClick={() => setRows((current) => [...current, { remote: '', code: '' }])}
              >
                {t('in_add_mapping')}
              </button>
            </div>

            <div className="iq-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={save.isPending}
                onClick={submit}
              >
                {t('in_save')}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={run.isPending}
                onClick={() => run.mutate({ adapter, vendorId })}
              >
                {t('in_run_now')}
              </button>
            </div>
            <ErrorText error={save.error ?? run.error ?? config.error} />
            {run.data ? (
              <div>
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
          </div>
        ) : (
          <p className="iq-empty">{t('in_pick_vendor')}</p>
        )}
      </section>
    </div>
  );
}

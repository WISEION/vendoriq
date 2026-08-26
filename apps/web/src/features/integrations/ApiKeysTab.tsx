/**
 * Screen 28, second tab: the credentials another product authenticates with.
 *
 * The key is displayed once, in the panel this screen shows immediately after creation, and
 * the API has no operation that could return it again — `ApiKey` in the contract carries no
 * key material at all. The copy field below is therefore the user's only chance to save it,
 * which is why the screen says so in both languages rather than assuming it is obvious.
 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { EmptyRow, ErrorText, Pill, useTimestamp } from './shared';
import { apiKeysQuery, SCOPES, useCreateApiKey, useRevokeApiKey } from './queries';
import type { ApiKeyCreated, Scope } from './queries';

export function ApiKeysTab() {
  const { t } = useLocale();
  const stamp = useTimestamp();
  const keys = useQuery(apiKeysQuery);
  const create = useCreateApiKey();
  const revoke = useRevokeApiKey();

  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<Scope[]>(['vendors:read']);
  const [issued, setIssued] = useState<ApiKeyCreated | null>(null);

  const toggle = (scope: Scope) =>
    setScopes((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope],
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.reset();
    create.mutate(
      { name, scopes },
      {
        onSuccess: (created) => {
          setIssued(created);
          setName('');
        },
      },
    );
  };

  return (
    <div className="iq-stack">
      {issued ? (
        <div className="card">
          <h3 className="iq-section-title">{t('in_key_once_title')}</h3>
          <p className="iq-note">{t('in_key_once_note')}</p>
          <div className="iq-secret">
            <code>{issued.key}</code>
          </div>
          <button type="button" className="btn-secondary" onClick={() => setIssued(null)}>
            {t('in_key_dismiss')}
          </button>
        </div>
      ) : null}

      <section className="card">
        <h3 className="iq-section-title">{t('in_new_key')}</h3>
        <form className="iq-stack" onSubmit={submit}>
          <label className="iq-inline-field" style={{ maxWidth: 360 }}>
            <span>{t('in_key_name')}</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={255}
            />
          </label>
          <div>
            <div className="iq-inline-field">
              <span>{t('in_key_scopes')}</span>
            </div>
            <div className="iq-scopes">
              {SCOPES.map((scope) => (
                <label key={scope}>
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope)}
                    onChange={() => toggle(scope)}
                  />
                  {scope}
                </label>
              ))}
            </div>
          </div>
          <div>
            <button
              type="submit"
              className="btn-primary"
              disabled={create.isPending || !name || scopes.length === 0}
            >
              {t('in_key_create')}
            </button>
          </div>
          <ErrorText error={create.error} />
        </form>
      </section>

      <section className="card">
        <h3 className="iq-section-title">{t('in_keys')}</h3>
        <div className="iq-table-wrap">
          <table className="iq-table">
            <thead>
              <tr>
                <th>{t('in_key_name')}</th>
                <th>{t('in_key_prefix')}</th>
                <th>{t('in_key_scopes')}</th>
                <th>{t('in_col_created')}</th>
                <th>{t('in_col_last_used')}</th>
                <th>{t('in_col_status')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(keys.data ?? []).map((key) => (
                <tr key={key.id}>
                  <td>{key.name}</td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {key.prefix ?? '—'}
                  </td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {(key.scopes ?? []).join(' ')}
                  </td>
                  <td>{stamp(key.created_at)}</td>
                  <td>{stamp(key.last_used_at)}</td>
                  <td>
                    <Pill tone={key.is_active ? 'good' : 'mute'}>
                      {key.is_active ? t('in_key_active') : t('in_key_revoked')}
                    </Pill>
                  </td>
                  <td>
                    {key.is_active ? (
                      <button
                        type="button"
                        className="btn-link"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate(key.id)}
                      >
                        {t('in_key_revoke')}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {keys.data?.length === 0 ? <EmptyRow columns={7} text={t('in_no_keys')} /> : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={keys.error ?? revoke.error} />
      </section>
    </div>
  );
}

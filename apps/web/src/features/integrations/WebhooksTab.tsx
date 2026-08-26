/**
 * Screen 28, third tab: outbound subscriptions.
 *
 * The signing secret is shown exactly once, for the same reason the API key is: after
 * creation there is no operation that returns it. "Send a test" posts a signed delivery
 * synchronously and reports the status the endpoint answered with, so a subscriber can be
 * verified before an event depends on it.
 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { EmptyRow, ErrorText, Pill, useTimestamp } from './shared';
import {
  EVENT_TYPES,
  useCreateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  webhooksQuery,
} from './queries';
import type { EventType, WebhookCreated, WebhookDelivery } from './queries';

export function WebhooksTab() {
  const { t } = useLocale();
  const stamp = useTimestamp();
  const webhooks = useQuery(webhooksQuery);
  const create = useCreateWebhook();
  const remove = useDeleteWebhook();
  const test = useTestWebhook();

  const [url, setUrl] = useState('');
  const [events, setEvents] = useState<EventType[]>(['vendor.prequalified']);
  const [issued, setIssued] = useState<WebhookCreated | null>(null);
  const [delivery, setDelivery] = useState<{ id: string; result: WebhookDelivery } | null>(null);

  const toggle = (event: EventType) =>
    setEvents((current) =>
      current.includes(event) ? current.filter((item) => item !== event) : [...current, event],
    );

  const submit = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    create.reset();
    create.mutate(
      { url, events, is_active: true },
      {
        onSuccess: (created) => {
          setIssued(created);
          setUrl('');
        },
      },
    );
  };

  return (
    <div className="iq-stack">
      {issued ? (
        <div className="card">
          <h3 className="iq-section-title">{t('in_secret_once_title')}</h3>
          <p className="iq-note">{t('in_secret_once_note')}</p>
          <div className="iq-secret">
            <code>{issued.secret}</code>
          </div>
          <button type="button" className="btn-secondary" onClick={() => setIssued(null)}>
            {t('in_key_dismiss')}
          </button>
        </div>
      ) : null}

      <section className="card">
        <h3 className="iq-section-title">{t('in_new_webhook')}</h3>
        <form className="iq-stack" onSubmit={submit}>
          <label className="iq-inline-field" style={{ maxWidth: 520 }}>
            <span>{t('in_webhook_url')}</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://"
              required
            />
          </label>
          <div>
            <div className="iq-inline-field">
              <span>{t('in_webhook_events')}</span>
            </div>
            <div className="iq-events">
              {EVENT_TYPES.map((event) => (
                <label key={event}>
                  <input
                    type="checkbox"
                    checked={events.includes(event)}
                    onChange={() => toggle(event)}
                  />
                  {event}
                </label>
              ))}
            </div>
          </div>
          <div>
            <button
              type="submit"
              className="btn-primary"
              disabled={create.isPending || !url || events.length === 0}
            >
              {t('in_webhook_create')}
            </button>
          </div>
          <ErrorText error={create.error} />
        </form>
      </section>

      <section className="card">
        <h3 className="iq-section-title">{t('in_webhooks')}</h3>
        <p className="iq-note">{t('in_webhooks_note')}</p>
        <div className="iq-table-wrap">
          <table className="iq-table">
            <thead>
              <tr>
                <th>{t('in_webhook_url')}</th>
                <th>{t('in_webhook_events')}</th>
                <th>{t('in_col_last_delivery')}</th>
                <th className="iq-num">{t('in_col_failures')}</th>
                <th>{t('in_col_status')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(webhooks.data ?? []).map((webhook) => (
                <tr key={webhook.id}>
                  <td className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>
                    {webhook.url}
                  </td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {(webhook.events ?? []).join(' ')}
                  </td>
                  <td>{stamp(webhook.last_delivery_at)}</td>
                  <td className="iq-num">{webhook.failure_count ?? 0}</td>
                  <td>
                    <Pill tone={webhook.is_active ? 'good' : 'mute'}>
                      {webhook.is_active ? t('in_key_active') : t('in_webhook_paused')}
                    </Pill>
                    {delivery?.id === webhook.id ? (
                      <div style={{ marginTop: 6 }}>
                        <Pill tone={delivery.result.delivered ? 'good' : 'crit'}>
                          {delivery.result.delivered
                            ? `${t('in_webhook_delivered')} ${delivery.result.status_code ?? ''}`
                            : (delivery.result.error ?? t('in_failed'))}
                        </Pill>
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div className="iq-actions">
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={test.isPending}
                        onClick={() =>
                          test.mutate(webhook.id, {
                            onSuccess: (result) => setDelivery({ id: webhook.id, result }),
                          })
                        }
                      >
                        {t('in_webhook_test')}
                      </button>
                      <button
                        type="button"
                        className="btn-link"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(webhook.id)}
                      >
                        {t('in_webhook_delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {webhooks.data?.length === 0 ? (
                <EmptyRow columns={6} text={t('in_no_webhooks')} />
              ) : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={webhooks.error ?? remove.error ?? test.error} />
      </section>
    </div>
  );
}

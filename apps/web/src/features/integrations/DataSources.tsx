/**
 * Screen 28 — `/integrations`. Adapters, API keys, webhooks and the event log as tabs
 * (`docs/SCREENS.md`).
 *
 * The tab is local UI state and lives in the URL's hash-free component state rather than a
 * route parameter: `docs/SCREENS.md` fixes one address for this screen, and adding a second
 * would be a route change only the orchestrator may make.
 */
import { useState } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';
import { AdaptersTab } from './AdaptersTab';
import { ApiKeysTab } from './ApiKeysTab';
import { EventLogTab } from './EventLogTab';
import { WebhooksTab } from './WebhooksTab';
import './integrations.css';

const TABS = [
  { id: 'adapters', labelKey: 'in_tab_adapters' },
  { id: 'api-keys', labelKey: 'in_tab_keys' },
  { id: 'webhooks', labelKey: 'in_tab_webhooks' },
  { id: 'events', labelKey: 'in_tab_events' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export function DataSources() {
  const { t } = useLocale();
  const [tab, setTab] = useState<TabId>('adapters');

  return (
    <div>
      <div className="iq-tabs" role="tablist" aria-label={t('in_tabs_label')}>
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            onClick={() => setTab(entry.id)}
          >
            {t(entry.labelKey)}
          </button>
        ))}
      </div>
      {tab === 'adapters' ? <AdaptersTab /> : null}
      {tab === 'api-keys' ? <ApiKeysTab /> : null}
      {tab === 'webhooks' ? <WebhooksTab /> : null}
      {tab === 'events' ? <EventLogTab /> : null}
    </div>
  );
}

/**
 * Screen 33 — `/admin/settings` (`docs/SCREENS.md`). Matching thresholds, prequalification
 * validity, notification settings, organisation and language — spec §11.2: "parameters, not
 * code". This screen is what makes that true in practice: every value here is a stored
 * `Setting` row (`services/settings_store.py`), not a constant anywhere in this codebase.
 *
 * No threshold is validated here beyond the HTML `min`/`step` a number input needs to be
 * usable — the server is the one authority on what a capacity ratio or a validity period may
 * be (`putSettings` answers `422` on an unknown key; nothing here repeats that check).
 */
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { useSession } from '../../auth/SessionProvider';
import { Card, ErrorText } from './shared';
import { settingsQuery, usePutSettings } from './queries';
import type { SettingsShape } from './queries';
import type { Body } from '../../api/http';
import './admin.css';

const CLASSES = ['A', 'B', 'C', 'D', 'F'] as const;

interface FormState {
  matching: {
    strong_min: string;
    capacity_ratio: string;
    supplier_turnover_divisor: string;
    default_min_class: (typeof CLASSES)[number];
  };
  qualification: {
    validity_months: string;
    pass_mark: string;
    tax_clearance_validity_months: string;
  };
  freshness: {
    financials_months: string;
    headcount_months: string;
    stale_profile_days: string;
  };
  notifications: {
    expiry_reminder_days: string;
    expiring_window_days: string;
    email_enabled: boolean;
  };
  organisation: {
    name: string;
    default_locale: 'az' | 'en';
  };
}

function toForm(data: SettingsShape): FormState {
  const matching = data.matching ?? {};
  const qualification = data.qualification ?? {};
  const freshness = data.freshness ?? {};
  const notifications = data.notifications;
  const organisation = data.organisation ?? {};
  return {
    matching: {
      strong_min: String(matching.strong_min ?? ''),
      capacity_ratio: String(matching.capacity_ratio ?? ''),
      supplier_turnover_divisor: String(matching.supplier_turnover_divisor ?? ''),
      default_min_class: (matching.default_min_class as FormState['matching']['default_min_class']) ?? 'C',
    },
    qualification: {
      validity_months: String(qualification.validity_months ?? ''),
      pass_mark: String(qualification.pass_mark ?? ''),
      tax_clearance_validity_months: String(qualification.tax_clearance_validity_months ?? ''),
    },
    freshness: {
      financials_months: String(freshness.financials_months ?? ''),
      headcount_months: String(freshness.headcount_months ?? ''),
      stale_profile_days: String(freshness.stale_profile_days ?? ''),
    },
    notifications: {
      expiry_reminder_days: (notifications?.expiry_reminder_days ?? []).join(', '),
      expiring_window_days: String(notifications?.expiring_window_days ?? ''),
      email_enabled: Boolean(notifications?.email_enabled),
    },
    organisation: {
      name: String(organisation.name ?? ''),
      default_locale: organisation.default_locale ?? 'az',
    },
  };
}

export function SettingsScreen() {
  const { t } = useLocale();
  const { session } = useSession();
  const canWrite =
    session.status === 'authenticated' && session.principal.permissions.includes('putSettings');

  const settings = useQuery(settingsQuery);
  const putMutation = usePutSettings();
  const [form, setForm] = useState<FormState | null>(null);

  useEffect(() => {
    if (settings.data) setForm(toForm(settings.data));
  }, [settings.data]);

  if (!form) {
    return (
      <div>
        <div className="page-head">
          <h2>{t('adm_settings_title')}</h2>
        </div>
        <ErrorText error={settings.error} />
        {settings.isLoading ? <p className="adm-note">{t('adm_loading')}</p> : null}
      </div>
    );
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canWrite) return;
    const body: Body<'putSettings'> = {
      matching: {
        strong_min: Number(form.matching.strong_min),
        capacity_ratio: Number(form.matching.capacity_ratio),
        supplier_turnover_divisor: Number(form.matching.supplier_turnover_divisor),
        default_min_class: form.matching.default_min_class,
      },
      qualification: {
        validity_months: Number(form.qualification.validity_months),
        pass_mark: Number(form.qualification.pass_mark),
        tax_clearance_validity_months: Number(form.qualification.tax_clearance_validity_months),
      },
      freshness: {
        financials_months: Number(form.freshness.financials_months),
        headcount_months: Number(form.freshness.headcount_months),
        stale_profile_days: Number(form.freshness.stale_profile_days),
      },
      notifications: {
        expiry_reminder_days: form.notifications.expiry_reminder_days
          .split(',')
          .map((value) => value.trim())
          .filter((value) => value.length > 0)
          .map(Number),
        expiring_window_days: Number(form.notifications.expiring_window_days),
        email_enabled: form.notifications.email_enabled,
      },
      organisation: {
        name: form.organisation.name,
        default_locale: form.organisation.default_locale,
      },
    };
    putMutation.mutate(body);
  };

  return (
    <div>
      <div className="page-head">
        <h2>{t('adm_settings_title')}</h2>
      </div>
      <p className="adm-note">{t('adm_settings_sub')}</p>
      {!canWrite ? <p className="adm-alert">{t('adm_settings_read_only')}</p> : null}

      <form onSubmit={handleSubmit} noValidate>
        <fieldset disabled={!canWrite || putMutation.isPending} className="adm-fieldset">
          <Card title={t('adm_group_matching')} note={t('adm_group_matching_note')}>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="set-strong-min">{t('adm_strong_min')}</label>
                <input
                  id="set-strong-min"
                  type="number"
                  min={0}
                  step={1}
                  value={form.matching.strong_min}
                  onChange={(event) =>
                    setForm({ ...form, matching: { ...form.matching, strong_min: event.target.value } })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-capacity">{t('adm_capacity_ratio')}</label>
                <input
                  id="set-capacity"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={form.matching.capacity_ratio}
                  onChange={(event) =>
                    setForm({ ...form, matching: { ...form.matching, capacity_ratio: event.target.value } })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-sup-div">{t('adm_supplier_turnover_divisor')}</label>
                <input
                  id="set-sup-div"
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={form.matching.supplier_turnover_divisor}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      matching: { ...form.matching, supplier_turnover_divisor: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-min-class">{t('adm_default_min_class')}</label>
                <select
                  id="set-min-class"
                  value={form.matching.default_min_class}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      matching: {
                        ...form.matching,
                        default_min_class: event.target.value as FormState['matching']['default_min_class'],
                      },
                    })
                  }
                >
                  {CLASSES.map((cls) => (
                    <option key={cls} value={cls}>
                      {cls}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </Card>

          <Card title={t('adm_group_qualification')} note={t('adm_group_qualification_note')}>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="set-validity">{t('adm_validity_months')}</label>
                <input
                  id="set-validity"
                  type="number"
                  min={1}
                  step={1}
                  value={form.qualification.validity_months}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      qualification: { ...form.qualification, validity_months: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-pass-mark">{t('adm_pass_mark')}</label>
                <input
                  id="set-pass-mark"
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={form.qualification.pass_mark}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      qualification: { ...form.qualification, pass_mark: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-tax">{t('adm_tax_clearance_validity_months')}</label>
                <input
                  id="set-tax"
                  type="number"
                  min={1}
                  step={1}
                  value={form.qualification.tax_clearance_validity_months}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      qualification: {
                        ...form.qualification,
                        tax_clearance_validity_months: event.target.value,
                      },
                    })
                  }
                />
              </div>
            </div>
          </Card>

          <Card title={t('adm_group_freshness')} note={t('adm_group_freshness_note')}>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="set-fin">{t('adm_financials_months')}</label>
                <input
                  id="set-fin"
                  type="number"
                  min={1}
                  step={1}
                  value={form.freshness.financials_months}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      freshness: { ...form.freshness, financials_months: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-head">{t('adm_headcount_months')}</label>
                <input
                  id="set-head"
                  type="number"
                  min={1}
                  step={1}
                  value={form.freshness.headcount_months}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      freshness: { ...form.freshness, headcount_months: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-stale">{t('adm_stale_profile_days')}</label>
                <input
                  id="set-stale"
                  type="number"
                  min={1}
                  step={1}
                  value={form.freshness.stale_profile_days}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      freshness: { ...form.freshness, stale_profile_days: event.target.value },
                    })
                  }
                />
              </div>
            </div>
          </Card>

          <Card title={t('adm_group_notifications')} note={t('adm_group_notifications_note')}>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="set-reminders">{t('adm_expiry_reminder_days')}</label>
                <input
                  id="set-reminders"
                  value={form.notifications.expiry_reminder_days}
                  placeholder="30, 7"
                  onChange={(event) =>
                    setForm({
                      ...form,
                      notifications: {
                        ...form.notifications,
                        expiry_reminder_days: event.target.value,
                      },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-expiring-window">{t('adm_expiring_window_days')}</label>
                <input
                  id="set-expiring-window"
                  type="number"
                  min={1}
                  step={1}
                  value={form.notifications.expiring_window_days}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      notifications: {
                        ...form.notifications,
                        expiring_window_days: event.target.value,
                      },
                    })
                  }
                />
              </div>
              <label className="adm-checkbox" style={{ alignSelf: 'end' }}>
                <input
                  type="checkbox"
                  checked={form.notifications.email_enabled}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      notifications: { ...form.notifications, email_enabled: event.target.checked },
                    })
                  }
                />
                {t('adm_email_enabled')}
              </label>
            </div>
          </Card>

          <Card title={t('adm_group_organisation')} note={t('adm_group_organisation_note')}>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="set-org-name">{t('adm_org_name')}</label>
                <input
                  id="set-org-name"
                  value={form.organisation.name}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      organisation: { ...form.organisation, name: event.target.value },
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="set-org-locale">{t('adm_default_locale')}</label>
                <select
                  id="set-org-locale"
                  value={form.organisation.default_locale}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      organisation: {
                        ...form.organisation,
                        default_locale: event.target.value as 'az' | 'en',
                      },
                    })
                  }
                >
                  <option value="az">AZ</option>
                  <option value="en">EN</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="set-org-currency">{t('adm_currency')}</label>
                <input id="set-org-currency" value="AZN" disabled />
              </div>
            </div>
          </Card>
        </fieldset>

        <ErrorText error={putMutation.error} />
        {putMutation.isSuccess ? (
          <p className="form-success" role="status">
            {t('adm_settings_saved')}
          </p>
        ) : null}
        {canWrite ? (
          <div className="adm-actions">
            <button type="submit" className="btn-primary" disabled={putMutation.isPending}>
              {t('adm_save')}
            </button>
          </div>
        ) : null}
      </form>
    </div>
  );
}

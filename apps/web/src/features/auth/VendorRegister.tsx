import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { registerVendor, verifyOtp } from '../../api/auth';
import type { Body } from '../../api/http';
import { useSession } from '../../auth/SessionProvider';
import { homeRouteFor } from '../../auth/session';
import { useLocale } from '../../i18n/LocaleProvider';
import { AuthLayout } from './AuthLayout';
import { localisedErrorKey } from './errorMessage';

type VendorType = NonNullable<Body<'registerVendor'>['type']>;

const emptyForm: Omit<Body<'registerVendor'>, 'locale'> = {
  legal_name: '',
  voen: '',
  type: 'sub',
  contact_name: '',
  position: '',
  phone: '',
  email: '',
};

/**
 * Vendor self-registration (`POST /auth/vendor/register`) — exactly the fields
 * `VendorRegistration` declares, nothing else. `locale` is not a separate field: it is the
 * language the applicant is already using this screen in (`useLocale()`), sent along rather
 * than asked for twice. Success returns the same `OtpChallenge` shape `requestOtp` does, so
 * the screen finishes the same way vendor sign-in does — a one-time code, verified in place.
 */
export function VendorRegister() {
  const { t, locale } = useLocale();
  const { refresh } = useSession();
  const navigate = useNavigate();

  const [form, setForm] = useState(emptyForm);
  const [code, setCode] = useState('');
  const [debugCode, setDebugCode] = useState<string | null>(null);

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const registerStep = useMutation({
    mutationFn: () => registerVendor({ ...form, locale }),
    onSuccess: (challenge) => setDebugCode(challenge.debug_code ?? null),
  });

  const verifyStep = useMutation({
    mutationFn: () => verifyOtp({ email: form.email, code }),
    onSuccess: async (session) => {
      await refresh();
      await navigate({ to: homeRouteFor(session.user) });
    },
  });

  const handleRegister = (event: FormEvent) => {
    event.preventDefault();
    registerStep.reset();
    registerStep.mutate();
  };

  const handleVerify = (event: FormEvent) => {
    event.preventDefault();
    verifyStep.reset();
    verifyStep.mutate();
  };

  const step = registerStep.isSuccess ? 'code' : 'form';

  return (
    <AuthLayout>
      <div className="auth-card">
        <div>
          <h2>{t('register_title')}</h2>
          <p className="muted">{t('register_sub')}</p>
        </div>

        {step === 'form' ? (
          <form className="auth-form" onSubmit={handleRegister} noValidate>
            <div className="field">
              <label htmlFor="reg-legal-name">{t('field_legal_name')}</label>
              <input
                id="reg-legal-name"
                name="organization"
                type="text"
                autoComplete="organization"
                required
                minLength={2}
                value={form.legal_name}
                onChange={(event) => set('legal_name', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-voen">{t('field_voen')}</label>
              <input
                id="reg-voen"
                name="voen"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{10}"
                maxLength={10}
                autoComplete="off"
                spellCheck={false}
                required
                value={form.voen}
                onChange={(event) => set('voen', event.target.value.replace(/\D/g, ''))}
              />
            </div>
            <div className="field">
              <span>{t('field_type')}</span>
              <div className="field-radio-group" role="radiogroup" aria-label={t('field_type')}>
                {(['sub', 'sup', 'both'] as VendorType[]).map((value) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="type"
                      value={value}
                      checked={form.type === value}
                      onChange={() => set('type', value)}
                    />
                    {t(`type_${value}`)}
                  </label>
                ))}
              </div>
            </div>
            <div className="field">
              <label htmlFor="reg-contact-name">{t('field_contact_name')}</label>
              <input
                id="reg-contact-name"
                name="name"
                type="text"
                autoComplete="name"
                required
                value={form.contact_name}
                onChange={(event) => set('contact_name', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-position">{t('field_position')}</label>
              <input
                id="reg-position"
                name="organization-title"
                type="text"
                autoComplete="organization-title"
                value={form.position}
                onChange={(event) => set('position', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-phone">{t('field_phone')}</label>
              <input
                id="reg-phone"
                name="tel"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                value={form.phone}
                onChange={(event) => set('phone', event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-email">{t('field_email')}</label>
              <input
                id="reg-email"
                name="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                spellCheck={false}
                required
                value={form.email}
                onChange={(event) => set('email', event.target.value)}
              />
            </div>
            {registerStep.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(registerStep.error))}
              </p>
            ) : null}
            <button type="submit" className="btn-primary" disabled={registerStep.isPending}>
              {registerStep.isPending ? `${t('register_submit')}…` : t('register_submit')}
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleVerify} noValidate>
            <p className="muted">
              {t('otp_sent_to')} <strong>{form.email}</strong>
            </p>
            {debugCode ? (
              <p className="auth-hint" role="status">
                {t('otp_debug_code')} <span className="mono">{debugCode}</span>
              </p>
            ) : null}
            <div className="field">
              <label htmlFor="reg-code">{t('field_code')}</label>
              <input
                id="reg-code"
                name="one-time-code"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                spellCheck={false}
                required
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
              />
            </div>
            {verifyStep.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(verifyStep.error))}
              </p>
            ) : null}
            <button type="submit" className="btn-primary" disabled={verifyStep.isPending}>
              {verifyStep.isPending ? `${t('otp_verify')}…` : t('otp_verify')}
            </button>
          </form>
        )}

        <div className="auth-links">
          <Link to="/login">{t('to_vendor_login')}</Link>
        </div>
      </div>
    </AuthLayout>
  );
}

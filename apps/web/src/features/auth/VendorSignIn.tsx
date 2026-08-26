import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { requestOtp, verifyOtp } from '../../api/auth';
import { useSession } from '../../auth/SessionProvider';
import { homeRouteFor } from '../../auth/session';
import { useLocale } from '../../i18n/LocaleProvider';
import { AuthLayout } from './AuthLayout';
import { localisedErrorKey } from './errorMessage';

/**
 * Vendor sign-in — e-mail, then a one-time code, one screen (`POST /auth/otp/request` then
 * `POST /auth/otp/verify`, brief §2 / PROGRESS.md). In `AUTH_MODE=test` the response carries
 * `debug_code`, which the second step shows so a tester never needs a mailbox.
 */
export function VendorSignIn() {
  const { t } = useLocale();
  const { refresh } = useSession();
  const navigate = useNavigate();
  const search = useSearch({ from: '/public/login' });

  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [debugCode, setDebugCode] = useState<string | null>(null);

  const requestStep = useMutation({
    mutationFn: () => requestOtp({ email }),
    onSuccess: (challenge) => setDebugCode(challenge.debug_code ?? null),
  });

  const verifyStep = useMutation({
    mutationFn: () => verifyOtp({ email, code }),
    onSuccess: async (session) => {
      await refresh();
      await navigate({ to: search.redirect ?? homeRouteFor(session.user) });
    },
  });

  const handleRequest = (event: FormEvent) => {
    event.preventDefault();
    requestStep.reset();
    requestStep.mutate();
  };

  const handleVerify = (event: FormEvent) => {
    event.preventDefault();
    verifyStep.reset();
    verifyStep.mutate();
  };

  const step = requestStep.isSuccess ? 'code' : 'email';

  return (
    <AuthLayout>
      <div className="auth-card">
        <div>
          <h2>{t('login_vendor_title')}</h2>
          <p className="muted">{t('login_vendor_sub')}</p>
        </div>

        {step === 'email' ? (
          <form className="auth-form" onSubmit={handleRequest} noValidate>
            <div className="field">
              <label htmlFor="vendor-email">{t('field_email')}</label>
              <input
                id="vendor-email"
                name="email"
                type="email"
                autoComplete="email"
                inputMode="email"
                spellCheck={false}
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            {requestStep.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(requestStep.error))}
              </p>
            ) : null}
            <button type="submit" className="btn-primary" disabled={requestStep.isPending}>
              {requestStep.isPending ? `${t('otp_send')}…` : t('otp_send')}
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleVerify} noValidate>
            <p className="muted">
              {t('otp_sent_to')} <strong>{email}</strong>
            </p>
            {debugCode ? (
              <p className="auth-hint" role="status">
                {t('otp_debug_code')} <span className="mono">{debugCode}</span>
              </p>
            ) : null}
            <div className="field">
              <label htmlFor="vendor-code">{t('field_code')}</label>
              <input
                id="vendor-code"
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
            <div className="auth-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  requestStep.reset();
                  setCode('');
                }}
              >
                {t('otp_change_email')}
              </button>
              <button type="submit" className="btn-primary" disabled={verifyStep.isPending}>
                {verifyStep.isPending ? `${t('otp_verify')}…` : t('otp_verify')}
              </button>
            </div>
            <button
              type="button"
              className="btn-link"
              onClick={() => requestStep.mutate()}
              disabled={requestStep.isPending}
            >
              {t('otp_resend')}
            </button>
          </form>
        )}

        <div className="auth-links">
          <Link to="/register">{t('to_register')}</Link>
          <Link to="/login/staff" search={{ redirect: search.redirect }}>
            {t('to_staff_login')}
          </Link>
        </div>
      </div>
    </AuthLayout>
  );
}

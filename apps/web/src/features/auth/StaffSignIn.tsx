import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link, useNavigate, useSearch } from '@tanstack/react-router';
import { staffLogin, verifyTotp } from '../../api/auth';
import { useSession } from '../../auth/SessionProvider';
import { homeRouteFor } from '../../auth/session';
import { useLocale } from '../../i18n/LocaleProvider';
import { AuthLayout } from './AuthLayout';
import { localisedErrorKey } from './errorMessage';

/**
 * Staff sign-in — e-mail + password, then the TOTP second factor, one screen
 * (`POST /auth/staff/login` returns a `challenge_id`; `POST /auth/staff/totp/verify` exchanges
 * it for the session — PROGRESS.md's ruling on the two-step flow). `debug_code` in
 * `AUTH_MODE=test` shows the current code so an authenticator app is optional.
 */
export function StaffSignIn() {
  const { t } = useLocale();
  const { refresh } = useSession();
  const navigate = useNavigate();
  const search = useSearch({ from: '/public/login/staff' });

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [debugCode, setDebugCode] = useState<string | null>(null);

  const passwordStep = useMutation({
    mutationFn: () => staffLogin({ email, password }),
    onSuccess: (challenge) => {
      setChallengeId(challenge.challenge_id);
      setDebugCode(challenge.debug_code ?? null);
    },
  });

  const totpStep = useMutation({
    mutationFn: () => {
      if (!challengeId) throw new Error('no active challenge');
      return verifyTotp({ challenge_id: challengeId, code });
    },
    onSuccess: async (session) => {
      await refresh();
      await navigate({ to: search.redirect ?? homeRouteFor(session.user) });
    },
  });

  const handlePassword = (event: FormEvent) => {
    event.preventDefault();
    passwordStep.reset();
    passwordStep.mutate();
  };

  const handleTotp = (event: FormEvent) => {
    event.preventDefault();
    totpStep.reset();
    totpStep.mutate();
  };

  const step = challengeId ? 'totp' : 'password';

  return (
    <AuthLayout>
      <div className="auth-card">
        <div>
          <h2>{t('login_staff_title')}</h2>
          <p className="muted">{t('login_staff_sub')}</p>
        </div>

        {step === 'password' ? (
          <form className="auth-form" onSubmit={handlePassword} noValidate>
            <div className="field">
              <label htmlFor="staff-email">{t('field_email')}</label>
              <input
                id="staff-email"
                name="email"
                type="email"
                autoComplete="username"
                inputMode="email"
                spellCheck={false}
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="staff-password">{t('field_password')}</label>
              <input
                id="staff-password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            {passwordStep.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(passwordStep.error))}
              </p>
            ) : null}
            <button type="submit" className="btn-primary" disabled={passwordStep.isPending}>
              {passwordStep.isPending ? `${t('staff_login')}…` : t('staff_login')}
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleTotp} noValidate>
            <p className="muted">{t('staff_totp_sub')}</p>
            {debugCode ? (
              <p className="auth-hint" role="status">
                {t('otp_debug_code')} <span className="mono">{debugCode}</span>
              </p>
            ) : null}
            <div className="field">
              <label htmlFor="staff-totp">{t('field_totp_code')}</label>
              <input
                id="staff-totp"
                name="totp-code"
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
            {totpStep.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(totpStep.error))}
              </p>
            ) : null}
            <div className="auth-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setChallengeId(null);
                  setCode('');
                }}
              >
                {t('staff_totp_back')}
              </button>
              <button type="submit" className="btn-primary" disabled={totpStep.isPending}>
                {totpStep.isPending ? `${t('staff_verify')}…` : t('staff_verify')}
              </button>
            </div>
          </form>
        )}

        <div className="auth-links">
          <Link to="/login" search={{ redirect: search.redirect }}>
            {t('to_vendor_login')}
          </Link>
        </div>
      </div>
    </AuthLayout>
  );
}

import type { ReactNode } from 'react';
import { LOCALES, useLocale } from '../../i18n/LocaleProvider';
import { useTheme } from '../../theme/ThemeProvider';

/**
 * The frame every public (signed-out) screen renders into: brand mark, language and theme
 * controls — available before a session exists — and a single centred card. There is no
 * `<Rail>` / `<Topbar>` here; those belong to `AppShell`, which only mounts once a session
 * does (`app/routes.tsx`).
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  const { locale, setLocale, t } = useLocale();
  const { theme, setTheme } = useTheme();

  return (
    <div className="auth-shell">
      <div className="auth-top">
        <div className="auth-brand">
          VendorIQ <small>uni ko qsc</small>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <div className="seg" role="group" aria-label="Language">
            {LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                aria-pressed={locale === code}
                onClick={() => setLocale(code)}
              >
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Theme">
            <button
              type="button"
              aria-pressed={theme === 'light'}
              onClick={() => setTheme('light')}
              title={t('show')}
            >
              ☀
            </button>
            <button type="button" aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}>
              ☾
            </button>
          </div>
        </div>
      </div>
      {children}
    </div>
  );
}

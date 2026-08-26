import { LOCALES, useLocale } from '../i18n/LocaleProvider';
import { WorkspaceSwitch } from './WorkspaceSwitch';
import { useTheme } from '../theme/ThemeProvider';

/** Page title on the left; workspace, AZ/EN and theme controls on the right. */
export function Topbar({
  title,
  workspace,
}: {
  title: string;
  workspace: 'manager' | 'vendor';
}) {
  const { locale, setLocale, t } = useLocale();
  const { theme, setTheme } = useTheme();

  return (
    <header className="topbar">
      <h1>{title}</h1>
      <WorkspaceSwitch workspace={workspace} />
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
    </header>
  );
}

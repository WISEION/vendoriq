import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/client';
import { useLocale } from '../i18n/LocaleProvider';

/**
 * Brief §6: while `AUTH_MODE=test` the one-time codes are visible and the accounts are seeded.
 * That has to be impossible to miss, so the shell says so on every screen.
 *
 * Translated, even though only a developer or a tester ever sees it. It was written as a
 * literal, which is precisely why the i18n test could not see it: the test checks that keys
 * resolve, and a hard-coded sentence has no key. The result was one line of English sitting
 * on every Azerbaijani screen, including all 34 of the delivered AZ screenshots.
 */
export function DevBanner() {
  const { t } = useLocale();
  const { data } = useQuery({ queryKey: ['health'], queryFn: getHealth, retry: false });
  if (!data || data.auth_mode !== 'test') return null;

  return (
    <div className="banner" role="status">
      <strong>AUTH_MODE=test</strong>
      <span>
        {t('dev_banner')} — {data.app_env} / {t('dev_storage')}: {data.storage_backend}
      </span>
    </div>
  );
}

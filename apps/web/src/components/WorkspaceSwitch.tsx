import { Link } from '@tanstack/react-router';
import { MANAGER_HOME_PATH, VENDOR_HOME_PATH } from '../app/paths';
import { useLocale } from '../i18n/LocaleProvider';
import { useSession } from '../auth/SessionProvider';

/**
 * Manager dashboard ↔ vendor portal. Both live in one codebase with role-gated routes
 * (spec §4); the switch is visible only to staff, who legitimately need to see the portal
 * as a vendor sees it. A vendor account never renders it.
 */
export function WorkspaceSwitch({ workspace }: { workspace: 'manager' | 'vendor' }) {
  const { t } = useLocale();
  const { session } = useSession();

  if (session.status === 'authenticated' && session.principal.role === 'vendor') return null;

  return (
    <div className="seg" role="group" aria-label="Workspace">
      <Link to={MANAGER_HOME_PATH} data-pressed={workspace === 'manager'}>
        {t('role_manager')}
      </Link>
      <Link to={VENDOR_HOME_PATH} data-pressed={workspace === 'vendor'}>
        {t('role_vendor')}
      </Link>
    </div>
  );
}

import { Link } from '@tanstack/react-router';
import { useLocale } from '../i18n/LocaleProvider';

/**
 * Manager dashboard ↔ vendor portal. Both live in one codebase with role-gated routes
 * (spec §4); the switch is visible only to staff, who legitimately need to see the portal
 * as a vendor sees it. A vendor account never renders it.
 */
export function WorkspaceSwitch({ workspace }: { workspace: 'manager' | 'vendor' }) {
  const { t } = useLocale();

  return (
    <div className="seg" role="group" aria-label="Workspace">
      <Link to="/" data-pressed={workspace === 'manager'}>
        {t('role_manager')}
      </Link>
      <Link to="/portal" data-pressed={workspace === 'vendor'}>
        {t('role_vendor')}
      </Link>
    </div>
  );
}

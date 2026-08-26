import { Link, useRouterState } from '@tanstack/react-router';
import { useLocale } from '../i18n/LocaleProvider';
import { MANAGER_NAV, VENDOR_NAV } from '../app/navigation';
import { Icon } from './Icon';

/**
 * Left rail. Which sections appear is a function of the workspace the user is in; which
 * *items* a role may open is enforced server-side — the rail only hides what is pointless.
 */
export function Rail({ workspace }: { workspace: 'manager' | 'vendor' }) {
  const { t } = useLocale();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const sections = workspace === 'manager' ? MANAGER_NAV : VENDOR_NAV;

  return (
    <aside className="rail">
      <div className="brand">
        VendorIQ <small>uni ko qsc</small>
      </div>
      {sections.map((section) => (
        <div key={section.titleKey}>
          <div className="section">{t(section.titleKey)}</div>
          <nav aria-label={t(section.titleKey)}>
            {section.items.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                data-active={
                  item.path === '/' || item.path === '/portal'
                    ? pathname === item.path
                    : pathname.startsWith(item.path)
                }
              >
                <Icon name={item.icon} />
                <span>{t(item.labelKey)}</span>
              </Link>
            ))}
          </nav>
        </div>
      ))}
      <div className="rail-foot">{t('foot')}</div>
    </aside>
  );
}

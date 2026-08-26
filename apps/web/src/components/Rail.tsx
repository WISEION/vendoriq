import { Link, useRouterState } from '@tanstack/react-router';
import { useLocale } from '../i18n/LocaleProvider';
import { navSectionsFor, VENDOR_NAV } from '../app/navigation';
import { useSession } from '../auth/SessionProvider';
import { Icon } from './Icon';

/**
 * Left rail. The workspace decides which set of sections applies; within the manager
 * workspace the caller's own `permissions` from `GET /api/auth/me` decide which items appear
 * (ADR-013). The rail only hides what the server would refuse anyway — it is a convenience,
 * never the enforcement.
 */
export function Rail({ workspace }: { workspace: 'manager' | 'vendor' }) {
  const { t } = useLocale();
  const { session } = useSession();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const permissions = session.status === 'authenticated' ? session.principal.permissions : [];
  const sections = workspace === 'manager' ? navSectionsFor(permissions) : VENDOR_NAV;

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

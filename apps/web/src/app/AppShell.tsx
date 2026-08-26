import { Outlet, useRouterState } from '@tanstack/react-router';
import { Rail } from '../components/Rail';
import { Topbar } from '../components/Topbar';
import { DevBanner } from '../components/DevBanner';
import { PAGE_TEXT } from './navigation';
import { useLocale } from '../i18n/LocaleProvider';

/** Rail + topbar + content. Every screen renders inside this frame. */
export function AppShell() {
  const { t } = useLocale();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const workspace = pathname.startsWith('/portal') ? 'vendor' : 'manager';
  const text = PAGE_TEXT[pathname];

  return (
    <div className="shell">
      <Rail workspace={workspace} />
      <div className="content">
        <Topbar title={text ? t(text.titleKey) : 'VendorIQ'} workspace={workspace} />
        <DevBanner />
        <Outlet />
      </div>
    </div>
  );
}

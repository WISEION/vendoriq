import { Outlet, useRouterState } from '@tanstack/react-router';
import { Rail } from '../components/Rail';
import { Topbar } from '../components/Topbar';
import { DevBanner } from '../components/DevBanner';
import { PAGE_TEXT } from './navigation';
import { useLocale } from '../i18n/LocaleProvider';

/** Rail + topbar + content. Every screen renders inside this frame. */
/**
 * The heading for an address, falling back to its nearest described ancestor.
 *
 * `PAGE_TEXT` describes the rail's destinations. The screens reached *from* them — a vendor
 * detail, one section of the application form, the Excel import — have no entry of their own,
 * and without this the topbar for all of them read "VendorIQ", which names the product rather
 * than the page the user is on.
 */
function pageTextFor(pathname: string): (typeof PAGE_TEXT)[string] | undefined {
  let path = pathname;
  while (path.length > 1) {
    const text = PAGE_TEXT[path];
    if (text) return text;
    path = path.slice(0, path.lastIndexOf('/')) || '/';
  }
  return PAGE_TEXT[path];
}

export function AppShell() {
  const { t } = useLocale();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const workspace = pathname.startsWith('/portal') ? 'vendor' : 'manager';
  const text = pageTextFor(pathname);

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

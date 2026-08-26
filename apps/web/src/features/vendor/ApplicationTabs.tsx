import { Link, useRouterState } from '@tanstack/react-router';
import { useLocale } from '../../i18n/LocaleProvider';
import { FORM_SECTIONS } from './fieldCatalog';
import type { SectionKey } from './fieldCatalog';

/**
 * The A–G tab strip (screens 6–12, `docs/SCREENS.md`). One rail entry ("Application form")
 * leads here; the seven sections are switched with these tabs, not seven rail rows — matching
 * `apps/web/src/app/navigation.ts`'s single `nav_vapply` entry.
 */
export function ApplicationTabs({ active }: { active: SectionKey }) {
  const { t, locale } = useLocale();
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <nav className="vp-tabs" aria-label={t('va_title')}>
      {FORM_SECTIONS.map((section) => {
        const path = `/portal/application/${section.key}`;
        const isActive = section.key === active || pathname === path;
        return (
          <Link key={section.key} to={path} data-active={isActive ? 'true' : 'false'} aria-current={isActive ? 'page' : undefined}>
            {locale === 'az' ? section.az : section.en}
          </Link>
        );
      })}
    </nav>
  );
}

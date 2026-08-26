import type { ReactNode } from 'react';
import { useLocale } from '../i18n/LocaleProvider';
import { PAGE_TEXT } from './navigation';

/**
 * The frame a screen is built into: heading, lead paragraph and the content region the
 * feature teams fill. In phase 0 the region is empty on purpose — the shell is the deliverable,
 * the screens are not.
 */
export function Page({ route, children }: { route: string; children?: ReactNode }) {
  const { t } = useLocale();
  const text = PAGE_TEXT[route];

  return (
    <main className="page">
      {text ? (
        <div className="page-head">
          <h2>{t(text.titleKey)}</h2>
          <p>{t(text.subKey)}</p>
        </div>
      ) : null}
      {children}
    </main>
  );
}

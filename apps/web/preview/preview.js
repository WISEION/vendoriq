/**
 * Dependency-free rendering of the same shell `src/app/AppShell.tsx` renders.
 *
 * It exists for one reason: on a host where the npm registry is unreachable, `make web` still
 * has to show the rail/topbar layout, the design tokens and the AZ/EN toggle. It imports the
 * real `src/theme/global.css`, the real `src/i18n/*.json` and mirrors the same markup and class
 * names, so what you see here is what Vite serves once `npm install` succeeds.
 *
 * It is *not* part of the application bundle and is excluded from lint and typecheck.
 */

const ICONS = {
  overview:
    '<rect x="1.5" y="1.5" width="5" height="5" rx="1"/><rect x="9.5" y="1.5" width="5" height="5" rx="1"/><rect x="1.5" y="9.5" width="5" height="5" rx="1"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/>',
  vendors: '<path d="M2 14V5l6-3 6 3v9"/><path d="M6 14v-4h4v4"/>',
  apps: '<path d="M3 2h7l3 3v9H3z"/><path d="M5.5 8.5l1.5 1.5 3.5-3.5"/>',
  projects: '<path d="M2 13h12"/><path d="M4 13V7h3v6M9 13V3h3v10"/>',
  market: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/>',
  models: '<path d="M2 4h12M2 8h8M2 12h10"/>',
  integrations: '<path d="M6 3H3v3M10 3h3v3M6 13H3v-3M10 13h3v-3"/><circle cx="8" cy="8" r="2"/>',
  vhome: '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
  vprofile: '<circle cx="8" cy="5.5" r="3"/><path d="M2.5 14c.5-3 3-4.5 5.5-4.5s5 1.5 5.5 4.5"/>',
  vapply: '<path d="M3 2h10v12H3z"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/>',
  vdocs: '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/>',
  vsubmit: '<path d="M2 8l12-6-4 12-2-5z"/>',
};

const MANAGER_NAV = [
  {
    titleKey: 'sec_manage',
    items: [
      { path: '/', labelKey: 'nav_overview', icon: 'overview' },
      { path: '/vendors', labelKey: 'nav_vendors', icon: 'vendors' },
      { path: '/applications', labelKey: 'nav_apps', icon: 'apps' },
      { path: '/projects', labelKey: 'nav_projects', icon: 'projects' },
    ],
  },
  { titleKey: 'sec_intel', items: [{ path: '/market', labelKey: 'nav_market', icon: 'market' }] },
  {
    titleKey: 'sec_setup',
    items: [
      { path: '/scoring-models', labelKey: 'nav_models', icon: 'models' },
      { path: '/integrations', labelKey: 'nav_integrations', icon: 'integrations' },
    ],
  },
];

const VENDOR_NAV = [
  {
    titleKey: 'sec_vendor',
    items: [
      { path: '/portal', labelKey: 'nav_vhome', icon: 'vhome' },
      { path: '/portal/profile', labelKey: 'nav_vprofile', icon: 'vprofile' },
      { path: '/portal/application', labelKey: 'nav_vapply', icon: 'vapply' },
      { path: '/portal/documents', labelKey: 'nav_vdocs', icon: 'vdocs' },
      { path: '/portal/submit', labelKey: 'nav_vsubmit', icon: 'vsubmit' },
    ],
  },
];

const PAGE_TEXT = {
  '/': { titleKey: 'ov_title', subKey: 'ov_sub' },
  '/vendors': { titleKey: 'vendors_title', subKey: 'vendors_sub' },
  '/applications': { titleKey: 'apps_title', subKey: 'apps_sub' },
  '/projects': { titleKey: 'proj_title', subKey: 'proj_sub' },
  '/market': { titleKey: 'mk_title', subKey: 'mk_sub' },
  '/scoring-models': { titleKey: 'mo_title', subKey: 'mo_sub' },
  '/integrations': { titleKey: 'in_title', subKey: 'in_sub' },
  '/portal': { titleKey: 'vh_title', subKey: 'vh_sub' },
  '/portal/profile': { titleKey: 'vp_title', subKey: 'vp_sub' },
  '/portal/application': { titleKey: 'va_title', subKey: 'va_sub' },
  '/portal/documents': { titleKey: 'vd_title', subKey: 'vd_sub' },
  '/portal/submit': { titleKey: 'vs_title', subKey: 'vs_sub' },
};

const state = {
  locale: localStorage.getItem('vendoriq.locale') || 'az',
  theme: localStorage.getItem('vendoriq.theme') || 'dark',
  route: '/',
  dict: { az: {}, en: {} },
  health: null,
};

const t = (key) => state.dict[state.locale][key] ?? state.dict.en[key] ?? key;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);

function railHtml() {
  const sections = state.route.startsWith('/portal') ? VENDOR_NAV : MANAGER_NAV;
  const nav = sections
    .map(
      (section) => `
      <div>
        <div class="section">${esc(t(section.titleKey))}</div>
        <nav aria-label="${esc(t(section.titleKey))}">
          ${section.items
            .map(
              (item) => `<a href="#${item.path}" data-active="${state.route === item.path}">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">${ICONS[item.icon]}</svg>
                <span>${esc(t(item.labelKey))}</span>
              </a>`,
            )
            .join('')}
        </nav>
      </div>`,
    )
    .join('');
  return `<aside class="rail">
    <div class="brand">VendorIQ <small>uni ko qsc</small></div>
    ${nav}
    <div class="rail-foot">${esc(t('foot'))}</div>
  </aside>`;
}

function bannerHtml() {
  if (!state.health || state.health.auth_mode !== 'test') return '';
  return `<div class="banner" role="status"><strong>AUTH_MODE=test</strong>
    <span>Seeded test accounts are active and one-time codes are shown in the server log —
    ${esc(state.health.app_env)} / storage: ${esc(state.health.storage_backend)}</span></div>`;
}

function render() {
  document.documentElement.lang = state.locale;
  document.documentElement.dataset.theme = state.theme;
  const text = PAGE_TEXT[state.route] ?? PAGE_TEXT['/'];

  document.getElementById('root').innerHTML = `
    <div class="shell">
      ${railHtml()}
      <div class="content">
        <header class="topbar">
          <h1>${esc(t(text.titleKey))}</h1>
          <div class="seg" role="group" aria-label="Workspace">
            <a href="#/" data-pressed="${!state.route.startsWith('/portal')}">${esc(t('role_manager'))}</a>
            <a href="#/portal" data-pressed="${state.route.startsWith('/portal')}">${esc(t('role_vendor'))}</a>
          </div>
          <div class="seg" role="group" aria-label="Language">
            <button type="button" data-locale="az" aria-pressed="${state.locale === 'az'}">AZ</button>
            <button type="button" data-locale="en" aria-pressed="${state.locale === 'en'}">EN</button>
          </div>
          <div class="seg" role="group" aria-label="Theme">
            <button type="button" data-theme="light" aria-pressed="${state.theme === 'light'}">☀</button>
            <button type="button" data-theme="dark" aria-pressed="${state.theme === 'dark'}">☾</button>
          </div>
        </header>
        ${bannerHtml()}
        <main class="page">
          <div class="page-head">
            <h2>${esc(t(text.titleKey))}</h2>
            <p>${esc(t(text.subKey))}</p>
          </div>
        </main>
      </div>
    </div>`;

  for (const button of document.querySelectorAll('.topbar [data-locale]')) {
    button.onclick = () => {
      state.locale = button.dataset.locale;
      localStorage.setItem('vendoriq.locale', state.locale);
      render();
    };
  }
  for (const button of document.querySelectorAll('.topbar [data-theme]')) {
    button.onclick = () => {
      state.theme = button.dataset.theme;
      localStorage.setItem('vendoriq.theme', state.theme);
      render();
    };
  }
}

window.addEventListener('hashchange', () => {
  state.route = window.location.hash.slice(1) || '/';
  render();
});

async function boot() {
  const [az, en] = await Promise.all([
    fetch('/src/i18n/az.json').then((r) => r.json()),
    fetch('/src/i18n/en.json').then((r) => r.json()),
  ]);
  state.dict = { az, en };
  state.route = window.location.hash.slice(1) || '/';
  render();

  try {
    const response = await fetch('/api/health');
    if (response.ok) {
      state.health = await response.json();
      render();
    }
  } catch {
    // The API is optional for the shell preview.
  }
}

boot();

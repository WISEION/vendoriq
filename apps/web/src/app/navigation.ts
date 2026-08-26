/**
 * The screen inventory: 34 artboards grouped exactly as the approved prototype's rail is
 * (`docs/design/app.js`, `NAV`). Routes exist from phase 0 so every screen has an address
 * before it has content; the feature teams fill the components in.
 */
/** `openapi.yaml` `UserRole` enum. */
export type UserRole = 'vendor' | 'officer' | 'commission' | 'manager' | 'admin';

export interface NavItem {
  /** Route path under the workspace root. */
  path: string;
  /** i18n key of the label. */
  labelKey: string;
  icon: keyof typeof ICONS;
  /**
   * Staff roles that may open this item, sourced from `docs/TEST_ACCOUNTS.md`'s role table
   * ("officer — the whole register", "commission — applications and evaluations", "manager /
   * admin — everything"). Omitted = every staff role (manager and admin always see
   * everything; access is still enforced server-side per operation — this only hides what a
   * role has no reason to open).
   */
  roles?: UserRole[];
}

export interface NavSection {
  /** i18n key of the section heading. */
  titleKey: string;
  items: NavItem[];
}

export const ICONS = {
  overview:
    '<rect x="1.5" y="1.5" width="5" height="5" rx="1"/><rect x="9.5" y="1.5" width="5" height="5" rx="1"/><rect x="1.5" y="9.5" width="5" height="5" rx="1"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/>',
  vendors: '<path d="M2 14V5l6-3 6 3v9"/><path d="M6 14v-4h4v4"/>',
  apps: '<path d="M3 2h7l3 3v9H3z"/><path d="M5.5 8.5l1.5 1.5 3.5-3.5"/>',
  projects: '<path d="M2 13h12"/><path d="M4 13V7h3v6M9 13V3h3v10"/>',
  market: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/>',
  models: '<path d="M2 4h12M2 8h8M2 12h10"/>',
  integrations:
    '<path d="M6 3H3v3M10 3h3v3M6 13H3v-3M10 13h3v-3"/><circle cx="8" cy="8" r="2"/>',
  admin: '<circle cx="8" cy="8" r="2.5"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2"/>',
  vhome: '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
  vprofile: '<circle cx="8" cy="5.5" r="3"/><path d="M2.5 14c.5-3 3-4.5 5.5-4.5s5 1.5 5.5 4.5"/>',
  vapply: '<path d="M3 2h10v12H3z"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/>',
  vdocs: '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/>',
  vsubmit: '<path d="M2 8l12-6-4 12-2-5z"/>',
} as const;

export const MANAGER_NAV: NavSection[] = [
  {
    titleKey: 'sec_manage',
    items: [
      { path: '/', labelKey: 'nav_overview', icon: 'overview' },
      {
        path: '/vendors',
        labelKey: 'nav_vendors',
        icon: 'vendors',
        roles: ['officer', 'manager', 'admin'],
      },
      {
        path: '/applications',
        labelKey: 'nav_apps',
        icon: 'apps',
        roles: ['officer', 'commission', 'manager', 'admin'],
      },
      { path: '/projects', labelKey: 'nav_projects', icon: 'projects', roles: ['manager', 'admin'] },
    ],
  },
  {
    titleKey: 'sec_intel',
    items: [{ path: '/market', labelKey: 'nav_market', icon: 'market', roles: ['manager', 'admin'] }],
  },
  {
    titleKey: 'sec_setup',
    items: [
      { path: '/scoring-models', labelKey: 'nav_models', icon: 'models', roles: ['manager', 'admin'] },
      {
        path: '/integrations',
        labelKey: 'nav_integrations',
        icon: 'integrations',
        roles: ['officer', 'admin'],
      },
    ],
  },
];

/** Sections and items a role may open — manager/admin see everything; others per `roles` above. */
export function navSectionsForRole(role: UserRole): NavSection[] {
  const seesEverything = role === 'manager' || role === 'admin';
  return MANAGER_NAV.map((section) => ({
    ...section,
    items: section.items.filter(
      (item) => seesEverything || !item.roles || item.roles.includes(role),
    ),
  })).filter((section) => section.items.length > 0);
}

export const VENDOR_NAV: NavSection[] = [
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

/** Page heading and lead paragraph per route, both from the prototype's dictionaries. */
export const PAGE_TEXT: Record<string, { titleKey: string; subKey: string }> = {
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

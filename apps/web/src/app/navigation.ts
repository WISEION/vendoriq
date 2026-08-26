/**
 * The rail: the addresses of `docs/SCREENS.md`, grouped as the approved prototype groups them
 * (`docs/design/app.js`, `NAV`).
 *
 * Visibility is not a second copy of the permission matrix. Each item names the **operation id**
 * that gates its screen, and the rail shows the item when `GET /api/auth/me` lists that id in
 * `permissions` (ADR-013). The server is the only place a role maps to an operation; a role
 * table here would be a duplicate that silently drifts — and did: it hid `/market` from officers
 * although `getIntelCoverage` admits them, and showed `/integrations` to admins but not managers.
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
   * The contract operation id that gates this screen — the one the screen cannot function
   * without. A management screen names the operation that *is* the management (a screen for
   * editing the taxonomy is gated on `createCategory`, not on the `listCategories` every
   * vendor may call to populate a picker).
   */
  gatedBy: string;
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
  integrations: '<path d="M6 3H3v3M10 3h3v3M6 13H3v-3M10 13h3v-3"/><circle cx="8" cy="8" r="2"/>',
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
      { path: '/', labelKey: 'nav_overview', icon: 'overview', gatedBy: 'getIntelOverview' },
      { path: '/vendors', labelKey: 'nav_vendors', icon: 'vendors', gatedBy: 'listVendors' },
      { path: '/applications', labelKey: 'nav_apps', icon: 'apps', gatedBy: 'listApplications' },
      { path: '/cycles', labelKey: 'nav_cycles', icon: 'apps', gatedBy: 'listCycles' },
      { path: '/projects', labelKey: 'nav_projects', icon: 'projects', gatedBy: 'listProjects' },
    ],
  },
  {
    titleKey: 'sec_intel',
    items: [
      { path: '/market', labelKey: 'nav_market', icon: 'market', gatedBy: 'getIntelCoverage' },
    ],
  },
  {
    titleKey: 'sec_admin',
    items: [
      {
        path: '/admin/categories',
        labelKey: 'nav_categories',
        icon: 'admin',
        gatedBy: 'createCategory',
      },
      { path: '/admin/users', labelKey: 'nav_users', icon: 'admin', gatedBy: 'listUsers' },
      { path: '/admin/settings', labelKey: 'nav_settings', icon: 'admin', gatedBy: 'putSettings' },
      { path: '/admin/audit', labelKey: 'nav_audit', icon: 'admin', gatedBy: 'listAuditEvents' },
    ],
  },
  {
    titleKey: 'sec_setup',
    items: [
      {
        path: '/scoring-models',
        labelKey: 'nav_models',
        icon: 'models',
        gatedBy: 'listScoringModels',
      },
      {
        path: '/integrations',
        labelKey: 'nav_integrations',
        icon: 'integrations',
        gatedBy: 'listAdapters',
      },
    ],
  },
];

/**
 * The rail for one identity: every item whose gating operation the server says this caller may
 * call. `permissions` comes straight from `GET /api/auth/me`; an empty list yields an empty rail
 * rather than a default, because "we do not know what you may do" must never render as "all of it".
 */
export function navSectionsFor(permissions: readonly string[]): NavSection[] {
  const granted = new Set(permissions);
  return MANAGER_NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => granted.has(item.gatedBy)),
  })).filter((section) => section.items.length > 0);
}

export const VENDOR_NAV: NavSection[] = [
  {
    titleKey: 'sec_vendor',
    items: [
      { path: '/portal', labelKey: 'nav_vhome', icon: 'vhome', gatedBy: 'listApplications' },
      { path: '/portal/profile', labelKey: 'nav_vprofile', icon: 'vprofile', gatedBy: 'getVendor' },
      {
        path: '/portal/application',
        labelKey: 'nav_vapply',
        icon: 'vapply',
        gatedBy: 'getApplication',
      },
      {
        path: '/portal/documents',
        labelKey: 'nav_vdocs',
        icon: 'vdocs',
        gatedBy: 'listDocuments',
      },
      {
        path: '/portal/submit',
        labelKey: 'nav_vsubmit',
        icon: 'vsubmit',
        gatedBy: 'submitApplication',
      },
    ],
  },
];

/** Page heading and lead paragraph per route, both from the prototype's dictionaries. */
export const PAGE_TEXT: Record<string, { titleKey: string; subKey: string }> = {
  '/': { titleKey: 'ov_title', subKey: 'ov_sub' },
  '/vendors': { titleKey: 'vendors_title', subKey: 'vendors_sub' },
  '/applications': { titleKey: 'apps_title', subKey: 'apps_sub' },
  '/cycles': { titleKey: 'cyc_title', subKey: 'cyc_sub' },
  '/projects': { titleKey: 'proj_title', subKey: 'proj_sub' },
  '/market': { titleKey: 'mk_title', subKey: 'mk_sub' },
  '/scoring-models': { titleKey: 'mo_title', subKey: 'mo_sub' },
  '/integrations': { titleKey: 'in_title', subKey: 'in_sub' },
  '/admin/categories': { titleKey: 'adm_cat_title', subKey: 'adm_cat_sub' },
  '/admin/users': { titleKey: 'adm_usr_title', subKey: 'adm_usr_sub' },
  '/admin/settings': { titleKey: 'adm_set_title', subKey: 'adm_set_sub' },
  '/admin/audit': { titleKey: 'adm_aud_title', subKey: 'adm_aud_sub' },
  '/portal': { titleKey: 'vh_title', subKey: 'vh_sub' },
  '/portal/profile': { titleKey: 'vp_title', subKey: 'vp_sub' },
  '/portal/application': { titleKey: 'va_title', subKey: 'va_sub' },
  '/portal/documents': { titleKey: 'vd_title', subKey: 'vd_sub' },
  '/portal/submit': { titleKey: 'vs_title', subKey: 'vs_sub' },
};

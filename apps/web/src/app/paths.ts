/**
 * Route path constants, typed as plain `string` rather than the literal each assigns.
 *
 * TanStack Router only carries a literal path type for a route declared directly in the tree
 * built in `routes.tsx`; the manager/vendor screens are generated from the runtime
 * `PAGE_TEXT` map in `./navigation.ts` (so every rail entry has an address before it has
 * content — see that file), and a route built from a runtime string has no literal type for
 * the router to register. Anywhere navigation crosses that boundary — `/portal` here, or
 * `NavItem.path` in the rail — the target has to be a plain `string`, exactly as `Link`
 * already accepts for the rail; these constants keep every such call site consistent instead
 * of re-deriving the same widening at each one.
 */
export const VENDOR_LOGIN_PATH: string = '/login';
export const STAFF_LOGIN_PATH: string = '/login/staff';
export const VENDOR_REGISTER_PATH: string = '/register';
export const MANAGER_HOME_PATH: string = '/';
export const VENDOR_HOME_PATH: string = '/portal';

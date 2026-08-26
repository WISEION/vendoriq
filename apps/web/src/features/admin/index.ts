/**
 * Screens 31–34 (`docs/SCREENS.md`), ready to mount.
 *
 * The routes and the rail entries are the orchestrator's file (`apps/web/src/app/routes.tsx`,
 * `navigation.ts`) — this task's report files the four entries as a change request. Every
 * component below takes no route-only prop, so registering them is four lines:
 *
 * ```tsx
 * // /admin/categories — gated by `createCategory`
 * <CategoriesScreen />
 * // /admin/users — gated by `listUsers`
 * <UsersScreen />
 * // /admin/settings — gated by `putSettings`
 * <SettingsScreen />
 * // /admin/audit — gated by `listAuditEvents`
 * <AuditLogScreen />
 * ```
 */
export { CategoriesScreen } from './CategoriesScreen';
export { UsersScreen } from './UsersScreen';
export { SettingsScreen } from './SettingsScreen';
export { AuditLogScreen } from './AuditLogScreen';

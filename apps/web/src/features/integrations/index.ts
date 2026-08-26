/**
 * Screens 28–30 (`docs/SCREENS.md`), ready to mount.
 *
 * The routes themselves are `apps/web/src/app/routes.tsx`, which is the orchestrator's file;
 * this task's report files the three entries as a change request. Every component below takes
 * what it needs as a prop, so registering them is three lines and no rewriting:
 *
 * ```tsx
 * // /integrations
 * <DataSources />
 * // /integrations/excel-import
 * <ExcelImport />
 * // /integrations/adapters/$adapter
 * <ErpConnector adapter={params.adapter} />
 * ```
 */
export { DataSources } from './DataSources';
export { ExcelImport } from './ExcelImport';
export { ErpConnector } from './ErpConnector';
export { AdaptersTab } from './AdaptersTab';
export { ApiKeysTab } from './ApiKeysTab';
export { WebhooksTab } from './WebhooksTab';
export { EventLogTab } from './EventLogTab';

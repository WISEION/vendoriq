/**
 * Route addresses for screens 22–24 (`docs/SCREENS.md`), typed as plain `string`.
 *
 * `apps/web/src/app/routes.tsx` and `navigation.ts` are the orchestrator's to wire (task
 * 2C's brief: "I wire routes and rail entries when I merge you") — today's route tree only
 * generates a flat, param-less route per `navigation.ts` `PAGE_TEXT` key, so `/projects/new`,
 * `/projects/$projectId` and `/projects/$projectId/edit` do not exist as routes yet. These
 * constants and builders are what the wiring should target; until then, a `Link`/`navigate`
 * built from a plain `string` (the same widening `app/paths.ts` already documents and uses
 * for `VENDOR_HOME_PATH` etc.) type-checks without the target existing in the router yet.
 */
export const CYCLES_PATH: string = '/cycles';
export const PROJECTS_PATH: string = '/projects';
export const PROJECT_NEW_PATH: string = '/projects/new';

export function projectMatchingPath(projectId: string): string {
  return `/projects/${projectId}`;
}

export function projectEditPath(projectId: string): string {
  return `/projects/${projectId}/edit`;
}

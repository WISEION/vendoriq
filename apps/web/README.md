# `apps/web` — the single-page app

React 18 + Vite + TypeScript. TanStack Query owns server state, TanStack Router owns the URL.
The design tokens are `src/theme/tokens.css`, copied verbatim from `docs/design/tokens.css`
(decision "A + D") — do not edit them here; edit the source and copy again.

```bash
npm install
npm run dev        # http://localhost:5173, /api proxied to http://localhost:8000
npm run test       # vitest
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
npm run build      # tsc --build && vite build
npm run e2e        # playwright
```

## Rules that are enforced, not just agreed

* **No business logic here.** Scoring, matching, eligibility and thresholds are server-side
  (`packages/scoring`). `eslint.config.js` blocks the import; the live evaluation screen calls
  `POST /applications/{id}/compute` on every keystroke instead of computing anything locally.
* **Every string is bilingual.** `src/i18n/az.json` and `en.json` are seeded from the approved
  prototype and carry identical key sets — `src/i18n/i18n.test.ts` fails the build if they drift.
  Azerbaijani is the default; the choice is stored per browser.
* **Both themes ship.** `data-theme` on `<html>` selects light or dark; the default follows the
  operating system.

## Layout

```
src/app/          shell, router, navigation model (the 34-screen inventory)
src/components/   rail, topbar, shared primitives
src/features/     auth · vendor · manager · admin — one folder per screen group
src/api/          the typed client; the generated client lands next to it in phase 1F
src/i18n/         az.json, en.json, provider
src/theme/        tokens.css (copied), global.css, theme provider
e2e/              Playwright specs
```

## `preview/` — the no-npm fallback

`preview/` renders the same shell without React or Vite, from the same `theme/global.css` and the
same `i18n/*.json`. It exists because the build host for phase 0 could not reach the npm registry
(`docs/DECISIONS.md` ADR-005), and `make web` falls back to serving it so the layout can still be
reviewed. It is excluded from the bundle, from ESLint and from `tsc`. Once `npm install`
succeeds, `make web` runs Vite and the preview is never used again.

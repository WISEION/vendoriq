#!/usr/bin/env bash
# `make web`.
#
# Normal path: install the dependencies once and run Vite.
# Fallback: on a host where the npm registry is unreachable (this build host — see
# docs/DECISIONS.md ADR-005) there is no Vite to run, so we serve apps/web with a static
# server. The fallback renders the same shell from the same tokens.css and the same
# i18n dictionaries; only the framework is absent.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/web" && pwd)"
PORT="${WEB_PORT:-5173}"
cd "$WEB_DIR"

if [ -d node_modules ]; then
  exec npm run dev -- --port "$PORT"
fi

echo "apps/web/node_modules is missing — installing…"
if npm install --no-audit --no-fund; then
  exec npm run dev -- --port "$PORT"
fi

cat >&2 <<EOF

  npm install failed (the registry is not reachable from this host).
  Serving the dependency-free shell preview instead — same layout, same design tokens,
  same AZ/EN dictionaries, no React/Vite.

  Open: http://localhost:${PORT}/preview/
  Run 'make web' again on a host with npm access to get the real dev server.

EOF
exec python3 -m http.server "$PORT" --bind 127.0.0.1

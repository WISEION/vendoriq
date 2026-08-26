"""FastAPI application factory.

Routers are mounted under ``API_PREFIX`` (``/api``) so one origin serves the SPA and the
API behind Caddy, exactly as the Vite dev proxy does locally. ``/health`` is additionally
mounted at the root because that is where a container health check looks.

Every contract tag has a router module and a mount from phase 2 onward; the phase-2 ones
start empty and are filled by the task that owns them. Their operations already have
permission matrix entries, so adding a handler does not require rethinking who may call it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, PlainTextResponse

from . import __version__
from .config import get_settings
from .errors import install_error_handlers
from .openapi import contract_yaml, load_contract
from .routers import (
    admin,
    auth,
    cycles,
    evaluations,
    events,
    integrations,
    intel,
    portal,
    projects,
    scoring_models,
    storage,
    vendors,
)
from .schemas import Health

#: Mounted under the API prefix, in contract-tag order.
#:
#: Every phase-2 router is mounted from the start, empty until its owner fills it in. That
#: keeps this list out of seven parallel diffs: a worker adds handlers to its own module and
#: never edits this file, so no mount can be lost to a concurrent write.
FEATURE_ROUTERS = (
    auth.router,
    vendors.router,
    portal.router,
    evaluations.router,
    cycles.router,
    projects.router,
    scoring_models.router,
    intel.router,
    integrations.router,
    admin.router,
    events.router,
    storage.router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-CSRF-Token", "X-API-Key"],
        expose_headers=["X-Dev-TOTP"],
    )
    install_error_handlers(app)

    def contract() -> dict[str, Any]:
        return load_contract()

    # The published schema is the hand-written contract, not a generated one (ADR-006).
    app.openapi = contract  # type: ignore[method-assign]

    @app.get("/health", tags=["health"])
    @app.get(f"{settings.api_prefix}/health", tags=["health"])
    def health() -> Health:
        """Liveness probe — also reports which modes the process is running in."""
        return Health(
            status="ok",
            version=__version__,
            app_env=settings.app_env,
            auth_mode=settings.auth_mode,
            storage_backend=settings.storage_backend,
        )

    for router in FEATURE_ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)

    @app.get(f"{settings.api_prefix}/openapi.json", include_in_schema=False)
    def openapi_json() -> dict[str, Any]:
        return load_contract()

    @app.get(f"{settings.api_prefix}/openapi.yaml", include_in_schema=False)
    def openapi_yaml() -> PlainTextResponse:
        return PlainTextResponse(contract_yaml(), media_type="application/yaml")

    @app.get(f"{settings.api_prefix}/docs", include_in_schema=False)
    def docs() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=f"{settings.api_prefix}/openapi.json",
            title=f"{settings.app_name} API",
        )

    @app.get(f"{settings.api_prefix}/redoc", include_in_schema=False)
    def redoc() -> HTMLResponse:
        return get_redoc_html(
            openapi_url=f"{settings.api_prefix}/openapi.json",
            title=f"{settings.app_name} API",
        )

    return app


app = create_app()

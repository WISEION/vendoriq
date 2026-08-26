"""HTTP routers.

One module per contract tag, except where a tag is split between two phase-2 tasks: the
``applications`` tag is served by ``portal`` (the vendor's own application) and
``evaluations`` (the officer's and the commission's side of it), because those are two
owners and one file cannot have two.
"""

from __future__ import annotations

from . import (
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

__all__ = [
    "admin",
    "auth",
    "cycles",
    "evaluations",
    "events",
    "integrations",
    "intel",
    "portal",
    "projects",
    "scoring_models",
    "storage",
    "vendors",
]

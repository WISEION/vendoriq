"""Business services. Routers call these; nothing here knows about HTTP.

Two invariants hold across the whole package and are the reason it exists as a layer:

1. **Every mutation writes an audit event** (CONTRIBUTING, definition of done §6) in the
   same transaction as the change it describes.
2. **Every value a source reported is an observation**, never a mutable column (ADR-004).
"""

from __future__ import annotations

from . import (
    accounts,
    applications,
    audit,
    auth,
    categories,
    contacts,
    documents,
    events,
    mail,
    observations,
    settings_store,
    state_machine,
    users,
    vendors,
)

__all__ = [
    "accounts",
    "applications",
    "audit",
    "auth",
    "categories",
    "contacts",
    "documents",
    "events",
    "mail",
    "observations",
    "settings_store",
    "state_machine",
    "users",
    "vendors",
]

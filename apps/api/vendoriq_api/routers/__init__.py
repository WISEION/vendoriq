"""HTTP routers, one module per contract tag."""

from __future__ import annotations

from . import admin, auth, events, storage, vendors

__all__ = ["admin", "auth", "events", "storage", "vendors"]

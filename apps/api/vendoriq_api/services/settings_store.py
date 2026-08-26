"""Organisation settings — every threshold in spec §11 is a row, not a constant.

Stored as one ``setting`` row per group (``matching``, ``qualification``, ``freshness``,
``notifications``, ``organisation``) so a group reads and writes atomically and the API
shape in the contract is the storage shape. Unknown keys are rejected: a typo that silently
creates ``capacity_ration`` would leave matching running on the default forever.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Setting
from . import audit

#: The defaults are the values spec §11.2 calls "defaults for discussion" — they are here,
#: in data, precisely so the discussion does not require a deployment.
DEFAULTS: dict[str, dict[str, Any]] = {
    "matching": {
        "strong_min": 2,
        "capacity_ratio": 0.40,
        "supplier_turnover_divisor": 4.0,
        "default_min_class": "C",
    },
    "qualification": {
        "validity_months": 12,
        "pass_mark": 70,
        "tax_clearance_validity_months": 3,
    },
    "freshness": {
        "financials_months": 15,
        "headcount_months": 12,
        "stale_profile_days": 90,
    },
    "notifications": {
        "expiry_reminder_days": [30, 7],
        "expiring_window_days": 60,
        "email_enabled": True,
    },
    "organisation": {
        "name": "Uni Ko QSC — commercial department",
        "default_locale": "az",
        "currency": "AZN",
    },
}

#: Field-code prefix → freshness window, derived from the ``freshness`` group. Used by the
#: stale-profile scan and by the vendor detail's ``stale_fields``.
FRESHNESS_PREFIXES = {"B": "financials_months", "E": "headcount_months"}


def all_settings(session: Session) -> dict[str, dict[str, Any]]:
    """Defaults overlaid with whatever has been stored — never a partial group."""
    merged = {group: dict(values) for group, values in DEFAULTS.items()}
    for row in session.scalars(select(Setting)):
        if row.key in merged and isinstance(row.value, dict):
            merged[row.key].update(row.value)
    return merged


def group(session: Session, name: str) -> dict[str, Any]:
    return all_settings(session).get(name, {})


def freshness_windows(session: Session) -> dict[str, int]:
    """``{"B": 456, "E": 365}`` — months converted to the days the resolver compares in."""
    values = group(session, "freshness")
    return {
        prefix: int(float(values.get(key, DEFAULTS["freshness"][key])) * 30.4375)
        for prefix, key in FRESHNESS_PREFIXES.items()
    }


def update(uow: UnitOfWork, patch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Apply a partial ``Settings``. Unknown group or key → 422 (contract)."""
    unknown_groups = [name for name in patch if name not in DEFAULTS]
    if unknown_groups:
        raise ApiError(
            422, "validation_error", "Unknown settings group.", {"groups": unknown_groups}
        )
    before = all_settings(uow.session)
    for name, values in patch.items():
        if not isinstance(values, dict):
            raise ApiError(422, "validation_error", f"Settings group {name!r} must be an object.")
        unknown_keys = [key for key in values if key not in DEFAULTS[name]]
        if unknown_keys:
            raise ApiError(
                422,
                "validation_error",
                f"Unknown key in settings group {name!r}.",
                {"group": name, "keys": unknown_keys},
            )
        row = uow.session.get(Setting, name)
        if row is None:
            row = Setting(key=name, value={})
            uow.session.add(row)
        # Reassign rather than mutate: SQLAlchemy does not track in-place JSONB edits.
        row.value = {**row.value, **values}
    uow.flush()
    after = all_settings(uow.session)
    audit.record(
        uow,
        entity_type="setting",
        entity_id=None,
        action="update",
        before={name: before[name] for name in patch},
        after={name: after[name] for name in patch},
    )
    return after

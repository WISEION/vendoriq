"""Autosave: application answers as ``portal`` observations, completion and computed cells.

Answers are not application-scoped in the data model — every field observation belongs to
the *vendor* (spec §7: "profile data is stored once and reused across cycles"), so a patch
here writes the same append-only observations ``GET /vendors/{id}`` and the evaluation screen
already read (``services/observations.py``). This module adds the portal's own rules on top:
which cells count towards completion, the two auto-calculated cells the form shows read-only,
and opening the application on first save.
"""

from __future__ import annotations

from typing import Any

from vendoriq_excel_import.catalog import FIELD_CATALOG
from vendoriq_scoring import derive_raw, to_number

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, Vendor
from ..models.enums import ApplicationStatus, ObservationSource, UserRole
from . import applications as applications_service
from . import observations as observations_service

__all__ = ["completion_pct", "computed_fields", "is_present", "patch"]

#: Codes the vendor actually types into. ``calc`` cells (``B.4``, ``B.8``) are display-only —
#: the server computes them, so they do not count towards "did the vendor answer this".
_ANSWERABLE_CODES: tuple[str, ...] = tuple(
    code for code, field in FIELD_CATALOG.items() if field.kind != "calc"
)

#: An application past filling is either under review or decided; the vendor's route back to
#: editing is ``information_requested``, not a silent re-open of a status the officer moved
#: on from (spec §9).
_EDITABLE_STATUSES = frozenset(
    {
        ApplicationStatus.INVITED,
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.INFORMATION_REQUESTED,
    }
)

#: Tokens that read as "no answer" even though the cell is not literally empty — the "no
#: expiry" literal and the various empty-cell spellings the Excel importer already tolerates
#: (brief §1.11). Kept in step with ``vendoriq_scoring.derive._is_present``.
_BLANK_TOKENS = frozenset({"müddətsiz", "muddetsiz", "—", "-", "n/a"})


def is_present(value: Any) -> bool:
    """Whether a cell reads as answered — a table counts once it has at least one row."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.casefold() not in _BLANK_TOKENS
    if isinstance(value, list | tuple):
        return len(value) > 0
    return True


def completion_pct(profile: dict[str, Any]) -> float:
    """Share of the answerable catalogue codes the vendor's current profile has filled."""
    if not _ANSWERABLE_CODES:
        return 0.0
    answered = sum(1 for code in _ANSWERABLE_CODES if is_present(profile.get(code)))
    return round(100 * answered / len(_ANSWERABLE_CODES), 1)


def computed_fields(profile: dict[str, Any], vendor_type: str) -> dict[str, float | None]:
    """Server-computed cells the form shows read-only — never recomputed in the browser.

    ``derive_raw`` (``packages/scoring``) is the single source for the scoring engine's raw
    indicators: average turnover, completed/ongoing project counts and the largest project
    value, permanent staff and engineer headcounts. Two more join it under the *form's own*
    codes (Appendix A), because the Excel sheet names them differently from the criterion
    they feed: ``B.4`` "3-year average (auto)" is exactly ``derive_raw``'s raw indicator
    ``B.1``, and ``B.8`` "Current ratio (auto)" (current assets over current liabilities) has
    no scoring-engine equivalent at all — it is a form convenience only.
    """
    kind = "sup" if vendor_type == "sup" else "sub"
    derived = derive_raw(profile, kind)  # type: ignore[arg-type]
    fields: dict[str, float | None] = {
        code: (float(value) if value is not None else None) for code, value in derived.items()
    }
    if "B.1" in fields:
        fields["B.4"] = fields["B.1"]
    fields["B.8"] = _current_ratio(profile)
    return fields


def _current_ratio(profile: dict[str, Any]) -> float | None:
    assets, liabilities = profile.get("B.6"), profile.get("B.7")
    if not is_present(assets) or not is_present(liabilities):
        return None
    denominator = to_number(liabilities)
    if denominator == 0:
        return None
    return round(to_number(assets) / denominator, 2)


def patch(
    uow: UnitOfWork,
    application: Application,
    vendor: Vendor,
    answers: dict[str, Any],
    *,
    role: UserRole | None,
) -> None:
    """Write one ``portal`` observation per answered field code (never a rewrite, ADR-004).

    The vendor opening the form is what starts it (spec §9): the first save against an
    ``invited`` application moves it to ``in_progress``, the same move ``POST
    /vendors/{id}/invite`` … ``transition`` already performs for an Excel intake.
    """
    if application.status not in _EDITABLE_STATUSES:
        raise ApiError(
            409,
            "conflict",
            "Answers cannot be edited once the application has moved past filling (spec §9).",
            {"status": application.status.value},
        )
    if answers:
        observations_service.record_many(uow, vendor.id, answers, source=ObservationSource.PORTAL)
    if application.status is ApplicationStatus.INVITED:
        applications_service.transition(uow, application, ApplicationStatus.IN_PROGRESS, role=role)

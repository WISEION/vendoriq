"""The document checklist as the API sees it (spec Appendix B, brief §1.1).

The rows live in ``vendoriq_excel_import.catalog`` because the parser needs them to read the
checklist sheet; the API depends on that package already, so it reads them from there rather
than keeping a second copy that would drift. What this module adds is the API's own rules
about those rows: which codes a supplier is asked for, and the expiry arithmetic.
"""

from __future__ import annotations

from datetime import date, timedelta

from vendoriq_excel_import.catalog import DOCUMENT_CATALOG, DocumentDef

from .models.enums import DocumentExpiryState, DocumentStatus, VendorType

__all__ = [
    "A05_VALIDITY_MONTHS",
    "DEFAULT_EXPIRING_WINDOW_DAYS",
    "DOCUMENT_CATALOG",
    "MANDATORY_DOCUMENT_CODES",
    "SUPPLIER_DOCUMENT_CODES",
    "DocumentDef",
    "checklist_for",
    "days_to_expiry",
    "expiry_state",
    "resolve_expiry",
]

#: Spec §7 / brief §1.5: the tax clearance certificate is valid three months from issue.
A05_VALIDITY_MONTHS = 3
#: "Expiring" window used by the reminder jobs and the intelligence screens (spec §12).
DEFAULT_EXPIRING_WINDOW_DAYS = 60

MANDATORY_DOCUMENT_CODES: tuple[str, ...] = tuple(
    code for code, item in DOCUMENT_CATALOG.items() if item.mandatory
)

#: Suppliers are asked for the same checklist as subcontractors, A-01 … G-02 (orchestrator
#: decision, phase 1B). H-01/H-02 — declaration and stamped form — apply to both, so the
#: only difference is that the supplier model evidences different criteria against the same
#: codes; there is no separate supplier catalogue to keep in sync.
SUPPLIER_DOCUMENT_CODES: tuple[str, ...] = tuple(DOCUMENT_CATALOG)


def checklist_for(vendor_type: VendorType) -> tuple[DocumentDef, ...]:
    """Every catalogue row a vendor of this type is asked for, in code order."""
    if vendor_type is VendorType.SUP:
        return tuple(DOCUMENT_CATALOG[code] for code in SUPPLIER_DOCUMENT_CODES)
    return tuple(DOCUMENT_CATALOG.values())


def _add_months(start: date, months: int) -> date:
    """Calendar months, clamped to the end of the target month (31 Jan + 1 → 28/29 Feb)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Day 28 always exists; step forward from there to the real last day of the month.
    last_day = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


def resolve_expiry(code: str, issue_date: date | None, expiry_date: date | None) -> date | None:
    """The expiry the system stores, whatever the client sent.

    ``A-05`` is the one document whose validity is a rule rather than a field on the paper:
    three months from issue, always (spec §7). A client that sends its own expiry for A-05 is
    overridden rather than rejected — the vendor is copying a date off a certificate that
    does not print one.
    """
    if code == "A-05":
        if issue_date is None:
            return None
        return _add_months(issue_date, A05_VALIDITY_MONTHS)
    return expiry_date


def days_to_expiry(expiry_date: date | None, *, today: date | None = None) -> int | None:
    """Negative once expired; ``None`` for a document that never expires ("Müddətsiz")."""
    if expiry_date is None:
        return None
    return (expiry_date - (today or date.today())).days


def expiry_state(
    status: DocumentStatus,
    expiry_date: date | None,
    *,
    today: date | None = None,
    window_days: int = DEFAULT_EXPIRING_WINDOW_DAYS,
) -> DocumentExpiryState:
    """valid | expiring | expired | missing | perm.

    ``not_applicable`` and ``in_preparation`` are both "not on file" as far as expiry is
    concerned: there is no document to expire, and the reminder jobs must not chase one.
    """
    if status is not DocumentStatus.UPLOADED:
        return DocumentExpiryState.MISSING
    if expiry_date is None:
        return DocumentExpiryState.PERM
    remaining = days_to_expiry(expiry_date, today=today)
    assert remaining is not None  # expiry_date is not None on this branch
    if remaining < 0:
        return DocumentExpiryState.EXPIRED
    if remaining <= window_days:
        return DocumentExpiryState.EXPIRING
    return DocumentExpiryState.VALID

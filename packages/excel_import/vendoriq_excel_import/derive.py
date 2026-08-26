"""Raw indicators for the import preview.

Two namespaces share the same letters and it is easy to confuse them. The *form* codes
(spec Appendix A) are questions: ``A.1`` is the company's name, ``A.11`` is "do you hold a
construction licence". The *raw indicator* codes (`sub-4`) are what the scoring engine
consumes: ``A.1`` is the licence rubric, ``A.2`` is years in operation.

The translation itself belongs to the engine — ``vendoriq_scoring.derive_raw`` — and this
module only adapts the importer's output to its input, so there is exactly one place where
"three turnovers become an average" is written down. What this module adds is the *year* to
count against: the engine defaults to today, the importer passes the date the form itself
carries, so a fixture derives the same numbers in every year.
"""

from __future__ import annotations

from typing import Any, Literal

from vendoriq_scoring import derive_raw

from .normalise import parse_iso

VendorType = Literal["sub", "sup", "both"]


def derive_indicators(
    answers: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
    meta: dict[str, Any],
    vendor_type: VendorType = "sub",
) -> dict[str, float | None]:
    """Raw indicators for ``vendoriq_scoring.score``, keyed by criterion code.

    Only the indicators the form can *state* are produced. Every other criterion is a rubric
    the officer fills in on the evaluation screen, and it stays absent rather than defaulting
    to zero — an absent criterion and a criterion scored zero mean different things to a
    human, even though the engine coerces both to 0.
    """
    if not answers:
        # An unfilled template derives nothing. Without this, its three empty tables would
        # be read as "this vendor has no ongoing projects and no references" — a claim the
        # blank form never made.
        return {}

    year = reference_year(meta)
    combined: dict[str, Any] = {**answers, **tables}
    raw = derive_raw(combined, vendor_type, current_year=year)
    return dict(raw)


def reference_year(meta: dict[str, Any]) -> int | None:
    """The year to count "years in operation" against: when the form was issued.

    ``None`` when the form carries no date at all, in which case the engine falls back to
    the current year — the only place in this package where a clock can be involved.
    """
    for key in ("issued_on", "due_on"):
        parsed = parse_iso(meta.get(key))
        if parsed is not None:
            return parsed.year
    return None

"""Turn application answers into the raw indicators the engine scores (brief §1.4).

The application form asks the vendor 100+ questions; the scoring model has 24 criteria.
This module is the bridge, and it is deliberately thin: it only derives what the form
*states as fact* (turnovers, project tables, headcounts) plus the Yes/No answers that
pre-fill a rubric cell. Judgement criteria — "equipment & tools", "accident record" —
stay absent from the map and are filled by the officer on the evaluation screen against
the uploaded evidence.

The Yes/No mappings are **pre-fills, not verdicts**. A vendor who ticks "yes" starts at
rubric 3; the officer lowers it after checking the document. That is why a "no" maps to
0 rather than being left absent: absent and 0 score the same, but 0 is a statement the
officer can see and override.

Pure: no clock, no I/O. The one time-dependent rule — years in operation — takes the
current year as an optional argument so a re-score of a past cycle stays reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from .numbers import parse_year, to_number
from .types import AnswerMap, RawIndicators, VendorTypeName

__all__ = ["YES_NO_PREFILL_SUB", "YES_NO_PREFILL_SUP", "derive_raw", "is_yes"]

#: Answers that read as "yes" in either language, plus the shapes Excel produces.
_YES_TOKENS = frozenset(
    {
        "yes", "y", "true", "1", "1.0", "✓", "x",
        "bəli", "beli", "bali", "hə", "he", "var", "hə/var",
    }
)  # fmt: skip

#: Keys a project table row may use for the contract value, most specific first.
_VALUE_KEYS = ("value", "value_azn", "amount", "dəyər", "deyer", "sum", "məbləğ")

#: Form Yes/No question → the ``sub-4`` rubric criterion it pre-fills (brief §1.4).
#: Several map many-to-one: F.5 (ISO 14001) and F.8 (ISO 45001) both feed criterion F.2,
#: which is literally named "ISO 14001 / 45001" — either certificate satisfies it.
YES_NO_PREFILL_SUB: dict[str, str] = {
    "A.11": "A.1",  # construction licence held?          → licence (KO)
    "A.15": "A.4",  # tax clearance, last 3 months?       → tax clearance (KO)
    "F.1": "F.1",  # HSE policy document?                → HSE policy & plan (KO)
    "C.1": "C.4",  # ISO 9001 held?                      → ISO 9001
    "B.9": "B.3",  # bank credit line?                   → bank credit line
    "B.12": "B.4",  # audited in the last 3 years?        → audited statements
    "E.12": "E.3",  # full-time HSE specialist?           → HSE specialist
    "G.1": "G.1",  # professional liability insurance?   → liability insurance
    "F.5": "F.2",  # ISO 14001?                          → ISO 14001 / 45001
    "F.8": "F.2",  # ISO 45001?                          → ISO 14001 / 45001
}

#: The same idea for ``sup-1``, restricted to questions that exist on the shared form and
#: whose supplier criterion means the same thing. The supplier form has no question for
#: manufacturer authorisation (C.3, a KO) or lead time (D.3) yet — see the open question
#: in ``packages/scoring/README``: those two are entered by the officer.
YES_NO_PREFILL_SUP: dict[str, str] = {
    "A.11": "A.1",  # registration / trade permit (KO)
    "A.15": "A.4",  # tax clearance (KO)
    "B.9": "B.3",  # bank credit line
    "B.12": "B.4",  # audited statements
    "C.1": "F.1",  # ISO 9001 — group F in the supplier model, not group C
}


def is_yes(value: object) -> bool:
    """Whether a Yes/No cell reads as "yes" in Azerbaijani or English."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value == 1
    if isinstance(value, str):
        return value.strip().casefold() in _YES_TOKENS
    return False


def derive_raw(
    answers: AnswerMap,
    vendor_type: VendorTypeName,
    *,
    current_year: int | None = None,
) -> RawIndicators:
    """Map application answers (by field-catalogue code) onto raw indicators.

    ``answers`` is keyed by the codes of spec Appendix A; table questions (``C.t1``,
    ``C.t2``, ``G.t1``) carry a list of row mappings. Values arrive already normalised by
    the importer but this function still tolerates the raw shapes (brief §1.11): dates as
    text or datetime, ``"85%"`` beside ``0.95``, multi-value cells, ``"Müddətsiz"``.

    Only indicators the form can *state* are returned. Rubric criteria that need an
    officer's judgement are absent, and absent means 0 to :func:`score` — never an error.
    """
    year = current_year if current_year is not None else date.today().year
    supplier = vendor_type == "sup"
    raw: RawIndicators = {}

    # A.2 — years in operation, from the year of registration (form A.4).
    registered = parse_year(answers.get("A.4"))
    if registered is not None:
        raw["A.2"] = max(year - registered, 0)

    # B.1 — mean of the three declared annual turnovers, blanks ignored.
    turnovers = [
        to_number(answers[code]) for code in ("B.1", "B.2", "B.3") if _is_present(answers.get(code))
    ]
    if turnovers:
        raw["B.1"] = sum(turnovers) / len(turnovers)

    # B.2 — equity (form B.5).
    if _is_present(answers.get("B.5")):
        raw["B.2"] = to_number(answers["B.5"])

    completed = _rows(answers.get("C.t1"))
    ongoing = _rows(answers.get("C.t2"))
    references = _rows(answers.get("G.t1"))

    if supplier:
        # The supplier model counts references in G.1; the subcontractor model in G.2.
        raw["G.1"] = len(references)
    else:
        raw["C.1"] = len(completed)  # completed projects, last 5 years
        raw["C.2"] = max((_row_value(row) for row in completed), default=0.0)
        raw["C.3"] = len(ongoing)  # ongoing projects — a workload curve, not a count of merit
        raw["G.2"] = len(references)

        # E.1 permanent staff, E.2 engineering headcount (form E.4…E.8: chief, civil,
        # architects, electrical, MEP). Form row E.9 is *technicians and foremen*, who are
        # not engineers, so it is excluded — ADR-008.
        if _is_present(answers.get("E.1")):
            raw["E.1"] = to_number(answers["E.1"])
        engineer_rows = [f"E.{n}" for n in range(4, 9)]
        if any(_is_present(answers.get(code)) for code in engineer_rows):
            raw["E.2"] = sum(to_number(answers.get(code)) for code in engineer_rows)

    prefill = YES_NO_PREFILL_SUP if supplier else YES_NO_PREFILL_SUB
    for question, criterion in prefill.items():
        if question not in answers:
            continue
        points = 3.0 if is_yes(answers[question]) else 0.0
        # Many-to-one (F.5 / F.8 → F.2): the better answer wins.
        raw[criterion] = max(points, to_number(raw.get(criterion)))

    return raw


def _is_present(value: object) -> bool:
    """A cell the vendor actually answered — blank and "no expiry" do not count."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.casefold() not in {"müddətsiz", "muddetsiz", "—", "-", "n/a"}
    return True


def _rows(value: object) -> list[object]:
    """Rows of a table answer, dropping the empty rows a spreadsheet always carries."""
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [row for row in value if _row_has_content(row)]


def _row_has_content(row: object) -> bool:
    if isinstance(row, dict):
        return any(_is_present(cell) for cell in row.values())
    if isinstance(row, Sequence) and not isinstance(row, str | bytes):
        return any(_is_present(cell) for cell in row)
    return _is_present(row)


def _row_value(row: object) -> float:
    """The contract value of one project row, whatever the importer called the column."""
    if isinstance(row, dict):
        for key in _VALUE_KEYS:
            if key in row:
                return to_number(row[key])
        return 0.0
    if isinstance(row, Sequence) and not isinstance(row, str | bytes):
        # Positional row (the seed's ``detail.projects``): the value is the largest number
        # that is not a year — years and counts never reach a project's price.
        return max(_numeric_cells(row), default=0.0)
    return 0.0


def _numeric_cells(row: Iterable[object]) -> list[float]:
    numbers = [to_number(cell) for cell in row if isinstance(cell, int | float)]
    return [n for n in numbers if not 1800 <= n <= 2200]

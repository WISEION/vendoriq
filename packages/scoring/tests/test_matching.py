"""Matching: who can build a package, and can the project be bid at all (spec §11).

The regression case at the bottom is the real one — the TQS-238 tender as it stands in
the seed. It must come out NO-GO at 96 % coverage, because nobody prequalified carries
the flooring category. That single 600 000 AZN hole in a 14.7 M AZN scope is exactly the
decision the commission is meant to see before it commits to a bid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from vendoriq_scoring import (
    CandidateInput,
    MatchParams,
    PackageInput,
    ProjectInput,
    match_package,
    match_project,
)

SEED = Path(__file__).resolve().parents[3] / "seed" / "data.json"

# A vendor good enough to be strong anywhere: class A, 5 M largest project, ISO 9001+45001.
STRONG_RAW: dict[str, Any] = {
    "A.1": 3, "A.2": 20, "A.3": 3, "A.4": 3,
    "B.1": 20_000_000, "B.2": 5_000_000, "B.3": 3, "B.4": 3,
    "C.1": 20, "C.2": 5_000_000, "C.3": 5, "C.4": 3,
    "D.1": 3, "D.2": 3, "D.3": 3,
    "E.1": 200, "E.2": 30, "E.3": 3, "E.4": 3,
    "F.1": 3, "F.2": 3, "F.3": 3,
    "G.1": 3, "G.2": 10,
}  # fmt: skip


def vendor(vendor_id: str, **overrides: Any) -> CandidateInput:
    """A prequalified class-A subcontractor in category ``facade``, unless told otherwise."""
    raw = {**STRONG_RAW, **overrides.pop("raw", {})}
    base: dict[str, Any] = {
        "id": vendor_id,
        "legal_name": f"{vendor_id} MMC",
        "vendor_type": "sub",
        "category_codes": ["facade"],
        "is_prequalified": True,
        "raw": raw,
        "model_version": "sub-4",
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def package(**overrides: Any) -> PackageInput:
    base: dict[str, Any] = {
        "id": "pk1",
        "category_code": "facade",
        "estimated_value": 4_500_000,
        "min_class": "B",
        "required_certs": [],
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


# ------------------------------------------------------------------- the four states


def test_two_strong_candidates_make_a_package_go() -> None:
    result = match_package(package(), [vendor("V1"), vendor("V2")])
    assert result.state == "go"
    assert len(result.strong) == 2
    assert result.gap is None
    assert result.package_id == "pk1"


def test_one_strong_candidate_is_only_conditional() -> None:
    """Single-source is a risk, not a plan — the second bidder is what makes it a tender."""
    result = match_package(package(), [vendor("V1")])
    assert result.state == "cond"
    assert result.gap == "too_few_strong"


def test_no_vendor_in_the_category_is_no_go() -> None:
    result = match_package(package(category_code="flooring"), [vendor("V1")])
    assert result.state == "nogo"
    assert result.candidates == []
    assert result.gap == "no_vendor_in_category"


def test_vendors_in_the_category_but_none_prequalified_is_no_go() -> None:
    result = match_package(package(), [vendor("V1", is_prequalified=False)])
    assert result.state == "nogo"
    assert result.gap == "no_prequalified_vendor"
    assert result.candidates[0].reasons == ["not_prequalified"]
    assert result.candidates[0].eligible is False


def test_the_strong_minimum_is_a_setting_not_a_constant() -> None:
    one_is_enough = MatchParams(strong_min=1)
    assert match_package(package(), [vendor("V1")], one_is_enough).state == "go"
    assert (
        match_package(package(), [vendor("V1"), vendor("V2")], MatchParams(strong_min=3)).state
        == "cond"
    )


# ------------------------------------------------------------------------- capacity


def test_capacity_fit_is_forty_percent_of_the_package_value() -> None:
    """A 4.5 M package needs a 1.8 M track record. 1 799 999 is not a rounding error."""
    at_the_line = vendor("V1", raw={"C.2": 1_800_000})
    just_under = vendor("V2", raw={"C.2": 1_799_999})
    result = match_package(package(), [at_the_line, just_under])
    fits = {candidate.vendor_id: candidate.capacity_fit for candidate in result.candidates}
    assert fits == {"V1": True, "V2": False}


def test_a_small_but_eligible_vendor_is_conditional_not_excluded() -> None:
    """Capacity blocks *strength*, never eligibility — a small firm can take part of it."""
    small = vendor("V1", raw={"C.2": 100_000})
    result = match_package(package(), [small, vendor("V2", raw={"C.2": 100_000})])
    assert [c.eligible for c in result.candidates] == [True, True]
    assert result.strong == []
    assert result.state == "cond"
    assert result.gap == "capacity_too_small"


def test_a_class_c_vendor_with_capacity_is_eligible_but_never_strong() -> None:
    """The gap is the class, not the size — only A and B count towards a GO."""
    class_c = vendor("V2", raw={**STRONG_RAW, "B.1": 0, "B.2": 0, "C.1": 3, "E.1": 0, "E.2": 0})
    result = match_package(package(min_class="C"), [vendor("V1"), class_c])
    verdicts = {c.vendor_id: (c.score.cls, c.eligible, c.capacity_fit) for c in result.candidates}
    assert verdicts["V2"] == ("C", True, True)
    assert [c.vendor_id for c in result.strong] == ["V1"]
    assert result.state == "cond"
    assert result.gap == "only_class_c"


def test_a_supplier_is_measured_by_turnover_divided_down() -> None:
    """A supplier has no "largest project", so annual turnover ÷ 4 stands in for one."""
    supplier = vendor(
        "S1",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "B.1": 20_000_000, "C.2": 0},
    )
    result = match_package(package(estimated_value=10_000_000), [supplier])
    assert result.candidates[0].capacity_value == pytest.approx(5_000_000)  # 20 M ÷ 4
    assert result.candidates[0].capacity_fit is True  # 5 M >= 40 % of 10 M

    tighter = MatchParams(supplier_turnover_divisor=10)
    stricter = match_package(package(estimated_value=10_000_000), [supplier], tighter)
    assert stricter.candidates[0].capacity_value == pytest.approx(2_000_000)
    assert stricter.candidates[0].capacity_fit is False


def test_the_capacity_ratio_is_a_setting() -> None:
    small = vendor("V1", raw={"C.2": 1_000_000})
    generous = MatchParams(capacity_ratio=0.2)
    assert match_package(package(), [small], generous).candidates[0].capacity_fit is True
    assert match_package(package(), [small]).candidates[0].capacity_fit is False


# --------------------------------------------------------------------- class and KO


def test_a_class_below_the_package_minimum_is_not_eligible() -> None:
    weak = vendor("V1", raw={**STRONG_RAW, "B.1": 0, "C.1": 0, "C.2": 0, "E.1": 0, "E.2": 0})
    result = match_package(package(min_class="B"), [weak])
    assert result.candidates[0].score.cls in {"C", "D", "F"}
    assert result.candidates[0].eligible is False
    assert "class_below_min" in result.candidates[0].reasons
    assert result.gap == "only_class_c"


def test_a_knock_out_makes_a_vendor_ineligible_however_high_the_total() -> None:
    knocked_out = vendor("V1", raw={**STRONG_RAW, "A.1": 0})
    result = match_package(package(), [knocked_out])
    candidate = result.candidates[0]
    assert candidate.score.total >= 90
    assert candidate.score.cls == "KO"
    assert candidate.eligible is False
    assert "ko_failed" in candidate.reasons


def test_class_rank_orders_ko_below_f() -> None:
    from vendoriq_scoring import CLASS_RANK

    assert CLASS_RANK["A"] > CLASS_RANK["B"] > CLASS_RANK["C"] > CLASS_RANK["D"]
    assert CLASS_RANK["D"] > CLASS_RANK["F"] > CLASS_RANK["KO"]
    assert CLASS_RANK["NA"] == CLASS_RANK["KO"] == 0


# ------------------------------------------------------------------------ certificates


def test_a_required_certificate_that_is_missing_blocks_eligibility() -> None:
    """A supplier without ISO 9001 (sup-1 criterion F.1) fails a package that demands it."""
    supplier_raw = {**STRONG_RAW, "C.4": 0, "F.1": 0, "C.3": 3}
    without_iso = vendor("S1", vendor_type="sup", model_version="sup-1", raw=supplier_raw)
    result = match_package(package(required_certs=["iso9001"]), [without_iso])
    assert result.candidates[0].certs_ok is False
    assert result.candidates[0].eligible is False
    assert "certificate_missing" in result.candidates[0].reasons
    assert result.gap == "certificate_missing"


def test_iso_9001_is_satisfied_from_either_model_position() -> None:
    """C.4 for a subcontractor, F.1 for a supplier — the requirement is one certificate."""
    subcontractor = vendor("V1", raw={**STRONG_RAW, "C.4": 3})
    supplier_shaped = vendor(
        "S2",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "C.4": 0, "F.1": 3, "C.3": 3},
    )
    result = match_package(package(required_certs=["iso9001"]), [subcontractor, supplier_shaped])
    assert all(candidate.certs_ok for candidate in result.candidates)


def test_the_iso_9001_check_is_near_inert_for_subcontractors() -> None:
    """A quirk of the reference, ported deliberately and worth knowing about.

    ``iso9001`` is satisfied by ``C.4 > 0 or F.1 > 0``. In ``sub-4`` F.1 is *HSE policy*,
    a knock-out criterion — so any subcontractor that clears KO also "has" ISO 9001 even
    with C.4 at zero. The requirement therefore only ever bites on suppliers today. This
    test exists so the day someone tightens the rule, they see it was intentional first.
    """
    no_iso_but_has_hse = vendor("V1", raw={**STRONG_RAW, "C.4": 0, "F.1": 3})
    result = match_package(package(required_certs=["iso9001"]), [no_iso_but_has_hse])
    assert result.candidates[0].certs_ok is True


def test_iso_45001_reads_criterion_f_2() -> None:
    with_it = vendor("V1", raw={**STRONG_RAW, "F.2": 3})
    without_it = vendor("V2", raw={**STRONG_RAW, "F.2": 0})
    result = match_package(package(required_certs=["iso45001"]), [with_it, without_it])
    ok = {candidate.vendor_id: candidate.certs_ok for candidate in result.candidates}
    assert ok == {"V1": True, "V2": False}


def test_an_unknown_certificate_key_passes() -> None:
    """Informational until a criterion exists for it — it must not silently reject everyone."""
    result = match_package(package(required_certs=["iso27001"]), [vendor("V1")])
    assert result.candidates[0].certs_ok is True


# ---------------------------------------------------------------------------- sorting


def test_candidates_are_sorted_by_total_descending() -> None:
    best = vendor("V1")
    middling = vendor("V2", raw={**STRONG_RAW, "B.1": 600_000, "C.1": 3})
    result = match_package(package(min_class="F"), [middling, best])
    totals = [candidate.score.total for candidate in result.candidates]
    assert totals == sorted(totals, reverse=True)
    assert result.candidates[0].vendor_id == "V1"


def test_a_vendor_outside_the_category_is_not_even_a_candidate() -> None:
    result = match_package(package(), [vendor("V1", category_codes=["mep"])])
    assert result.candidates == []


# ------------------------------------------------------------- project aggregation


def two_packages(*states: str) -> tuple[ProjectInput, list[CandidateInput]]:
    """Build a project whose packages land on the requested states, by category."""
    categories = {"go": "facade", "cond": "steel", "nogo": "flooring"}
    packages = [
        package(id=f"pk{index}", category_code=categories[state], estimated_value=1_000_000)
        for index, state in enumerate(states, start=1)
    ]
    candidates = [
        vendor("G1", category_codes=["facade"]),
        vendor("G2", category_codes=["facade"]),
        vendor("C1", category_codes=["steel"]),  # one strong vendor only → conditional
    ]
    return {"id": "P1", "packages": packages}, candidates


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("go", "go"), "go"),
        (("go", "cond"), "cond"),
        (("cond", "cond"), "cond"),
        (("go", "nogo"), "nogo"),
        (("cond", "nogo"), "nogo"),
        (("nogo", "nogo"), "nogo"),
    ],
)
def test_one_no_go_package_sinks_the_project(states: tuple[str, ...], expected: str) -> None:
    project, candidates = two_packages(*states)
    result = match_project(project, candidates)
    assert result.state == expected
    assert result.recommendation_key == f"m_rec_{expected}"


def test_coverage_is_the_value_share_of_the_packages_that_can_be_filled() -> None:
    project, candidates = two_packages("go", "nogo")
    assert match_project(project, candidates).coverage_pct == 50

    project, candidates = two_packages("go", "cond")
    assert match_project(project, candidates).coverage_pct == 100


def test_a_project_with_no_packages_is_go_at_full_coverage() -> None:
    """Vacuous, but it must not divide by zero on a project someone just created."""
    result = match_project({"id": "P0", "packages": []}, [])
    assert result.state == "go"
    assert result.coverage_pct == 100


def test_the_project_result_carries_the_params_it_used() -> None:
    """The persisted run has to record the thresholds, or last month's run is unreadable."""
    params = MatchParams(strong_min=3, capacity_ratio=0.5, supplier_turnover_divisor=6)
    project, candidates = two_packages("go")
    assert match_project(project, candidates, params).params == params


# ------------------------------------------------------------- TQS-238, the real case


def _seed() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(SEED.read_text(encoding="utf-8"))
    return document


def _seed_candidates() -> list[CandidateInput]:
    seed = _seed()
    rows: list[CandidateInput] = []
    for row in [*seed["vendors"], *seed["suppliers"]]:
        rows.append(
            {
                "id": row["id"],
                "legal_name": row["name"],
                "vendor_type": row["type"],
                "category_codes": row["cats"],
                "is_prequalified": row["status"] == "prequalified",
                "raw": row["raw"],
                "model_version": "sub-4" if row["type"] == "sub" else "sup-1",
            }
        )
    return rows


def _tqs_238() -> ProjectInput:
    project = next(p for p in _seed()["projects"] if p["code"] == "TQS-238")
    return {
        "id": project["id"],
        "packages": [
            {
                "id": pkg["id"],
                "category_code": pkg["cat"],
                "estimated_value": pkg["value"],
                "min_class": pkg["minClass"],
                "required_certs": pkg["certs"],
            }
            for pkg in project["packages"]
        ],
    }


def test_tqs_238_is_no_go_at_ninety_six_percent_coverage() -> None:
    """The regression case from README §4 — that 96 % is a number, not a coincidence."""
    result = match_project(_tqs_238(), _seed_candidates())
    assert result.state == "nogo"
    assert result.coverage_pct == 96
    assert result.recommendation_key == "m_rec_nogo"


def test_the_flooring_package_is_the_hole() -> None:
    """pk5 (flooring, 600 000 AZN): the only vendor carrying the category is rejected."""
    result = match_project(_tqs_238(), _seed_candidates())
    by_id = {pkg.package_id: pkg for pkg in result.packages}

    flooring = by_id["pk5"]
    assert flooring.state == "nogo"
    assert flooring.gap == "no_prequalified_vendor"
    assert [candidate.vendor_id for candidate in flooring.candidates] == ["V07"]
    assert "not_prequalified" in flooring.candidates[0].reasons

    # Every other package can be filled, which is what keeps coverage at 96 %.
    assert {pkg.state for pkg in result.packages if pkg.package_id != "pk5"} == {"go", "cond"}


def test_the_facade_package_goes_on_wesa_and_shield() -> None:
    """pk1 needs class B and ISO 9001 on a 4.5 M scope — V09 (94.7) and V05 (90.3) clear it."""
    result = match_project(_tqs_238(), _seed_candidates())
    facade = next(pkg for pkg in result.packages if pkg.package_id == "pk1")
    assert facade.state == "go"
    assert [candidate.vendor_id for candidate in facade.strong] == ["V09", "V05"]


def test_the_material_packages_are_matched_against_the_supplier_model() -> None:
    """pk6/pk7 are material categories: the candidates are suppliers scored with sup-1."""
    result = match_project(_tqs_238(), _seed_candidates())
    concrete = next(pkg for pkg in result.packages if pkg.package_id == "pk6")
    assert [candidate.vendor_id for candidate in concrete.eligible] == ["S02"]
    assert concrete.state == "cond"  # a single strong supplier is not a tender
    assert concrete.gap == "too_few_strong"


def test_relaxing_the_strong_minimum_would_not_save_tqs_238() -> None:
    """Even at strong_min=1 the project stays NO-GO: flooring has nobody at all."""
    result = match_project(_tqs_238(), _seed_candidates(), MatchParams(strong_min=1))
    assert result.state == "nogo"
    assert result.coverage_pct == 96

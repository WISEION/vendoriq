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
    load_model,
    match_package,
    match_project,
)
from vendoriq_scoring.matching import _certificate_criterion

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


def test_iso_9001_is_read_from_each_models_own_criterion() -> None:
    """C.4 for a subcontractor, F.1 for a supplier — each model's real ISO 9001 cell."""
    subcontractor = vendor("V1", raw={**STRONG_RAW, "C.4": 3, "F.1": 3})
    supplier_shaped = vendor(
        "S2",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "C.4": 0, "F.1": 3, "C.3": 3},
    )
    result = match_package(package(required_certs=["iso9001"]), [subcontractor, supplier_shaped])
    assert all(candidate.certs_ok for candidate in result.candidates)


def test_a_subcontractors_hse_policy_is_not_an_iso_9001_certificate() -> None:
    """ADR-009, the direction that used to let vendors through.

    The prototype read ``C.4 > 0 or F.1 > 0`` for every vendor. In ``sub-4`` F.1 is the
    *HSE policy* knock-out, so every subcontractor that cleared KO also "held" ISO 9001
    with C.4 at zero — the requirement was inert for the entire subcontractor register.
    A subcontractor is now checked on C.4 and nothing else.
    """
    hse_but_no_iso = vendor("V1", raw={**STRONG_RAW, "C.4": 0, "F.1": 3})
    result = match_package(package(required_certs=["iso9001"]), [hse_but_no_iso])
    assert result.candidates[0].certs_ok is False
    assert result.candidates[0].eligible is False
    assert "certificate_missing" in result.candidates[0].reasons


def test_a_supplier_holds_iso_9001_through_f_1_even_with_c_4_empty() -> None:
    """ADR-009, the other direction.

    In ``sup-1`` F.1 *is* ISO 9001 and C.4 is product certificates (CE, GOST, test
    reports). A supplier with the quality-management certificate and no product
    certificates on file still satisfies an ``iso9001`` requirement.
    """
    iso_but_no_product_certs = vendor(
        "S1",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "C.4": 0, "F.1": 3, "C.3": 3},
    )
    result = match_package(package(required_certs=["iso9001"]), [iso_but_no_product_certs])
    assert result.candidates[0].certs_ok is True
    assert "certificate_missing" not in result.candidates[0].reasons


def test_a_supplier_product_certificate_is_not_an_iso_9001_certificate() -> None:
    """The mirror of the subcontractor case: ``sup-1`` C.4 must not stand in for F.1."""
    product_certs_but_no_iso = vendor(
        "S1",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "C.4": 3, "F.1": 0, "C.3": 3},
    )
    result = match_package(package(required_certs=["iso9001"]), [product_certs_but_no_iso])
    assert result.candidates[0].certs_ok is False


def test_iso_45001_reads_criterion_f_2() -> None:
    with_it = vendor("V1", raw={**STRONG_RAW, "F.2": 3})
    without_it = vendor("V2", raw={**STRONG_RAW, "F.2": 0})
    result = match_package(package(required_certs=["iso45001"]), [with_it, without_it])
    ok = {candidate.vendor_id: candidate.certs_ok for candidate in result.candidates}
    assert ok == {"V1": True, "V2": False}


@pytest.mark.parametrize(
    ("version", "cert", "expected_code"),
    [
        ("sub-4", "iso9001", "C.4"),
        ("sub-4", "iso45001", "F.2"),
        ("sup-1", "iso9001", "F.1"),
        ("sup-1", "iso45001", None),  # sup-1 has no ISO 45001 row; F.2 is defects/returns
        ("sub-4", "iso27001", None),
        ("sup-1", "iso27001", None),
    ],
)
def test_the_certificate_criterion_each_model_resolves_to(
    version: str, cert: str, expected_code: str | None
) -> None:
    """Pins the resolution table itself, so a criterion relabel cannot quietly repoint it."""
    assert _certificate_criterion(cert, load_model(version)) == expected_code


def test_a_certificate_is_resolved_against_the_model_the_vendor_was_scored_with() -> None:
    """ADR-011: ``model_version`` decides, not ``vendor_type``.

    The same raw map, the same vendor type, two models — and two answers, because
    ``sub-4`` reads ISO 9001 off C.4 while ``sup-1`` reads it off F.1. A ``both`` vendor
    is the case that forces the question, and the only defensible answer is the rubric
    its score was actually produced with.
    """
    holds_c_4_only = {**STRONG_RAW, "C.4": 3, "F.1": 0, "C.3": 3}
    as_subcontractor = vendor(
        "B1", vendor_type="both", model_version="sub-4", raw={**holds_c_4_only, "F.1": 3}
    )
    as_supplier = vendor("B2", vendor_type="both", model_version="sup-1", raw=holds_c_4_only)

    scored_with_sub_4 = match_package(package(required_certs=["iso9001"]), [as_subcontractor])
    assert scored_with_sub_4.candidates[0].certs_ok is True

    scored_with_sup_1 = match_package(package(required_certs=["iso9001"]), [as_supplier])
    assert scored_with_sup_1.candidates[0].certs_ok is False
    assert scored_with_sup_1.candidates[0].missing_certs == ["iso9001"]


def test_a_certificate_the_model_cannot_evidence_is_not_held() -> None:
    """ADR-011: no criterion, no verification, no certificate.

    ``sup-1`` has no ISO 45001 row at all — F.2 there is the *defect / return record*.
    Passing the requirement would report a check that never ran, and a false positive is
    the dangerous direction: it puts an unverified vendor on a shortlist silently, while
    this false negative is printed on the screen for the manager to overrule.
    """
    supplier = vendor(
        "S1",
        vendor_type="sup",
        model_version="sup-1",
        raw={**STRONG_RAW, "F.2": 3, "C.3": 3},
    )
    result = match_package(package(min_class="F", required_certs=["iso45001"]), [supplier])
    assert result.candidates[0].certs_ok is False
    assert result.candidates[0].eligible is False
    assert result.candidates[0].reasons == ["certificate_missing"]
    assert result.candidates[0].missing_certs == ["iso45001"]
    assert result.state == "nogo"
    assert result.gap == "certificate_missing"


def test_the_missing_certificate_is_named_on_the_candidate_and_the_package() -> None:
    """The gap key says *what* is wrong; ``missing_certs`` says *which* certificate."""
    no_iso = vendor("V1", raw={**STRONG_RAW, "C.4": 0, "F.2": 0})
    result = match_package(package(min_class="F", required_certs=["iso9001", "iso45001"]), [no_iso])
    assert result.candidates[0].missing_certs == ["iso9001", "iso45001"]
    assert result.gap == "certificate_missing"
    assert result.missing_certs == ["iso45001", "iso9001"]  # sorted union across candidates


def test_a_satisfied_requirement_names_nothing() -> None:
    result = match_package(package(required_certs=["iso9001"]), [vendor("V1"), vendor("V2")])
    assert result.state == "go"
    assert result.missing_certs == []
    assert all(candidate.missing_certs == [] for candidate in result.candidates)


def test_an_unknown_certificate_key_is_not_held() -> None:
    """ADR-011 reversed the old "unknown key passes" rule, for the same reason.

    ``iso27001`` has no criterion in any shipped model and no entry in the standards
    table, so nothing about it was ever checked. It is reported missing rather than
    waved through.
    """
    result = match_package(package(required_certs=["iso27001"]), [vendor("V1")])
    assert result.candidates[0].certs_ok is False
    assert result.candidates[0].missing_certs == ["iso27001"]


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


def test_no_material_package_in_the_seed_requires_a_certificate() -> None:
    """The blast radius of ADR-011, pinned so a seed edit has to face it.

    Suppliers can no longer evidence ``iso45001`` at all (``sup-1`` has no such
    criterion), so the day a material package asks for one, every supplier goes
    ineligible and the package turns NO-GO. Today none does: ``iso9001`` is required on
    TQS-238 pk1 (facade) and TQS-301 pk1 (steel), ``iso45001`` on TQS-238 pk3 (MEP) —
    all three are work packages matched against ``sub-4``.
    """
    seed = _seed()
    supplier_categories = {cat for row in seed["suppliers"] for cat in row["cats"]}
    demanding = [
        (project["code"], pkg["id"], pkg["cat"], pkg["certs"])
        for project in seed["projects"]
        for pkg in project["packages"]
        if pkg["certs"]
    ]
    assert demanding == [
        ("TQS-238", "pk1", "facade", ["iso9001"]),
        ("TQS-238", "pk3", "mep", ["iso45001"]),
        ("TQS-301", "pk1", "steel", ["iso9001"]),
    ]
    assert all(category not in supplier_categories for _, _, category, _ in demanding)


def test_the_mep_package_still_matches_on_sub_4_certificates() -> None:
    """pk3 is the seed's only ISO 45001 package, and ADR-011 leaves it exactly as it was.

    It is matched against ``sub-4``, where F.2 carries the standard, so the certificate
    is still evidenced and the package is still CONDITIONAL on one strong vendor —
    nothing about it turns on the supplier-side gap.
    """
    result = match_project(_tqs_238(), _seed_candidates())
    mep = next(pkg for pkg in result.packages if pkg.package_id == "pk3")
    assert mep.state == "cond"
    assert mep.gap == "too_few_strong"
    assert [candidate.vendor_id for candidate in mep.eligible] == ["V13"]
    assert all(candidate.certs_ok for candidate in mep.eligible)
    # V02 submitted a blank form, so the certificate is one of the many things it lacks —
    # the roll-up reports the certificate that blocked *a* candidate, not the package.
    assert mep.missing_certs == ["iso45001"]
    assert [c.vendor_id for c in mep.candidates if c.missing_certs] == ["V02"]


def test_relaxing_the_strong_minimum_would_not_save_tqs_238() -> None:
    """Even at strong_min=1 the project stays NO-GO: flooring has nobody at all."""
    result = match_project(_tqs_238(), _seed_candidates(), MatchParams(strong_min=1))
    assert result.state == "nogo"
    assert result.coverage_pct == 96

"""Officer evaluation, live scoring, decisions and the second-evaluator cross-check.

Everything that turns raw indicators plus rubric cells into points, a total, a knock-out
result and a class goes through :mod:`vendoriq_scoring` — this module never reimplements a
threshold, a rounding rule or a class band (CONTRIBUTING, packages/scoring/README.md). What
lives here is the part the engine cannot know: which application, which model version, whose
rubric cell wins when several sources disagree, and the workflow rules around all of that
(spec §9, §10.3).

**"A locked model version" (task 2B brief).** ``ScoringModel.is_locked`` becomes ``True`` the
moment any application is scored with a version and *stays* true for as long as that version
exists — it is what makes the version safe to keep scoring against, not a reason to refuse
(see ``docs/DECISIONS.md`` ADR-014 and ``test_seed.py``'s own assertion that ``sub-4`` is
locked precisely because 13 real applications use it). Refusing every future evaluation on a
locked version would refuse the entire Rev4 cycle, including the two vendors this task's
acceptance criteria name. What spec §10.3 actually wants withheld is a version the commission
has retired — a model nobody should keep scoring against because a newer one replaced it. This
module therefore refuses on ``ScoringModelStatus.RETIRED``, not on ``is_locked``. Flagged as an
explicit interpretation in the final report for the orchestrator to confirm or correct.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_scoring import score as engine_score
from vendoriq_scoring.types import ClassBand as EngineClassBand
from vendoriq_scoring.types import Criterion as EngineCriterion
from vendoriq_scoring.types import GroupDef as EngineGroupDef
from vendoriq_scoring.types import ModelStatusName, RawIndicators
from vendoriq_scoring.types import ScoringModel as EngineScoringModel

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, Evaluation, QualificationCycle, Vendor
from ..models import ScoringModel as ScoringModelRow
from ..models.enums import (
    ApplicationStatus,
    DecisionKind,
    EventType,
    ScoreClass,
    ScoringModelStatus,
    VendorType,
)
from ..schemas.evaluations import (
    ApplicationDetail,
    ComputeRequest,
    DecisionInput,
    Divergence,
    EvaluationRow,
    RubricInput,
)
from ..schemas.evaluations import (
    Evaluation as EvaluationSchema,
)
from ..schemas.evaluations import (
    ScoreResult as ScoreResultSchema,
)
from ..schemas.evaluations import (
    SecondEvaluation as SecondEvaluationSchema,
)
from ..security.principal import Principal
from . import applications as applications_service
from . import audit, events, observations

__all__ = [
    "VendorHistoryRow",
    "compute",
    "decide",
    "get",
    "get_evaluation",
    "save_evaluation",
    "save_second_evaluation",
    "vendor_history",
]

get = applications_service.get


# ── vendor evaluation history (screen 17) ───────────────────────────────────
@dataclass(frozen=True, slots=True)
class VendorHistoryRow:
    """One application this vendor has had, across every cycle it entered.

    Plain data, not the ``EvaluationSummary`` pydantic schema (``schemas/vendors.py``, task
    2A) — building that response shape is the router's job, same as every other payload
    builder in ``routers/vendors.py``; this only runs the query.
    """

    application_id: uuid.UUID
    cycle_name: str | None
    model_version: str | None
    computed: dict[str, Any] | None
    decision: DecisionKind | None
    decided_at: datetime | None


def vendor_history(session: Session, vendor_id: uuid.UUID) -> list[VendorHistoryRow]:
    """Every application this vendor has had, newest first (screen 17, spec §8).

    Not filtered to decided applications: an application still ``under_review`` belongs in
    the history too, just with ``total``/``cls``/``decision`` left null — the same "unknown
    stays empty, never invented" rule as everywhere else.
    """
    rows = session.execute(
        select(Application, QualificationCycle)
        .join(QualificationCycle, QualificationCycle.id == Application.cycle_id)
        .where(Application.vendor_id == vendor_id)
        .order_by(Application.created_at.desc())
    ).all()
    return [
        VendorHistoryRow(
            application_id=application.id,
            cycle_name=cycle.name,
            model_version=cycle.scoring_model_version,
            computed=application.computed,
            decision=application.decision,
            decided_at=application.decided_at,
        )
        for application, cycle in rows
    ]


# ── model loading ───────────────────────────────────────────────────────────
def _engine_model(session: Session, version: str) -> EngineScoringModel:
    """Build the engine's immutable ``ScoringModel`` from the database row.

    Reading the row rather than ``vendoriq_scoring.load_model`` is deliberate: a version the
    phase-2D model editor creates only ever exists as a database row, and every application
    must be scored against exactly what the commission published, not against whichever of
    the two happens to agree today.
    """
    row = session.get(ScoringModelRow, version)
    if row is None:
        raise ApiError(404, "not_found", f"No such scoring model version {version!r}.")
    criteria = cast(list[EngineCriterion], row.criteria)
    return EngineScoringModel(
        version=row.version,
        vendor_type=row.vendor_type.value,
        name_az=row.name_az,
        name_en=row.name_en,
        status=cast(ModelStatusName, row.status.value),
        pass_mark=float(row.pass_mark),
        validity_months=row.validity_months,
        # ADR-007: the system stores AZN only; the column deliberately does not exist
        # (docs/DECISIONS.md ADR-014) so this is the one place the constant is spelled out.
        currency="AZN",
        # ADR-014: total_max is the sum of the criteria maxima, never a stored column.
        total_max=sum(float(criterion["max"]) for criterion in criteria),
        groups=cast(list[EngineGroupDef], row.groups),
        criteria=criteria,
        classes=cast(list[EngineClassBand], row.classes),
        source=f"scoring_model:{row.version}",
    )


def _model_row_or_404(session: Session, version: str) -> ScoringModelRow:
    row = session.get(ScoringModelRow, version)
    if row is None:
        raise ApiError(404, "not_found", f"No such scoring model version {version!r}.")
    return row


def _cycle(session: Session, application: Application) -> QualificationCycle:
    cycle = session.get(QualificationCycle, application.cycle_id)
    if cycle is None:  # pragma: no cover - FK guarantees this in practice
        raise ApiError(404, "not_found", "The application's cycle no longer exists.")
    return cycle


def _refuse_if_decided(application: Application) -> None:
    if application.decision is not None:
        raise ApiError(
            409,
            "conflict",
            "This application's decision has already been recorded; the evaluation is "
            "immutable from here (spec §10.3).",
            {"decision": application.decision.value},
        )


def _refuse_if_retired(model_row: ScoringModelRow) -> None:
    if model_row.status is ScoringModelStatus.RETIRED:
        raise ApiError(
            409,
            "conflict",
            "This application's scoring model version has been retired and can no longer "
            "accept new scores (spec §10.3).",
            {"model_version": model_row.version, "status": model_row.status.value},
        )


# ── raw indicators ──────────────────────────────────────────────────────────
def _base_raw(session: Session, application: Application, vendor: Vendor) -> dict[str, Any]:
    """Numeric raw indicators before the rubric is laid over them.

    The frozen snapshot once the vendor has submitted (spec §9: "submission freezes a
    raw-indicator snapshot"); the live, current profile before that, run through the same
    :func:`derive_raw` the vendor portal and the register already call — this is not a second
    implementation of the derivation rule, it is the same call.

    **And live again while the application sits in `information_requested`** (3B, finding 4).
    That state exists precisely because a figure was wrong and the vendor has been asked to
    replace it, so the snapshot is stale *by definition* for as long as it lasts. Preferring
    it there showed the officer the number that had already been superseded — spec §5's
    freeze silently defeating spec §9's loop. The snapshot is re-frozen from the corrected
    profile when the review resumes (`services/applications.py::transition`), so this window
    is the only time the two disagree, and during it the live figure is the true one.
    """
    if (
        application.raw_snapshot is not None
        and application.status is not ApplicationStatus.INFORMATION_REQUESTED
    ):
        return dict(application.raw_snapshot)
    from vendoriq_scoring import derive_raw

    profile = observations.current_profile(session, vendor.id)
    kind = "sup" if vendor.type is VendorType.SUP else "sub"
    derived = derive_raw(profile, kind)  # type: ignore[arg-type]
    return dict(derived)


def _scoring_raw(
    criteria: list[EngineCriterion], base_raw: dict[str, Any], rubric: dict[str, int]
) -> RawIndicators:
    """What :func:`vendoriq_scoring.score` actually reads for one application.

    Rubric criteria take the officer's 0-3 cell — falling back to whatever ``base_raw``
    carries for that code, which is either a Yes/No pre-fill (``derive_raw``,
    ``YES_NO_PREFILL_SUB``/``_SUP``) or, for the 13 seeded Rev4 vendors, the value the
    workbook itself recorded before this system existed (brief §1.10). Numeric criteria read
    ``base_raw`` directly; the rubric map has nothing to say about them.
    """
    raw: dict[str, float | int | None] = {}
    for criterion in criteria:
        code = criterion["code"]
        if criterion["kind"] == "rubric":
            if code in rubric:
                raw[code] = rubric[code]
            elif code in base_raw:
                raw[code] = base_raw[code]
            else:
                raw[code] = None
        else:
            raw[code] = base_raw.get(code)
    return raw


# ── evaluation sheet ────────────────────────────────────────────────────────
def _primary_evaluation(session: Session, application_id: uuid.UUID) -> Evaluation | None:
    return session.scalar(
        select(Evaluation).where(
            Evaluation.application_id == application_id, Evaluation.is_primary.is_(True)
        )
    )


def get_evaluation(session: Session, application: Application) -> EvaluationSchema:
    """The evaluation sheet: every criterion, its raw indicator, the officer's cell, points."""
    cycle = _cycle(session, application)
    model_row = _model_row_or_404(session, cycle.scoring_model_version)
    model = _engine_model(session, cycle.scoring_model_version)
    vendor = session.get(Vendor, application.vendor_id)
    if vendor is None:  # pragma: no cover - FK guarantees this
        raise ApiError(404, "not_found", "The application's vendor no longer exists.")

    base_raw = _base_raw(session, application, vendor)
    rubric = dict(application.rubric_scores or {})
    raw = _scoring_raw(model.criteria, base_raw, rubric)

    if application.computed is not None:
        computed_dict: dict[str, Any] = dict(application.computed)
    else:
        computed_dict = asdict(engine_score(model, raw))

    sources = observations.current_sources(session, application.vendor_id)
    per = cast(dict[str, float], computed_dict.get("per", {}))

    rows = [
        EvaluationRow(
            code=criterion["code"],
            group=criterion["group"],
            name_az=criterion.get("name_az", ""),
            name_en=criterion.get("name_en", ""),
            kind=criterion["kind"],
            max=criterion["max"],
            ko=bool(criterion.get("ko", False)),
            unit=criterion.get("unit"),
            evidence_doc=criterion.get("evidence_doc"),
            raw_value=(
                None
                if criterion["kind"] == "rubric"
                else (float(v) if (v := raw.get(criterion["code"])) is not None else None)
            ),
            raw_source=sources.get(criterion["code"]),
            rubric_score=(
                int(v)
                if criterion["kind"] == "rubric" and (v := raw.get(criterion["code"])) is not None
                else None
            ),
            points=per.get(criterion["code"], 0.0),
        )
        for criterion in model.criteria
    ]

    primary = _primary_evaluation(session, application.id)
    evaluator_name = primary.evaluator.full_name if primary and primary.evaluator else None
    pass_mark = float(model_row.pass_mark)
    total = float(computed_dict.get("total", 0.0))
    ko = bool(computed_dict.get("ko", False))
    computed = ScoreResultSchema(
        per=per,
        groups=cast(dict[str, float], computed_dict.get("groups", {})),
        total=total,
        ko=ko,
        cls=computed_dict.get("cls", "KO"),
        pass_mark=pass_mark,
        model_version=model.version,
    )
    return EvaluationSchema(
        application_id=application.id,
        model_version=model.version,
        rows=rows,
        computed=computed,
        can_approve=ko and total >= pass_mark,
        evaluator_name=evaluator_name,
    )


def save_evaluation(
    uow: UnitOfWork, application: Application, principal: Principal, body: RubricInput
) -> EvaluationSchema:
    """Persist the officer's rubric, recompute, and record the primary ``Evaluation`` row."""
    session = uow.session
    _refuse_if_decided(application)
    cycle = _cycle(session, application)
    model_row = _model_row_or_404(session, cycle.scoring_model_version)
    _refuse_if_retired(model_row)
    model = _engine_model(session, cycle.scoring_model_version)

    rubric_codes = {c["code"] for c in model.criteria if c["kind"] == "rubric"}
    unknown = sorted(set(body.rubric_scores) - rubric_codes)
    if unknown:
        raise ApiError(
            422,
            "validation_error",
            f"Not rubric criteria of {model.version}: {', '.join(unknown)}.",
            {"unknown_codes": unknown},
        )

    vendor = session.get(Vendor, application.vendor_id)
    if vendor is None:  # pragma: no cover - FK guarantees this
        raise ApiError(404, "not_found", "The application's vendor no longer exists.")

    # The moment this version has scored an application, its definition is frozen (spec
    # §10.3, ADR-017). `patch_draft` has always refused on `is_locked` — but nothing except
    # the seed ever *set* it, so every model created through the editor stayed editable
    # forever (3B, finding 2). The demonstrated consequence: an application refused at 5.7
    # points, the live version's pass mark patched from 70 to 1, the same application then
    # approved to `prequalified`. Locking here rather than at the decision is deliberate:
    # `is_locked` records that the version was *used to score*, which is this line, not that
    # a commission agreed with the result.
    if not model_row.is_locked:
        model_row.is_locked = True

    before = dict(application.rubric_scores or {})
    application.rubric_scores = dict(body.rubric_scores)
    base_raw = _base_raw(session, application, vendor)
    raw = _scoring_raw(model.criteria, base_raw, application.rubric_scores)
    result = engine_score(model, raw)
    application.computed = asdict(result)
    uow.flush()

    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="evaluate",
        before={"rubric_scores": before},
        after={"rubric_scores": application.rubric_scores, "computed": application.computed},
    )

    primary = _primary_evaluation(session, application.id)
    if primary is None:
        primary = Evaluation(application_id=application.id, is_primary=True)
        session.add(primary)
    primary.evaluator_id = principal.user_id
    primary.rubric = {"scores": dict(body.rubric_scores), "evidence": dict(body.evidence or {})}
    primary.computed = application.computed
    uow.flush()

    return get_evaluation(session, application)


def compute(session: Session, application: Application, body: ComputeRequest) -> ScoreResultSchema:
    """Score without persisting anything — the live evaluation screen's every keystroke."""
    cycle = _cycle(session, application)
    version = body.model_version or cycle.scoring_model_version
    model_row = _model_row_or_404(session, version)
    model = _engine_model(session, version)

    vendor = session.get(Vendor, application.vendor_id)
    if vendor is None:  # pragma: no cover - FK guarantees this
        raise ApiError(404, "not_found", "The application's vendor no longer exists.")

    base_raw = dict(_base_raw(session, application, vendor))
    if body.raw_overrides:
        base_raw.update(body.raw_overrides)
    rubric = {**(application.rubric_scores or {}), **(body.rubric_scores or {})}
    raw = _scoring_raw(model.criteria, base_raw, rubric)
    result = engine_score(model, raw)
    return ScoreResultSchema(
        per=result.per,
        groups=result.groups,
        total=result.total,
        ko=result.ko,
        cls=ScoreClass(result.cls),
        pass_mark=float(model_row.pass_mark),
        model_version=model.version,
    )


def save_second_evaluation(
    uow: UnitOfWork, application: Application, principal: Principal, body: RubricInput
) -> SecondEvaluationSchema:
    """The optional second evaluator's rubric set and the divergence report (spec §10.3)."""
    session = uow.session
    _refuse_if_decided(application)
    cycle = _cycle(session, application)
    model_row = _model_row_or_404(session, cycle.scoring_model_version)
    _refuse_if_retired(model_row)
    model = _engine_model(session, cycle.scoring_model_version)

    primary = _primary_evaluation(session, application.id)
    if primary is None:
        raise ApiError(
            409,
            "conflict",
            "Record the primary evaluation (PUT the evaluation sheet) before a second one.",
        )
    if principal.user_id is not None and principal.user_id == primary.evaluator_id:
        raise ApiError(
            409, "conflict", "The second evaluator must be a different person from the primary."
        )

    rubric_codes = {c["code"] for c in model.criteria if c["kind"] == "rubric"}
    unknown = sorted(set(body.rubric_scores) - rubric_codes)
    if unknown:
        raise ApiError(
            422,
            "validation_error",
            f"Not rubric criteria of {model.version}: {', '.join(unknown)}.",
            {"unknown_codes": unknown},
        )

    vendor = session.get(Vendor, application.vendor_id)
    if vendor is None:  # pragma: no cover - FK guarantees this
        raise ApiError(404, "not_found", "The application's vendor no longer exists.")

    second = session.scalar(
        select(Evaluation).where(
            Evaluation.application_id == application.id,
            Evaluation.evaluator_id == principal.user_id,
            Evaluation.is_primary.is_(False),
        )
    )
    if second is None:
        second = Evaluation(
            application_id=application.id, evaluator_id=principal.user_id, is_primary=False
        )
        session.add(second)

    base_raw = _base_raw(session, application, vendor)
    raw = _scoring_raw(model.criteria, base_raw, body.rubric_scores)
    result = engine_score(model, raw)
    second.rubric = {"scores": dict(body.rubric_scores), "evidence": dict(body.evidence or {})}
    second.computed = asdict(result)
    uow.flush()

    primary_scores = cast(dict[str, Any], (primary.rubric or {}).get("scores", {}))
    divergences = [
        Divergence(code=code, first=int(primary_scores[code]), second=int(second_value))
        for code, second_value in body.rubric_scores.items()
        if code in primary_scores and abs(int(primary_scores[code]) - int(second_value)) > 1
    ]

    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="second_evaluate",
        after={
            "rubric_scores": body.rubric_scores,
            "computed": second.computed,
            "divergences": [d.model_dump() for d in divergences],
        },
    )

    return SecondEvaluationSchema(
        computed=ScoreResultSchema(
            per=result.per,
            groups=result.groups,
            total=result.total,
            ko=result.ko,
            cls=ScoreClass(result.cls),
            pass_mark=float(model_row.pass_mark),
            model_version=model.version,
        ),
        divergences=divergences,
    )


# ── decision ─────────────────────────────────────────────────────────────────
_TARGET_FOR_DECISION: dict[DecisionKind, ApplicationStatus] = {
    DecisionKind.APPROVE: ApplicationStatus.PREQUALIFIED,
    DecisionKind.REJECT: ApplicationStatus.REJECTED,
    DecisionKind.REQUEST_INFO: ApplicationStatus.INFORMATION_REQUESTED,
}


def decide(
    uow: UnitOfWork, application: Application, principal: Principal, body: DecisionInput
) -> ApplicationDetail:
    """Approve, reject or request information — the state machine plus the score gate.

    Approve is refused here, not only by the button the screen disables: the pass mark and
    the knock-out result are read from the same ``computed`` the evaluation screen shows, so
    a client cannot approve a score it never actually saw recomputed.
    """
    session = uow.session
    decision = body.decision
    if decision in (DecisionKind.REJECT, DecisionKind.REQUEST_INFO) and not (
        body.justification and body.justification.strip()
    ):
        raise ApiError(422, "validation_error", "A justification is required for this decision.")

    if decision is DecisionKind.APPROVE:
        computed = application.computed
        cycle = _cycle(session, application)
        model_row = _model_row_or_404(session, cycle.scoring_model_version)
        pass_mark = float(model_row.pass_mark)
        if computed is None:
            raise ApiError(409, "conflict", "No score has been computed for this application yet.")
        ko = bool(computed.get("ko", False))
        total = float(computed.get("total", 0.0))
        if not ko or total < pass_mark:
            raise ApiError(
                409,
                "conflict",
                "Approval is refused below the pass mark or on a knock-out failure (spec §8).",
                {"total": total, "ko": ko, "pass_mark": pass_mark},
            )

    target = _TARGET_FOR_DECISION[decision]
    applications_service.transition(
        uow, application, target, role=principal.role, note=body.justification
    )

    if decision in (DecisionKind.APPROVE, DecisionKind.REJECT):
        application.decision = decision
        application.decided_by = principal.user_id
        application.decided_at = datetime.now(UTC)
        application.justification = body.justification
        if decision is DecisionKind.APPROVE and body.valid_months:
            application.declaration = {
                **(application.declaration or {}),
                "valid_months": body.valid_months,
            }
    uow.flush()

    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="decide",
        after={
            "decision": decision.value,
            "justification": body.justification,
            "status": application.status.value,
        },
    )
    events.emit(
        uow,
        EventType.APPLICATION_DECIDED,
        entity_type="application",
        entity_id=application.id,
        payload={
            "vendor_id": str(application.vendor_id),
            "decision": decision.value,
            "status": application.status.value,
        },
    )

    summary = applications_service.payload(session, application)
    cycle = _cycle(session, application)
    # `ScoreResultSchema` here is exactly `schemas.applications.ScoreResult` (re-exported by
    # `schemas/evaluations.py`, not a second class) — the same one `ApplicationDetail.computed`
    # is typed as, so this is the one canonical schema, not the drift the final report's
    # round 2 asked to stop.
    computed_payload = (
        ScoreResultSchema(**application.computed, model_version=cycle.scoring_model_version)
        if application.computed
        else None
    )
    return ApplicationDetail(
        **summary.model_dump(),
        scoring_model_version=cycle.scoring_model_version,
        rubric_scores=application.rubric_scores,
        computed=computed_payload,
        justification=application.justification,
        # The vendor sees the score breakdown only after the commission decision (spec §7) —
        # a decision was just recorded, so it is released from this response onward.
        score_released=application.decision is not None,
    )

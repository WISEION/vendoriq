"""Reading an application, the pre-submission check, and submitting it (spec §7, §9).

The three checks on the declaration screen read the same catalogues the rest of the API
already trusts: the three knock-out fields and the mandatory-document list are not
re-invented here, they come from ``vendoriq_excel_import.catalog`` and
``services/documents.missing_mandatory``. Submission freezes ``packages/scoring``'s
``derive_raw`` output into ``raw_snapshot`` — the only place a raw indicator is computed for
this endpoint; the frontend never does this arithmetic (brief: "no business logic in the
frontend").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_excel_import.catalog import MANDATORY_FIELD_CODES
from vendoriq_scoring import derive_raw, is_yes

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, QualificationCycle, Vendor
from ..models.enums import ApplicationStatus, UserRole, VendorType
from ..schemas.applications import ApplicationDetail, Declaration, DeclarationInput, ScoreResult
from ..schemas.applications import SubmissionChecks as SubmissionChecksSchema
from ..schemas.vendors import Application as ApplicationSchema
from . import applications as applications_service
from . import audit
from . import documents as documents_service
from . import observations as observations_service
from .answers import is_present

__all__ = ["checks", "detail_payload", "list_page", "submit", "summary_payload"]

#: The three knock-out questions of Appendix A: A.11 licence, A.15 tax clearance, F.1 HSE.
#: Sourced from the same catalogue the Excel importer validates against — a second,
#: hand-copied list here would be exactly the kind of drift ADR-004 exists to prevent.
KO_FIELD_CODES: tuple[str, ...] = MANDATORY_FIELD_CODES

#: Keys a stored ``computed`` blob is allowed to carry into ``ScoreResult`` — the evaluation
#: screen (task 2B) owns what else that dict might grow, and ``Model`` rejects unknown keys.
_SCORE_RESULT_FIELDS = frozenset(
    {"per", "groups", "total", "ko", "cls", "pass_mark", "model_version"}
)


def checks(session: Session, vendor: Vendor) -> SubmissionChecksSchema:
    """The pre-submission checklist: mandatory fields, mandatory documents, the KO answers.

    ``mandatory_fields`` is completeness — the three fields were answered at all.
    ``knock_out_answers`` is the stronger claim the declaration screen's own copy names
    (``vs_c3``, ported verbatim from the prototype): those same three answers read "Yes".
    A vendor who honestly has no licence yet cannot submit through the portal — same as the
    paper process, where an incomplete form was never accepted either.
    """
    profile = observations_service.current_profile(session, vendor.id)
    missing_fields = sorted(code for code in KO_FIELD_CODES if not is_present(profile.get(code)))
    missing_docs = sorted(documents_service.missing_mandatory(session, vendor))
    ko_ok = all(is_yes(profile.get(code)) for code in KO_FIELD_CODES)
    return SubmissionChecksSchema(
        mandatory_fields=not missing_fields,
        mandatory_documents=not missing_docs,
        knock_out_answers=ko_ok,
        missing_field_codes=missing_fields,
        missing_document_codes=missing_docs,
    )


def list_page(
    session: Session,
    *,
    principal_vendor_id: uuid.UUID | None,
    cycle_id: uuid.UUID | None = None,
    statuses: list[ApplicationStatus] | None = None,
    vendor_id: uuid.UUID | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Application], int]:
    """The evaluation queue for staff; a vendor caller always gets exactly its own rows."""
    query = select(Application)
    if principal_vendor_id is not None:
        query = query.where(Application.vendor_id == principal_vendor_id)
    elif vendor_id is not None:
        query = query.where(Application.vendor_id == vendor_id)
    if cycle_id is not None:
        query = query.where(Application.cycle_id == cycle_id)
    if statuses:
        query = query.where(Application.status.in_(statuses))
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.join(Vendor, Vendor.id == Application.vendor_id).where(
            func.lower(Vendor.legal_name).like(needle)
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Application.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(rows), total


def summary_payload(
    session: Session, application: Application, *, principal_role: UserRole | None
) -> ApplicationSchema:
    """The contract's ``Application`` row, with the score hidden pre-decision for a vendor."""
    base = applications_service.payload(session, application)
    if principal_role is UserRole.VENDOR and application.decided_at is None:
        base = base.model_copy(update={"total": None, "cls": None})
    return base


def detail_payload(
    session: Session,
    application: Application,
    *,
    principal_role: UserRole | None,
) -> ApplicationDetail:
    """Answers, the raw snapshot, the rubric and the computed score — score-gated for vendors.

    "Answers" is the vendor's current profile, not a per-application table: the data model
    has no ``application_id`` on ``field_observation`` by design (spec §7 — profile data is
    reused across cycles), so what the form shows is simply the vendor's winning
    observations, the same ones ``GET /vendors/{id}`` resolves.
    """
    vendor = session.get(Vendor, application.vendor_id)
    cycle = session.get(QualificationCycle, application.cycle_id)
    base = summary_payload(session, application, principal_role=principal_role)
    released = application.decided_at is not None
    hide_score = principal_role is UserRole.VENDOR and not released

    computed = None
    if not hide_score and application.computed:
        computed = ScoreResult(
            **{k: v for k, v in application.computed.items() if k in _SCORE_RESULT_FIELDS}
        )
    declaration = Declaration(**application.declaration) if application.declaration else None

    return ApplicationDetail(
        **base.model_dump(),
        scoring_model_version=cycle.scoring_model_version if cycle else None,
        answers=observations_service.current_profile(session, application.vendor_id),
        raw_snapshot=application.raw_snapshot,
        rubric_scores=None if hide_score else application.rubric_scores,
        computed=computed,
        declaration=declaration,
        justification=application.justification,
        checks=checks(session, vendor) if vendor else None,
        score_released=released,
    )


def submit(
    uow: UnitOfWork,
    application: Application,
    vendor: Vendor,
    declaration_input: DeclarationInput,
    *,
    role: UserRole | None,
) -> Application:
    """Gate on the pre-submission check, then freeze the raw-indicator snapshot and submit.

    Idempotent-safe by construction: the state machine only has an edge from
    ``in_progress`` to ``submitted``, so a second call against an already-``submitted``
    application fails ``assert_transition`` with a ``409`` *before* the snapshot below is
    touched — there is never a second freeze.
    """
    result = checks(uow.session, vendor)
    if not (result.mandatory_fields and result.mandatory_documents and result.knock_out_answers):
        raise ApiError(
            409,
            "conflict",
            "Pre-submission check failed.",
            {
                "checks": {
                    "mandatory_fields": result.mandatory_fields,
                    "mandatory_documents": result.mandatory_documents,
                    "knock_out_answers": result.knock_out_answers,
                },
                "missing_field_codes": result.missing_field_codes,
                "missing_document_codes": result.missing_document_codes,
            },
        )

    kind = "sup" if vendor.type is VendorType.SUP else "sub"
    profile = observations_service.current_profile(uow.session, vendor.id)
    derived = derive_raw(profile, kind)  # type: ignore[arg-type]
    snapshot = {
        code: (float(value) if value is not None else None) for code, value in derived.items()
    }

    # The transition raises before anything below runs if the state does not allow it — the
    # only writer of ``application.status`` is ``applications.transition`` (ADR, spec §9).
    applications_service.transition(
        uow,
        application,
        ApplicationStatus.SUBMITTED,
        role=role,
        note="Declaration signed and submitted.",
    )
    application.submitted_at = datetime.now(UTC)
    application.raw_snapshot = snapshot
    application.declaration = {
        "signatory_name": declaration_input.signatory_name,
        "signatory_position": declaration_input.signatory_position,
        "agreed": declaration_input.agreed,
        "signed_at": datetime.now(UTC).isoformat(),
        "stamp_file_key": None,
    }
    uow.flush()
    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="submit",
        after={"raw_snapshot": snapshot, "signatory_name": declaration_input.signatory_name},
    )
    return application

"""Projects, work packages and matching runs (contract tag ``projects``, spec §11).

Screens 22–24 (`docs/SCREENS.md`). ``run_match`` / ``get_latest_match`` never compute a
threshold or a gap themselves — that is entirely ``services/matching.py`` and, beneath it,
``packages/scoring`` (CONTRIBUTING: the engine is the only place a matching rule lives).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import MatchRun as MatchRunRow
from ..models import Project as ProjectRow
from ..models import WorkPackage as WorkPackageRow
from ..models.enums import ProjectStage
from ..schemas.projects import MatchParams as MatchParamsSchema
from ..schemas.projects import (
    MatchRun,
    Project,
    ProjectDetail,
    ProjectInput,
    ProjectPage,
    WorkPackage,
    WorkPackageInput,
)
from ..security import Principal, get_uow, require
from ..services import projects as projects_service

router = APIRouter(tags=["projects"])


# ── serialisers ─────────────────────────────────────────────────────────────
def project_payload(uow: UnitOfWork, project: ProjectRow) -> Project:
    run = projects_service.latest_match(uow.session, project.id)
    state = run.result.get("state") if run is not None else None
    coverage = run.result.get("coverage_pct") if run is not None else None
    return Project(
        id=project.id,
        code=project.code,
        name=project.name,
        client=project.client,
        stage=project.stage,
        estimated_value=float(project.estimated_value)
        if project.estimated_value is not None
        else None,
        deadline=project.deadline,
        external_ref=project.external_ref,
        is_demo=project.is_demo,
        package_count=projects_service.package_count(uow.session, project.id),
        coverage_pct=coverage,
        match_state=state,
        last_matched_at=run.ran_at if run is not None else None,
    )


def package_payload(uow: UnitOfWork, package: WorkPackageRow) -> WorkPackage:
    from .admin import category_payload

    return WorkPackage(
        id=package.id,
        project_id=package.project_id,
        name=package.name,
        category=category_payload(uow, package.category),
        estimated_value=float(package.estimated_value),
        min_class=package.min_class,
        required_certs=list(package.required_certs),
        notes=package.notes,
        is_demo=package.is_demo,
    )


def match_run_payload(row: MatchRunRow) -> MatchRun:
    return MatchRun(**projects_service.match_run_payload(row))


def _load_project(uow: UnitOfWork, project_id: uuid.UUID) -> ProjectRow:
    return projects_service.get(uow.session, project_id)


# ── projects ─────────────────────────────────────────────────────────────────
@router.get("/projects")
def list_projects(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    stage: Annotated[list[ProjectStage] | None, Query()] = None,
    q: str | None = None,
    include_demo: bool = True,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listProjects")),
) -> ProjectPage:
    filters = projects_service.ProjectFilters(stages=stage or (), q=q, include_demo=include_demo)
    rows, total = projects_service.list_page(uow.session, filters, page=page, page_size=page_size)
    return ProjectPage(
        items=[project_payload(uow, row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createProject")),
) -> Project:
    project = projects_service.create(uow, body.model_dump(exclude_unset=True))
    return project_payload(uow, project)


@router.get("/projects/{project_id}")
def get_project(
    project_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getProject")),
) -> ProjectDetail:
    project = _load_project(uow, project_id)
    run = projects_service.latest_match(uow.session, project_id)
    return ProjectDetail(
        **project_payload(uow, project).model_dump(),
        packages=[
            package_payload(uow, row)
            for row in projects_service.list_packages(uow.session, project_id)
        ],
        latest_match=match_run_payload(run) if run is not None else None,
    )


@router.patch("/projects/{project_id}")
def patch_project(
    project_id: uuid.UUID,
    body: ProjectInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchProject")),
) -> Project:
    project = _load_project(uow, project_id)
    projects_service.patch(uow, project, body.model_dump(exclude_unset=True))
    return project_payload(uow, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deleteProject")),
) -> None:
    project = _load_project(uow, project_id)
    projects_service.delete(uow, project)


# ── work packages ────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/packages")
def list_packages(
    project_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listPackages")),
) -> list[WorkPackage]:
    _load_project(uow, project_id)
    return [
        package_payload(uow, row) for row in projects_service.list_packages(uow.session, project_id)
    ]


@router.post("/projects/{project_id}/packages", status_code=201)
def create_package(
    project_id: uuid.UUID,
    body: WorkPackageInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createPackage")),
) -> WorkPackage:
    project = _load_project(uow, project_id)
    package = projects_service.create_package(uow, project, body.model_dump(exclude_unset=True))
    return package_payload(uow, package)


@router.patch("/projects/{project_id}/packages/{package_id}")
def patch_package(
    project_id: uuid.UUID,
    package_id: uuid.UUID,
    body: WorkPackageInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchPackage")),
) -> WorkPackage:
    _load_project(uow, project_id)
    package = projects_service.get_package(uow.session, project_id, package_id)
    projects_service.patch_package(uow, package, body.model_dump(exclude_unset=True))
    return package_payload(uow, package)


@router.delete("/projects/{project_id}/packages/{package_id}", status_code=204)
def delete_package(
    project_id: uuid.UUID,
    package_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deletePackage")),
) -> None:
    _load_project(uow, project_id)
    package = projects_service.get_package(uow.session, project_id, package_id)
    projects_service.delete_package(uow, package)


# ── matching ─────────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/match", status_code=201)
def run_match(
    project_id: uuid.UUID,
    body: MatchParamsSchema | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("runMatch")),
) -> MatchRun:
    project = _load_project(uow, project_id)
    override = body.model_dump(exclude_unset=True) if body is not None else None
    row = projects_service.run_match(uow, project, override)
    return match_run_payload(row)


@router.get("/projects/{project_id}/match/latest")
def get_latest_match(
    project_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getLatestMatch")),
) -> MatchRun:
    _load_project(uow, project_id)
    run = projects_service.latest_match(uow.session, project_id)
    if run is None:
        raise ApiError(404, "not_found", "This project has never been matched.")
    return match_run_payload(run)


@router.get("/projects/{project_id}/export.xlsx")
def export_project(
    project_id: uuid.UUID,
    locale: Literal["az", "en"] = "az",
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("exportProject")),
) -> Response:
    project = _load_project(uow, project_id)
    content = projects_service.export_workbook(uow.session, project, locale=locale)
    filename = f"{project.code}-matching.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]

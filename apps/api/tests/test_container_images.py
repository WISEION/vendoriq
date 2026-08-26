"""The images install exactly what the lock files say, or they fail.

Each Dockerfile used to end its dependency step with a fallback — `uv sync --frozen … || uv
sync …`, `npm ci … || npm install …`. Written while the lock files were not yet committed,
it survived after they were, and what it did then was this: the moment a lock file and its
manifests disagreed, the build stopped honouring the lock and resolved whatever was newest on
the registry. Quietly. The image would come out with a dependency set nobody chose, the
docker-build check in CI would stay green, and the first sign of it would be behaviour
differing between a developer's machine and production.

That is precisely the failure a lock file exists to prevent, so the fallbacks are gone and
this keeps them gone. It is a text check, because the build itself cannot run here (no Docker
daemon, brief §9) — but a fallback is a textual thing, and `uv lock --check` plus `npm ci`
are already run by CI on every push.
"""

from __future__ import annotations

from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[3] / "infra"
#: The canonical three, by name — a glob also swept up the `.sandbox` variants a
#: TLS-intercepted build host generates for itself, which are neither committed nor CI's.
DOCKERFILES = [INFRA / name for name in ("Dockerfile.api", "Dockerfile.worker", "Dockerfile.web")]


def test_there_are_dockerfiles_to_check() -> None:
    """Guards against a rename silently emptying the list."""
    for path in DOCKERFILES:
        assert path.is_file(), path


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.name)
def test_no_dependency_step_has_an_unlocked_fallback(dockerfile: Path) -> None:
    for number, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if "||" in line and ("uv sync" in line or "npm ci" in line or "npm install" in line):
            pytest.fail(f"{dockerfile.name}:{number} falls back to an unlocked install: {line}")


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.name)
def test_every_install_is_locked(dockerfile: Path) -> None:
    body = dockerfile.read_text(encoding="utf-8")
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "uv sync" in line:
            assert "--frozen" in line, f"{dockerfile.name}: {line.strip()}"
            # Without --all-packages a workspace root sync installs no member's
            # dependencies: the image built green in CI and died at `alembic: not found`
            # the first time a container actually started. --all-extras is boto3 —
            # STORAGE_BACKEND=s3 is what the compose stack runs.
            assert "--all-packages" in line, f"{dockerfile.name}: {line.strip()}"
            assert "--all-extras" in line, f"{dockerfile.name}: {line.strip()}"
        # `npm install` resolves; `npm ci` installs the lock file and fails if it cannot.
        assert "npm install" not in line, f"{dockerfile.name}: {line.strip()}"


@pytest.mark.parametrize(
    ("dockerfile", "lock"),
    [
        ("Dockerfile.api", "uv.lock"),
        ("Dockerfile.worker", "uv.lock"),
        ("Dockerfile.web", "package-lock.json"),
    ],
)
def test_the_lock_file_is_copied_without_a_glob(dockerfile: str, lock: str) -> None:
    """`COPY uv.lock* ./` succeeds when the file is absent. `COPY uv.lock ./` does not.

    The glob was the other half of the fallback: together they turned a missing lock file into
    a successful build rather than a stopped one.
    """
    body = (INFRA / dockerfile).read_text(encoding="utf-8")
    assert f"{lock}*" not in body, f"{dockerfile} copies {lock} through a glob"
    assert lock in body, f"{dockerfile} never copies {lock}"

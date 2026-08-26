"""What restore.sh refuses to do.

The scripts themselves cannot be exercised here — there is no Docker daemon on this build
host (BUILD_BRIEF §9), so `pg_restore` and `mc mirror` are unverified and said so in
docs/REPORT.md. What *is* verifiable is the part that runs before any container is touched:
the refusals. Those are the half that matters most, because a restore script is used on the
worst day of the year by somebody in a hurry, and its job at that moment is to say no to a
snapshot that would quietly produce a system whose rows point at documents that are not
there.

So: given a directory that is not a snapshot, it must stop, and it must stop with something
other than a shell's default 1 — an exit code an operator's own wrapper can branch on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RESTORE = REPO_ROOT / "scripts" / "restore.sh"
BACKUP = REPO_ROOT / "scripts" / "backup.sh"

USAGE = 64
NOT_A_SNAPSHOT = 65


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RESTORE), *args],
        capture_output=True,
        text=True,
        # Nothing here should ever reach a prompt or a container; if it does, fail loudly
        # rather than hanging the suite.
        timeout=30,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.parametrize("script", [BACKUP, RESTORE])
def test_both_scripts_are_executable_and_parse(script: Path) -> None:
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0


def test_restore_without_an_argument_explains_itself() -> None:
    result = _run()
    assert result.returncode == USAGE
    assert "usage:" in result.stderr


@pytest.mark.parametrize("missing", ["database.dump", "documents", "manifest.txt"])
def test_restore_refuses_a_snapshot_missing_any_of_its_three_parts(
    tmp_path: Path, missing: str
) -> None:
    (tmp_path / "database.dump").write_bytes(b"")
    (tmp_path / "documents").mkdir()
    (tmp_path / "manifest.txt").write_text("alembic_revision=abc123\n")

    target = tmp_path / missing
    target.unlink() if target.is_file() else target.rmdir()

    result = _run(str(tmp_path))
    assert result.returncode == NOT_A_SNAPSHOT
    assert missing in result.stderr

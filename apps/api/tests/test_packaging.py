"""No source file is invisible to git.

The failure this guards against shipped for two phases without anyone noticing. `.gitignore`
carried an unanchored `storage/`, written for the local file-storage backend at the repository
root. Unanchored, it matches a directory of that name at *any* depth — and it matched
`apps/api/vendoriq_api/storage/`, the storage abstraction itself. Every commit since phase 0
excluded it.

Nothing local ever failed, because the working tree had the files. It surfaced the first time
CI ran against a fresh clone, as `ModuleNotFoundError: No module named 'vendoriq_api.storage'`
— the application could not be imported at all from what the repository actually contained.

The check is for **ignored** files, not untracked ones: work in progress is untracked all the
time and that is fine. A source file that git has been told to pretend does not exist is the
bug.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
#: Where first-party source lives. Everything under these, `.py` or `.ts`, must be visible.
SOURCE_ROOTS = ("apps/api", "apps/worker", "apps/web/src", "packages")
#: Directories that are legitimately generated and legitimately ignored.
GENERATED = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules", "dist")


def _source_files() -> list[Path]:
    found: list[Path] = []
    for root in SOURCE_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or not path.is_file():
                continue
            if any(part in GENERATED for part in path.parts):
                continue
            found.append(path)
    return found


def test_no_source_file_is_hidden_from_git() -> None:
    files = _source_files()
    assert files, "found no source files — the roots or the suffixes are wrong"

    try:
        result = subprocess.run(
            # `--no-index` matters: without it `check-ignore` stays silent about paths that
            # are already tracked, so the check would pass for exactly the files most worth
            # protecting and only catch a pattern the moment it had already done its damage.
            ["git", "check-ignore", "--no-index", "--stdin"],
            input="\n".join(str(path) for path in files),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:  # pragma: no cover - no git available
        pytest.skip(f"git is not usable here: {error}")

    # `check-ignore` exits 1 when nothing matched, which is the outcome we want.
    ignored = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())

    assert not ignored, (
        "these source files are excluded by .gitignore and would be missing from a fresh "
        f"clone: {ignored}"
    )

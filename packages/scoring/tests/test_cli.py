"""`python -m vendoriq_scoring` — the engine without the API in front of it.

Small on purpose: the CLI exists so an officer's raw-indicator file can be checked against
a model version from a shell, and so the 13/13 claim can be reproduced by hand.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from vendoriq_scoring.cli import main

SEED_FIXTURE = Path(__file__).resolve().parents[3] / "seed" / "vendors_seed.json"


@pytest.fixture
def wesa_raw(tmp_path: Path) -> Path:
    """V05's raw indicators, straight from the Rev4 fixture."""
    rows = json.loads(SEED_FIXTURE.read_text(encoding="utf-8"))
    wesa = next(row for row in rows if row["id"] == "V05")
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(wesa["raw"]), encoding="utf-8")
    return path


def test_score_prints_the_result_as_json(
    wesa_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["score", "--model", "sub-4", "--raw", str(wesa_raw)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == "sub-4"
    assert payload["total"] == 90.3
    assert payload["cls"] == "A"
    assert payload["ko"] is True
    assert payload["groups"]["C"] > 0
    assert payload["per"]["A.1"] == 5.0


def test_score_defaults_to_the_subcontractor_model(
    wesa_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["score", "--raw", str(wesa_raw)]) == 0
    assert json.loads(capsys.readouterr().out)["model"] == "sub-4"


def test_score_accepts_a_model_file_path(
    wesa_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from vendoriq_scoring import MODELS_DIR

    path = str(MODELS_DIR / "sup-1.json")
    assert main(["score", "--model", path, "--raw", str(wesa_raw)]) == 0
    assert json.loads(capsys.readouterr().out)["model"] == "sup-1"


def test_derive_turns_answers_into_raw_indicators(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = tmp_path / "answers.json"
    answers.write_text(
        json.dumps({"A.4": 2015, "A.11": "Bəli", "E.1": 80, "E.5": 4}), encoding="utf-8"
    )
    assert main(["derive", "--answers", str(answers), "--type", "sub", "--year", "2026"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["A.2"] == 11
    assert payload["A.1"] == 3.0
    assert payload["E.2"] == 4


def test_an_unknown_model_is_an_error_not_a_traceback(
    wesa_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["score", "--model", "sub-99", "--raw", str(wesa_raw)]) == 2
    assert "unknown model" in capsys.readouterr().err


def test_a_missing_raw_file_is_an_error_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["score", "--raw", "/nowhere/raw.json"]) == 2
    assert "error:" in capsys.readouterr().err


def test_raw_must_be_an_object(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "raw.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert main(["score", "--raw", str(path)]) == 2
    assert "keyed by criterion code" in capsys.readouterr().err


def test_the_module_entry_point_runs_end_to_end(wesa_raw: Path) -> None:
    """The documented invocation, as a real subprocess — argv wiring included."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "vendoriq_scoring",
            "score",
            "--model",
            "sub-4",
            "--raw",
            str(wesa_raw),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout)["total"] == 90.3


def test_stdin_composes_derive_into_score(tmp_path: Path) -> None:
    """``derive | score`` — the pipeline the importer's output is checked with."""
    answers = json.dumps(
        {
            "A.4": 2015, "A.11": "Bəli", "A.15": "Bəli", "F.1": "Bəli",
            "B.1": 7_000_000, "B.2": 5_000_000, "B.3": 2_600_000, "B.5": 1_200_000,
            "E.1": 80, "E.5": 9,
        }
    )  # fmt: skip
    derived = subprocess.run(
        [sys.executable, "-m", "vendoriq_scoring", "derive", "--answers", "-", "--year", "2026"],
        input=answers,
        capture_output=True,
        text=True,
        check=True,
    )
    scored = subprocess.run(
        [sys.executable, "-m", "vendoriq_scoring", "score", "--model", "sub-4", "--raw", "-"],
        input=derived.stdout,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(scored.stdout)
    assert payload["ko"] is True
    assert payload["per"]["A.2"] == 3  # 11 years in operation, bands top

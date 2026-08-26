"""A small command line over the engine, for checking a score without the API running.

    python -m vendoriq_scoring score --model sub-4 --raw raw.json
    cat raw.json | python -m vendoriq_scoring score --model sub-4 --raw -
    python -m vendoriq_scoring derive --type sub --answers answers.json | \\
        python -m vendoriq_scoring score --model sub-4 --raw -

``raw.json`` is a flat ``{"A.1": 3, "B.1": 385937, ...}`` map — the same shape the seed
carries per vendor. Output is JSON on stdout so the CLI composes with ``jq``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

from .derive import derive_raw
from .engine import score
from .loader import BUILTIN_MODEL_VERSIONS, load_model, model_from_dict
from .types import RawIndicators, ScoringModel, VendorTypeName

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code; never raises for user error."""
    parser = argparse.ArgumentParser(
        prog="python -m vendoriq_scoring",
        description="Score a vendor against a VendorIQ scoring model.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scorer = commands.add_parser("score", help="score raw indicators against a model")
    scorer.add_argument(
        "--model",
        default="sub-4",
        help=f"model version (built in: {', '.join(BUILTIN_MODEL_VERSIONS)}), or a path to JSON",
    )
    scorer.add_argument(
        "--raw", required=True, help="path to the raw-indicator JSON, or - for stdin"
    )
    scorer.add_argument("--indent", type=int, default=2, help="JSON indent; 0 for one line")

    deriver = commands.add_parser("derive", help="turn application answers into raw indicators")
    deriver.add_argument(
        "--answers", required=True, help="path to the answers JSON, or - for stdin"
    )
    deriver.add_argument(
        "--type", default="sub", choices=("sub", "sup", "both"), dest="vendor_type"
    )
    deriver.add_argument("--year", type=int, default=None, help="current year (default: today)")
    deriver.add_argument("--indent", type=int, default=2, help="JSON indent; 0 for one line")

    args = parser.parse_args(argv)
    try:
        if args.command == "score":
            payload = _score_command(args.model, args.raw)
        else:
            payload = _derive_command(args.answers, args.vendor_type, args.year)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=args.indent or None, sort_keys=False))
    return 0


def _score_command(model_ref: str, raw_ref: str) -> dict[str, object]:
    model = _resolve_model(model_ref)
    raw = cast(RawIndicators, _read_json(raw_ref))
    if not isinstance(raw, dict):
        raise ValueError("the raw indicators must be a JSON object keyed by criterion code")
    result = score(model, raw)
    return {"model": model.version, **asdict(result)}


def _derive_command(answers_ref: str, vendor_type: str, year: int | None) -> dict[str, object]:
    answers = _read_json(answers_ref)
    if not isinstance(answers, dict):
        raise ValueError("the answers must be a JSON object keyed by form field code")
    return dict(derive_raw(answers, cast(VendorTypeName, vendor_type), current_year=year))


def _resolve_model(reference: str) -> ScoringModel:
    """A built-in version name, or a path to a model JSON file."""
    if reference in BUILTIN_MODEL_VERSIONS:
        return load_model(reference)
    path = Path(reference)
    if path.is_file():
        document = json.loads(path.read_text(encoding="utf-8"))
        return model_from_dict(document)
    raise ValueError(f"unknown model {reference!r}: not a built-in version and not a file")


def _read_json(reference: str) -> object:
    if reference == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(reference).read_text(encoding="utf-8"))

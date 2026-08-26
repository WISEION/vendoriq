"""``python -m vendoriq_api.seed`` — the argument parser and the operator's summary.

Three commands, matching the Makefile (brief §2, seed/README.md)::

    load --real     the 13 vendors, categories, scoring models, the TQS2026006 cycle
    load --demo     the removable demo layer on top
    purge-demo      deletes every is_demo=True row, real data untouched
    create-admin    one real staff account — how a production stack gets its first user

Each command opens exactly one transaction (``db.session_scope``) — either everything it
does commits, or a failure (including a :class:`SeedError`) rolls all of it back.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
from collections.abc import Sequence

from ..config import get_settings
from ..db import UnitOfWork, session_scope
from ..models.enums import UserRole
from ..services import accounts as accounts_service
from .demo import DemoSummary, load_demo
from .errors import SeedError
from .purge import PurgeSummary, purge_demo
from .real import RealSummary, load_real

logger = logging.getLogger("vendoriq.seed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vendoriq_api.seed",
        description="Load or purge the VendorIQ seed data (seed/README.md).",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    load_parser = subcommands.add_parser("load", help="Load seed data into the database.")
    load_parser.add_argument(
        "--real", action="store_true", help="Load the real vendors, categories and models."
    )
    load_parser.add_argument(
        "--demo", action="store_true", help="Load the removable demo layer (is_demo=true)."
    )

    subcommands.add_parser("purge-demo", help="Delete every is_demo=true row.")

    admin_parser = subcommands.add_parser(
        "create-admin",
        help="Create one real staff account (the first user of a production stack).",
    )
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--name", required=True, help="Full name, as shown in the UI.")
    admin_parser.add_argument(
        "--role",
        default=UserRole.ADMIN.value,
        choices=[role.value for role in UserRole if role is not UserRole.VENDOR],
        help="Default: admin.",
    )
    # No --password flag. Command lines are visible to every process on the host through
    # `ps`, and they end up in the shell history of whoever deployed.
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "load":
            real = bool(args.real)
            demo = bool(args.demo)
            if not real and not demo:
                parser.error("`load` needs --real, --demo, or both.")
            _run_load(real=real, demo=demo)
            return 0
        if args.command == "purge-demo":
            _run_purge()
            return 0
        if args.command == "create-admin":
            return _run_create_admin(email=args.email, name=args.name, role=UserRole(args.role))
    except SeedError as exc:
        logger.error("seed error: %s", exc)
        return 1

    parser.error(f"unknown command {args.command!r}")
    return 2  # pragma: no cover - argparse.error already raises SystemExit


def _run_load(*, real: bool, demo: bool) -> None:
    settings = get_settings()
    with session_scope() as session:
        uow = UnitOfWork(session)
        if real:
            _print_real_summary(load_real(uow, settings=settings))
        if demo:
            _print_demo_summary(load_demo(uow))


def _run_purge() -> None:
    with session_scope() as session:
        summary = purge_demo(UnitOfWork(session))
    _print_purge_summary(summary)


def _run_create_admin(*, email: str, name: str, role: UserRole) -> int:
    """Prompt for a password, create the account, print the TOTP secret once."""
    # The environment variable exists for a provisioning script that has no terminal; an
    # operator at a prompt gets `getpass`, which does not echo and does not reach history.
    password = os.environ.get("VENDORIQ_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if not os.environ.get("VENDORIQ_ADMIN_PASSWORD") and password != getpass.getpass("Repeat: "):
        print("The two passwords differ — nothing was created.")
        return 1

    try:
        with session_scope() as session:
            user, uri = accounts_service.create_staff_account(
                UnitOfWork(session), email=email, full_name=name, role=role, password=password
            )
            secret, address, role_name = user.totp_secret, user.email, user.role.value
    except (accounts_service.AccountExistsError, ValueError) as exc:
        print(str(exc))
        return 1

    print("== VendorIQ: staff account created ==")
    print(f"  {role_name:<10} {address}")
    print(f"  TOTP secret: {secret}")
    print(f"  {uri}")
    print()
    print("Enrol the authenticator now. The secret is shown once and is not stored anywhere")
    print("it can be read back — losing it means creating the account again.")
    return 0


def _print_real_summary(summary: RealSummary) -> None:
    print("== VendorIQ seed: real data ==")
    print(f"  scoring models    {summary.scoring_models_loaded} loaded (sub-4, sup-1)")
    print(f"  categories        {summary.categories_created} created")
    print(
        f"  vendors           {summary.vendors_created} created, "
        f"{summary.vendors_matched} already present"
    )
    print(f"  contacts          {summary.contacts_created} created")
    print(f"  observations      {summary.observations_created} recorded")
    print(f"  project TQS-238   {'created' if summary.project_created else 'already present'}")
    print(
        f"  cycle             {'created' if summary.cycle_created else 'already present'} "
        "(TQS2026006 Rev4)"
    )
    print(
        f"  applications      {summary.applications_created} created, "
        f"{summary.applications_matched} already present — all 13 Rev4 totals verified"
    )
    if summary.test_accounts:
        print("  test accounts (AUTH_MODE=test):")
        for user, uri in summary.test_accounts:
            print(f"    {user.role.value:<10} {user.email}")
            if user.totp_secret and uri:
                print(f"        TOTP secret: {user.totp_secret}")
                print(f"        {uri}")


def _print_demo_summary(summary: DemoSummary) -> None:
    print("== VendorIQ seed: demo layer ==")
    print(f"  category links    {summary.category_assignments_created} created, confirmed")
    print(f"  suppliers         {summary.suppliers_created} created")
    print(f"  supplier contacts {summary.supplier_contacts_created} created")
    print(f"  supplier obs.     {summary.supplier_observations_created} recorded")
    print(
        f"  supplier qual.    {summary.supplier_applications_created} applications created "
        f"against sup-1 — {summary.suppliers_prequalified} prequalified, "
        f"{summary.suppliers_rejected} rejected"
    )
    print(f"  projects          {summary.projects_created} created (TQS-301)")
    print(f"  work packages     {summary.work_packages_created} created")
    print(f"  documents         {summary.documents_created} created")


def _print_purge_summary(summary: PurgeSummary) -> None:
    print("== VendorIQ seed: purge-demo ==")
    for table, count in summary.removed.items():
        print(f"  {table:<20} {count} removed")
    print(f"  {'total':<20} {summary.total} removed")

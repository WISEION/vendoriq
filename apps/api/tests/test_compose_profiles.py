"""The production overlay cannot be started with development defaults.

`infra/docker-compose.yml` is written for a laptop. It defaults `APP_ENV` to development,
`AUTH_MODE` to test, and every password to a word printed in this repository. That is the
right shape for `docker compose --profile dev up` and the wrong shape for a public hostname:
test mode seeds the accounts in `docs/TEST_ACCOUNTS.md` and prints sign-in codes into the
response, so a stack that reaches production still carrying those defaults is not merely
misconfigured, it is open.

`infra/docker-compose.prod.yml` closes that by replacing each default with either a fixed
production value or the `${VAR:?...}` form, which makes `docker compose` refuse to render a
configuration at all until a real value is supplied. This test is what keeps that true: the
guarantee is one careless `:-` away from evaporating silently, and nothing about the running
system would look different afterwards.

The YAML assertions run anywhere. When the `docker compose` CLI is available the rendered
configuration is checked as well — the same parse the daemon would do — because reading the
overlay is not the same as knowing how compose merges it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA = REPO_ROOT / "infra"
BASE = INFRA / "docker-compose.yml"
PROD = INFRA / "docker-compose.prod.yml"

#: Enough of a production environment to render the overlay. Values are placeholders; what
#: matters is that every one of them has to be present at all.
PROD_ENV = {
    "SESSION_SECRET": "0" * 64,
    "POSTGRES_USER": "vendoriq_prod",
    "POSTGRES_PASSWORD": "not-the-default",
    "POSTGRES_DB": "vendoriq_prod",
    "MINIO_ROOT_USER": "vendoriq_prod",
    "MINIO_ROOT_PASSWORD": "also-not-the-default",
    "SMTP_HOST": "smtp.example.az",
    "SMTP_FROM": "noreply@example.az",
    "DOMAIN": "vendoriq.example.az",
    "TLS_DIRECTIVE": "tls ops@example.az",
}


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def _service_env(compose: dict[str, Any], service: str) -> dict[str, Any]:
    """The service's own `environment` mapping, with YAML anchors already expanded."""
    return dict(compose["services"][service].get("environment") or {})


def test_the_dev_profile_still_carries_the_convenient_defaults() -> None:
    """The premise of every other test here: the base file *is* the unsafe one."""
    env = _service_env(_load(BASE), "api")
    assert "${APP_ENV:-development}" in env["APP_ENV"]
    assert "${AUTH_MODE:-test}" in env["AUTH_MODE"]


@pytest.mark.parametrize("service", ["api", "worker"])
def test_the_overlay_pins_production_and_live_auth(service: str) -> None:
    env = _service_env(_load(PROD), service)
    # Pinned, not defaulted: no `${...}` at all, so there is nothing for an operator to
    # override and nothing for the API's own AUTH_MODE guard to be talked out of.
    assert env["APP_ENV"] == "production"
    assert env["AUTH_MODE"] == "live"


@pytest.mark.parametrize(
    ("service", "key"),
    [
        ("db", "POSTGRES_PASSWORD"),
        ("minio", "MINIO_ROOT_PASSWORD"),
        ("api", "SESSION_SECRET"),
        ("worker", "SESSION_SECRET"),
        ("caddy", "DOMAIN"),
        ("caddy", "TLS_DIRECTIVE"),
    ],
)
def test_every_secret_and_hostname_is_required_rather_than_defaulted(
    service: str, key: str
) -> None:
    value = _service_env(_load(PROD), service)[key]
    assert ":?" in value, f"{service}.{key} must use ${{VAR:?...}}, got {value!r}"
    assert ":-" not in value, f"{service}.{key} has a default, which is the whole bug"


def test_the_seed_service_is_not_in_the_production_profile() -> None:
    """`make seed` loads the demo layer and the test accounts. Not on a live stack."""
    assert _load(BASE)["services"]["seed"]["profiles"] == ["dev"]


# ── the same claims, as docker compose actually renders them ────────────────────────────

pytestmark_cli = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker CLI not installed on this host"
)


def _render(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(BASE),
            "-f",
            str(PROD),
            "--profile",
            "prod",
            "config",
            "--format",
            "json",
        ],
        # A clean environment: `docker compose` reads `infra/.env` from the project directory,
        # and an operator's own file must not be able to make this test pass.
        cwd=INFRA,
        env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), **env},
        capture_output=True,
        text=True,
    )


@pytestmark_cli
def test_compose_refuses_to_render_without_a_session_secret() -> None:
    missing = {k: v for k, v in PROD_ENV.items() if k != "SESSION_SECRET"}
    result = _render(missing)
    assert result.returncode != 0
    assert "SESSION_SECRET" in result.stderr


@pytestmark_cli
def test_the_rendered_production_stack_publishes_nothing_but_caddy() -> None:
    """Postgres, MinIO and the API are reachable only through the proxy that has the TLS."""
    result = _render(PROD_ENV)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    published = {name for name, svc in config["services"].items() if svc.get("ports")}
    assert published == {"caddy"}


@pytestmark_cli
def test_the_rendered_api_service_is_production_live_and_on_object_storage() -> None:
    result = _render(PROD_ENV)
    assert result.returncode == 0, result.stderr
    env = json.loads(result.stdout)["services"]["api"]["environment"]
    assert env["APP_ENV"] == "production"
    assert env["AUTH_MODE"] == "live"
    # Local filesystem storage in a container is storage that dies with the container.
    assert env["STORAGE_BACKEND"] == "s3"
    assert PROD_ENV["POSTGRES_PASSWORD"] in env["DATABASE_URL"]

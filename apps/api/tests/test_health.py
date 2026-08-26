"""Phase 0 smoke tests: the app boots and serves the contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from vendoriq_api.config import Settings
from vendoriq_api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_mode"] in {"test", "live"}


def test_health_under_api_prefix(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


def test_openapi_json_is_the_handwritten_contract(client: TestClient) -> None:
    document = client.get("/api/openapi.json").json()
    assert document["openapi"].startswith("3.1")
    assert document["info"]["title"] == "VendorIQ API"
    assert "/health" in document["paths"]


def test_openapi_yaml_is_served(client: TestClient) -> None:
    response = client.get("/api/openapi.yaml")
    assert response.status_code == 200
    assert response.text.lstrip().startswith("openapi:")


def test_docs_page_renders(client: TestClient) -> None:
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    body = client.get("/api/does-not-exist").json()
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"


def test_test_auth_mode_is_refused_in_production() -> None:
    """Brief §6: the app must not start with AUTH_MODE=test and APP_ENV=production."""
    with pytest.raises(ValueError, match="AUTH_MODE=test is refused"):
        # _env_file is a pydantic-settings runtime keyword the generated __init__ hides.
        Settings(app_env="production", auth_mode="test", _env_file=None)  # type: ignore[call-arg]

"""Authentication: OTP, password + TOTP, sessions, CSRF and API keys (ADR-003, spec §3)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from vendoriq_api.config import AppEnv, Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.errors import ApiError
from vendoriq_api.models.enums import Scope, UserRole, VendorType
from vendoriq_api.security import hashing, tokens
from vendoriq_api.security import totp as totp_module
from vendoriq_api.services import auth as auth_service
from vendoriq_api.services import users as users_service


# ── vendor registration and OTP ─────────────────────────────────────────────
def test_registration_creates_the_vendor_and_returns_a_code(client: TestClient) -> None:
    response = client.post(
        "/api/auth/vendor/register",
        json={
            "legal_name": "Yeni Podratçı MMC",
            "voen": "1234509876",
            "type": "sub",
            "contact_name": "Test Adam",
            "email": "new.vendor@example.az",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.vendor@example.az"
    # AUTH_MODE=test reveals the code so the owner can click through without e-mail.
    assert body["debug_code"] is not None and len(body["debug_code"]) == 6


def test_a_duplicate_voen_is_a_conflict(client: TestClient, make_vendor: Any) -> None:
    existing = make_vendor(voen="1003915341")
    response = client.post(
        "/api/auth/vendor/register",
        json={
            "legal_name": "Copycat MMC",
            "voen": existing.voen,
            "type": "sub",
            "contact_name": "X",
            "email": "copycat@example.az",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_voen_must_be_ten_digits(client: TestClient) -> None:
    response = client.post(
        "/api/auth/vendor/register",
        json={
            "legal_name": "Short VOEN MMC",
            "voen": "123",
            "type": "sub",
            "contact_name": "X",
            "email": "short@example.az",
        },
    )
    assert response.status_code == 422


def test_otp_request_does_not_reveal_whether_the_account_exists(
    client: TestClient, make_user: Any, make_vendor: Any
) -> None:
    """Both answers are 202 with the same shape — no enumeration oracle."""
    known = make_user(UserRole.VENDOR, vendor=make_vendor())
    real = client.post("/api/auth/otp/request", json={"email": known.email})
    fake = client.post("/api/auth/otp/request", json={"email": "nobody@nowhere.az"})
    assert real.status_code == fake.status_code == 202
    assert set(real.json()) == set(fake.json())


def test_the_real_code_logs_in(client: TestClient, make_user: Any, make_vendor: Any) -> None:
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    code = client.post("/api/auth/otp/request", json={"email": user.email}).json()["debug_code"]
    response = client.post("/api/auth/otp/verify", json={"email": user.email, "code": code})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == user.email


def test_the_test_code_logs_in_without_a_request(
    client: TestClient, make_user: Any, make_vendor: Any
) -> None:
    """Brief §6: `000000` is accepted unconditionally in test mode."""
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    response = client.post("/api/auth/otp/verify", json={"email": user.email, "code": "000000"})
    assert response.status_code == 200


def test_a_wrong_code_is_refused(client: TestClient, make_user: Any, make_vendor: Any) -> None:
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    client.post("/api/auth/otp/request", json={"email": user.email})
    response = client.post("/api/auth/otp/verify", json={"email": user.email, "code": "123456"})
    assert response.status_code == 401


def test_a_code_is_burned_after_use(
    uow: UnitOfWork, settings: Settings, make_user: Any, make_vendor: Any
) -> None:
    """Replaying a one-time code must fail — that is what makes it one-time."""
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    issue = auth_service.issue_otp(uow, settings, email=user.email)
    assert issue.debug_code is not None
    auth_service.verify_otp(uow, settings, email=user.email, code=issue.debug_code)
    live = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="development",
        auth_mode="live",
        database_url=settings.database_url,
        session_secret=settings.session_secret,
    )
    with pytest.raises(ApiError) as raised:
        auth_service.verify_otp(uow, live, email=user.email, code=issue.debug_code)
    assert raised.value.status_code == 401


def test_live_mode_hides_the_code_and_refuses_the_test_code(
    uow: UnitOfWork, settings: Settings, make_user: Any, make_vendor: Any
) -> None:
    """ADR-003: with AUTH_MODE=live, `debug_code` is null and `000000` is just wrong."""
    live = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="development",
        auth_mode="live",
        database_url=settings.database_url,
        session_secret=settings.session_secret,
    )
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    issue = auth_service.issue_otp(uow, live, email=user.email)
    assert issue.debug_code is None
    with pytest.raises(ApiError) as raised:
        auth_service.verify_otp(uow, live, email=user.email, code="000000")
    assert raised.value.status_code == 401


def test_otp_requests_are_rate_limited(
    client: TestClient, make_user: Any, make_vendor: Any, settings: Settings
) -> None:
    """Spec §13 / contract 429: the code endpoint is an obvious brute-force target."""
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    for _ in range(settings.otp_rate_limit):
        assert client.post("/api/auth/otp/request", json={"email": user.email}).status_code == 202
    limited = client.post("/api/auth/otp/request", json={"email": user.email})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert limited.json()["error"]["details"]["retry_after"] > 0


def test_a_deactivated_vendor_account_cannot_log_in(
    client: TestClient, make_user: Any, make_vendor: Any
) -> None:
    user = make_user(UserRole.VENDOR, vendor=make_vendor(), is_active=False)
    assert (
        client.post(
            "/api/auth/otp/verify", json={"email": user.email, "code": "000000"}
        ).status_code
        == 401
    )


# ── staff password + TOTP ───────────────────────────────────────────────────
def test_password_alone_does_not_issue_a_session(
    client: TestClient,
    make_user: Any,
    settings: Settings,
    password: str,
) -> None:
    """Contract: `totp_required: true` and a challenge; no cookie until the second factor."""
    user = make_user(UserRole.MANAGER)
    response = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    )
    assert response.status_code == 200
    assert response.json()["totp_required"] is True
    assert settings.session_cookie not in client.cookies
    assert client.get("/api/auth/me").status_code == 401


def test_a_wrong_password_is_refused(client: TestClient, make_user: Any) -> None:
    user = make_user(UserRole.MANAGER)
    response = client.post("/api/auth/staff/login", json={"email": user.email, "password": "nope"})
    assert response.status_code == 401


def test_a_vendor_account_cannot_use_the_staff_endpoint(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    password: str,
) -> None:
    """Vendors have no password; the endpoint must not become a probe for that fact."""
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    response = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    )
    assert response.status_code == 401


def test_the_current_totp_code_completes_the_login(
    client: TestClient,
    make_user: Any,
    settings: Settings,
    password: str,
) -> None:
    user = make_user(UserRole.OFFICER)
    challenge = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    ).json()
    live_code = totp_module.totp(user.totp_secret, step=settings.totp_step_seconds)
    response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": live_code},
    )
    assert response.status_code == 200, response.text
    assert response.json()["csrf_token"]


def test_the_test_code_also_completes_the_login(
    client: TestClient, make_user: Any, password: str
) -> None:
    user = make_user(UserRole.ADMIN)
    challenge = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    ).json()
    response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": "000000"},
    )
    assert response.status_code == 200


def test_the_dev_totp_header_is_present_in_development_test_mode(
    client: TestClient,
    make_user: Any,
    password: str,
) -> None:
    """Task 1C: `X-Dev-TOTP` carries the current code when APP_ENV=development."""
    user = make_user(UserRole.OFFICER)
    response = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    )
    assert response.headers["X-Dev-TOTP"] == response.json()["debug_code"]


def test_the_dev_totp_header_is_withheld_outside_development(
    settings: Settings, make_user: Any
) -> None:
    """A staging box left in test mode still does not print codes into a response header."""
    user = make_user(UserRole.OFFICER)
    staging = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="staging",
        auth_mode="test",
        database_url=settings.database_url,
        session_secret=settings.session_secret,
    )
    assert auth_service.dev_totp_code(staging, user) is None
    assert auth_service.dev_totp_code(settings, user) is not None


def test_a_wrong_totp_code_is_refused(client: TestClient, make_user: Any, password: str) -> None:
    user = make_user(UserRole.OFFICER)
    challenge = client.post(
        "/api/auth/staff/login", json={"email": user.email, "password": password}
    ).json()
    response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": "111111"},
    )
    assert response.status_code == 401


def test_a_forged_challenge_id_is_refused(
    client: TestClient, make_user: Any, password: str
) -> None:
    """The id must match the signed token in the cookie — otherwise it proves nothing."""
    user = make_user(UserRole.OFFICER)
    client.post("/api/auth/staff/login", json={"email": user.email, "password": password})
    response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": "00000000-0000-0000-0000-000000000000", "code": "000000"},
    )
    assert response.status_code == 401


def test_totp_verify_without_a_challenge_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": "00000000-0000-0000-0000-000000000000", "code": "000000"},
    )
    assert response.status_code == 401


# ── the TOTP implementation itself ──────────────────────────────────────────
def test_totp_matches_the_rfc_6238_sha1_test_vectors() -> None:
    """RFC 6238 Appendix B, SHA-1 rows: the seed is ASCII "12345678901234567890"."""
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of 12345678901234567890
    expectations = {
        59: "94287082",
        1111111109: "07081804",
        1111111111: "14050471",
        1234567890: "89005924",
        2000000000: "69279037",
    }
    for moment, expected in expectations.items():
        assert totp_module.totp(secret, at=moment, digits=8) == expected


def test_totp_accepts_the_neighbouring_step_and_nothing_further() -> None:
    """RFC 6238 §5.2 recommends at most one step of tolerance either side."""
    secret = totp_module.generate_secret()
    now = 1_700_000_000
    assert totp_module.verify(secret, totp_module.totp(secret, at=now), at=now)
    assert totp_module.verify(secret, totp_module.totp(secret, at=now - 30), at=now)
    assert not totp_module.verify(secret, totp_module.totp(secret, at=now - 120), at=now)


def test_totp_rejects_malformed_input() -> None:
    secret = totp_module.generate_secret()
    for bad in ("", "12345", "1234567", "abcdef", "12 456"):
        assert not totp_module.verify(secret, bad)


def test_the_provisioning_uri_is_an_otpauth_url() -> None:
    uri = totp_module.provisioning_uri("JBSWY3DPEHPK3PXP", "officer@vendoriq.test")
    assert uri.startswith("otpauth://totp/VendorIQ%3Aofficer%40vendoriq.test?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri


# ── password hashing ────────────────────────────────────────────────────────
def test_passwords_round_trip_through_the_available_hasher() -> None:
    encoded = hashing.hash_password("Correct Horse Battery Staple")
    assert encoded != "Correct Horse Battery Staple"
    assert hashing.verify_password("Correct Horse Battery Staple", encoded)
    assert not hashing.verify_password("wrong", encoded)


def test_verify_password_handles_a_missing_hash() -> None:
    """A vendor account has no password; asking must be a plain False, not a crash."""
    assert not hashing.verify_password("anything", None)
    assert not hashing.verify_password("anything", "")
    assert not hashing.verify_password("anything", "garbage$not$a$hash")


def test_two_hashes_of_one_password_differ() -> None:
    """Distinct salts: identical passwords must not produce identical stored values."""
    assert hashing.hash_password("same") != hashing.hash_password("same")


# ── sessions and CSRF ───────────────────────────────────────────────────────
def test_the_session_cookie_is_httponly_and_the_csrf_cookie_is_not(
    client: TestClient, make_user: Any, login: Any, settings: Settings
) -> None:
    """Both halves of the double-submit pair are set, and only one is readable by script."""
    login(make_user(UserRole.OFFICER))
    assert settings.session_cookie in client.cookies
    assert settings.csrf_cookie in client.cookies
    jar = {cookie.name: cookie for cookie in client.cookies.jar}
    assert jar[settings.session_cookie].has_nonstandard_attr("HttpOnly")
    assert not jar[settings.csrf_cookie].has_nonstandard_attr("HttpOnly")


def test_a_mutation_without_the_csrf_header_is_forbidden(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """Double submit: the cookie rides along automatically, the header cannot be forged."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    del client.headers["X-CSRF-Token"]
    response = client.patch(f"/api/vendors/{vendor.id}", json={"region": "Bakı", "reason": "x"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["error"]["message"]


def test_a_wrong_csrf_token_is_forbidden(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    client.headers["X-CSRF-Token"] = "not-the-token"
    response = client.patch(f"/api/vendors/{vendor.id}", json={"region": "Bakı", "reason": "x"})
    assert response.status_code == 403


def test_reads_do_not_need_the_csrf_header(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))
    del client.headers["X-CSRF-Token"]
    assert client.get("/api/vendors").status_code == 200


def test_logout_clears_the_session(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_a_tampered_session_cookie_is_ignored(
    client: TestClient, make_user: Any, login: Any, settings: Settings
) -> None:
    login(make_user(UserRole.OFFICER))
    good = client.cookies[settings.session_cookie]
    client.cookies.set(settings.session_cookie, good[:-3] + "xyz")
    assert client.get("/api/auth/me").status_code == 401


def test_an_expired_token_is_refused() -> None:
    token = tokens.sign({"sub": "x"}, "secret", ttl_seconds=-1)
    with pytest.raises(tokens.TokenError):
        tokens.unsign(token, "secret")


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = tokens.sign({"sub": "x"}, "secret-a", ttl_seconds=60)
    with pytest.raises(tokens.TokenError):
        tokens.unsign(token, "secret-b")
    for malformed in ("", "no-dot", "a.b", "!!!.???"):
        with pytest.raises(tokens.TokenError):
            tokens.unsign(malformed, "secret-a")


def test_a_deactivated_account_loses_its_session(
    client: TestClient, make_user: Any, login: Any, session: Any
) -> None:
    """Deactivation is the revocation mechanism for a stateless session."""
    user = make_user(UserRole.OFFICER)
    login(user)
    assert client.get("/api/auth/me").status_code == 200
    user.is_active = False
    session.flush()
    assert client.get("/api/auth/me").status_code == 401


# ── API keys ────────────────────────────────────────────────────────────────
def test_an_api_key_authenticates_a_machine_client(
    client: TestClient, uow: UnitOfWork, make_vendor: Any
) -> None:
    """Alternative to the session cookie for other products (brief §2)."""
    make_vendor()
    _, plaintext = users_service.create_api_key(
        uow,
        name="Reporting bot",
        scopes=[Scope.VENDORS_READ.value],
        created_by=None,
    )
    response = client.get("/api/vendors", headers={"X-API-Key": plaintext})
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_an_api_key_is_confined_to_its_scopes(client: TestClient, uow: UnitOfWork) -> None:
    _, read_only = users_service.create_api_key(
        uow, name="Read only", scopes=[Scope.VENDORS_READ.value], created_by=None
    )
    forbidden = client.post(
        "/api/vendors",
        json={"legal_name": "Bot Co", "type": "sub"},
        headers={"X-API-Key": read_only},
    )
    assert forbidden.status_code == 403


def test_an_api_key_may_not_mint_another_api_key_or_touch_accounts(
    client: TestClient, uow: UnitOfWork
) -> None:
    """Operations declared with ``scope=None`` are closed to machines by construction.

    Account creation and API-key management are the two things a leaked key must not be
    able to do, because either one turns a scoped credential into an unscoped one.
    """
    _, key = users_service.create_api_key(
        uow,
        name="Everything bot",
        scopes=[scope.value for scope in Scope],
        created_by=None,
    )
    # Commit so the refused request below — which rolls its unit of work back — cannot
    # take the key with it.
    uow.commit()
    headers = {"X-API-Key": key}
    created = client.post(
        "/api/admin/users",
        json={"email": "sneaky@vendoriq.test", "role": "admin", "password": "x"},
        headers=headers,
    )
    assert created.status_code == 403
    # …even though the same key can read what admin:read covers.
    assert client.get("/api/admin/users", headers=headers).status_code == 200


def test_an_api_key_needs_the_right_scope_for_admin_reads(
    client: TestClient, uow: UnitOfWork
) -> None:
    _, key = users_service.create_api_key(
        uow, name="Vendors bot", scopes=[Scope.VENDORS_READ.value], created_by=None
    )
    assert client.get("/api/admin/users", headers={"X-API-Key": key}).status_code == 403


def test_api_key_mutations_do_not_need_a_csrf_token(client: TestClient, uow: UnitOfWork) -> None:
    """A browser does not attach `X-API-Key` automatically, so CSRF does not apply."""
    _, key = users_service.create_api_key(
        uow, name="Writer bot", scopes=[Scope.VENDORS_WRITE.value], created_by=None
    )
    response = client.post(
        "/api/vendors",
        json={"legal_name": "Bot Created MMC", "type": "sub"},
        headers={"X-API-Key": key},
    )
    assert response.status_code == 201


def test_a_revoked_key_stops_working(client: TestClient, uow: UnitOfWork) -> None:
    record, key = users_service.create_api_key(
        uow, name="Doomed", scopes=[Scope.VENDORS_READ.value], created_by=None
    )
    assert client.get("/api/vendors", headers={"X-API-Key": key}).status_code == 200
    users_service.revoke_api_key(uow, record)
    assert client.get("/api/vendors", headers={"X-API-Key": key}).status_code == 401


def test_an_unknown_key_is_unauthenticated(client: TestClient) -> None:
    assert client.get("/api/vendors", headers={"X-API-Key": "vq_nope_nope"}).status_code == 401


def test_only_the_hash_of_a_key_is_stored(uow: UnitOfWork) -> None:
    record, plaintext = users_service.create_api_key(
        uow, name="Secret", scopes=[Scope.INTEL_READ.value], created_by=None
    )
    assert plaintext not in record.hashed_key
    assert hashing.tokens_match(plaintext, record.hashed_key)


def test_an_unknown_scope_is_rejected(uow: UnitOfWork) -> None:
    with pytest.raises(ApiError) as raised:
        users_service.create_api_key(uow, name="Bad", scopes=["vendors:destroy"], created_by=None)
    assert raised.value.status_code == 422


# ── /auth/me ────────────────────────────────────────────────────────────────
def test_me_reports_the_role_and_its_operations(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.COMMISSION))
    body = client.get("/api/auth/me").json()
    assert body["role"] == "commission"
    assert body["auth_mode"] == "test"
    assert "decideApplication" in body["permissions"]
    assert "createUser" not in body["permissions"]


def test_me_for_a_vendor_carries_its_vendor(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor(legal_name="Wesa Test MMC")
    login(make_user(UserRole.VENDOR, vendor=vendor))
    body = client.get("/api/auth/me").json()
    assert body["vendor_id"] == str(vendor.id)
    assert body["vendor_name"] == "Wesa Test MMC"


def test_me_for_an_api_key_lists_scope_operations(client: TestClient, uow: UnitOfWork) -> None:
    _, key = users_service.create_api_key(
        uow, name="Bot", scopes=[Scope.VENDORS_READ.value], created_by=None
    )
    body = client.get("/api/auth/me", headers={"X-API-Key": key}).json()
    assert "listVendors" in body["permissions"]
    assert "createVendor" not in body["permissions"]


# ── the startup guard ───────────────────────────────────────────────────────
def test_test_mode_is_refused_in_production() -> None:
    """Brief §6: the process must refuse to open a port, not warn."""
    with pytest.raises(ValueError, match="AUTH_MODE=test is refused"):
        Settings(app_env="production", auth_mode="test", _env_file=None)  # type: ignore[call-arg]


def test_live_mode_in_production_is_fine() -> None:
    # A real `session_secret` is now required alongside `AUTH_MODE=live` in production
    # (3B, finding 9) — this test is about the auth-mode guard, so it supplies one.
    settings = Settings(  # type: ignore[call-arg]
        app_env="production", auth_mode="live", session_secret="0" * 64, _env_file=None
    )
    assert settings.app_env == "production"


@pytest.mark.parametrize("app_env", ["development", "staging"])
def test_test_mode_is_allowed_outside_production(app_env: AppEnv) -> None:
    settings = Settings(app_env=app_env, auth_mode="test", _env_file=None)  # type: ignore[call-arg]
    assert settings.auth_mode == "test"


def test_health_reports_the_modes(client: TestClient) -> None:
    """The dev banner reads this to warn that the system is not secure yet."""
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "version": body["version"],
        "app_env": "development",
        "auth_mode": "test",
        "storage_backend": "local",
    }


def test_rate_limit_window_expires(settings: Settings) -> None:
    """A retry after the window must succeed — a limiter that never forgets is a lockout."""
    auth_service.reset_rate_limits()
    auth_service._rate_limit("probe", limit=1, window_seconds=1)
    with pytest.raises(ApiError) as raised:
        auth_service._rate_limit("probe", limit=1, window_seconds=1)
    assert raised.value.status_code == 429
    time.sleep(1.05)
    auth_service._rate_limit("probe", limit=1, window_seconds=1)


def test_registration_rejects_a_duplicate_email(
    client: TestClient, make_user: Any, make_vendor: Any
) -> None:
    existing = make_user(UserRole.VENDOR, vendor=make_vendor())
    response = client.post(
        "/api/auth/vendor/register",
        json={
            "legal_name": "Another MMC",
            "voen": "5555555555",
            "type": VendorType.SUP.value,
            "contact_name": "X",
            "email": existing.email,
        },
    )
    assert response.status_code == 409

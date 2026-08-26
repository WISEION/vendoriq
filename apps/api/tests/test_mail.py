"""Outbound e-mail and its log fallback (brief §2)."""

from __future__ import annotations

import logging
import smtplib
from types import TracebackType
from typing import Any, ClassVar

import pytest
from vendoriq_api.config import Settings
from vendoriq_api.services import mail


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, app_env="development", auth_mode="test", **overrides)  # type: ignore[call-arg]


def test_without_an_smtp_host_the_message_goes_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A demo box has no mail server; the message must still be recoverable."""
    with caplog.at_level(logging.INFO, logger="vendoriq.mail"):
        sent = mail.send(_settings(smtp_host=None), to="a@b.az", subject="Test", body="the body")
    assert sent is False
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "a@b.az" in logged
    assert "the body" in logged


class _FakeSMTP:
    """Records what a real SMTP conversation would have been given."""

    instances: ClassVar[list[_FakeSMTP]] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[Any] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, message: Any) -> None:
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _reset_fake() -> None:
    _FakeSMTP.instances.clear()


def test_with_an_smtp_host_the_message_is_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    sent = mail.send(
        _settings(
            smtp_host="mail.example.az",
            smtp_port=2525,
            smtp_user="postmaster",
            smtp_password="secret",
            smtp_tls=True,
            smtp_from="noreply@vendoriq.local",
        ),
        to="habib.atakisiyev@wesa.az",
        subject="VendorIQ — dəvət / invitation",
        body="Prekvalifikasiya müraciətinə dəvət olunmusunuz.",
    )
    assert sent is True
    server = _FakeSMTP.instances[-1]
    assert (server.host, server.port) == ("mail.example.az", 2525)
    assert server.started_tls is True
    assert server.login_args == ("postmaster", "secret")
    message = server.messages[0]
    assert message["To"] == "habib.atakisiyev@wesa.az"
    assert message["From"] == "noreply@vendoriq.local"
    # The AZ subject survives the header encoding.
    assert "dəvət" in str(message["Subject"])


def test_tls_and_credentials_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relay on the same host needs neither STARTTLS nor a login."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    mail.send(
        _settings(smtp_host="localhost", smtp_tls=False, smtp_user=None, smtp_password=None),
        to="a@b.az",
        subject="Plain",
        body="body",
    )
    server = _FakeSMTP.instances[-1]
    assert server.started_tls is False
    assert server.login_args is None

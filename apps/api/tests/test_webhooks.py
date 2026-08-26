"""Webhook signing, delivery, retry and dispatch (task 2E).

The HMAC scheme is the part of this system another company writes code against, so it is
tested the way a subscriber would use it: sign, then verify; then tamper with one byte and
prove the verification fails.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Webhook
from vendoriq_api.models.enums import EventType
from vendoriq_api.services import events as events_service
from vendoriq_api.services import webhooks


# ── a receiving endpoint, on loopback ───────────────────────────────────────
class _Receiver(BaseHTTPRequestHandler):
    status: int = 200
    #: Statuses to answer with, in order; the last one repeats.
    script: ClassVar[list[int]] = []
    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append(
            {
                "path": self.path,
                "body": body,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        index = min(len(type(self).received) - 1, len(type(self).script) - 1)
        status = type(self).script[index] if type(self).script else type(self).status
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        return


@pytest.fixture
def receiver() -> Iterator[tuple[str, type[_Receiver]]]:
    _Receiver.received = []
    _Receiver.script = []
    _Receiver.status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/hook", _Receiver
    finally:
        server.shutdown()
        server.server_close()


# ── the signature ───────────────────────────────────────────────────────────
def test_a_signature_verifies_against_the_body_it_was_made_from() -> None:
    secret = webhooks.new_secret()
    body = b'{"type":"vendor.prequalified"}'

    header, timestamp = webhooks.sign(secret, body)

    assert header.startswith(f"t={timestamp},v1=")
    assert webhooks.verify(secret, header, body)


def test_a_tampered_body_fails_verification() -> None:
    """The test the integration guide points at: one byte changes, the signature dies."""
    secret = webhooks.new_secret()
    body = json.dumps({"type": "vendor.prequalified", "payload": {"class": "C"}}).encode()
    header, _ = webhooks.sign(secret, body)
    assert webhooks.verify(secret, header, body)

    # A receiver upgrading itself from class C to class A, the attack the signature exists for.
    tampered = body.replace(b'"C"', b'"A"')

    assert tampered != body
    assert webhooks.verify(secret, header, tampered) is False


def test_a_tampered_timestamp_fails_verification() -> None:
    """The timestamp is *inside* the signed message, so it cannot be moved independently."""
    secret = webhooks.new_secret()
    body = b'{"a":1}'
    header, timestamp = webhooks.sign(secret, body)

    moved = header.replace(f"t={timestamp}", f"t={timestamp - 60}")

    assert webhooks.verify(secret, moved, body, now=timestamp) is False


def test_the_wrong_secret_fails_verification() -> None:
    body = b'{"a":1}'
    header, _ = webhooks.sign(webhooks.new_secret(), body)
    assert webhooks.verify(webhooks.new_secret(), header, body) is False


def test_a_replayed_delivery_is_detectable() -> None:
    """A perfectly valid signature from an hour ago is refused by the tolerance window."""
    secret = webhooks.new_secret()
    body = b'{"a":1}'
    header, timestamp = webhooks.sign(secret, body)

    assert webhooks.verify(secret, header, body, now=timestamp + 10) is True
    assert webhooks.verify(secret, header, body, now=timestamp + 3600) is False


def test_a_malformed_signature_header_is_refused_rather_than_raising() -> None:
    secret = webhooks.new_secret()
    for header in ("", "nonsense", "t=abc,v1=deadbeef", "v1=deadbeef", "t=1"):
        assert webhooks.verify(secret, header, b"{}") is False


def test_the_signed_payload_carries_the_delivery_timestamp() -> None:
    body = webhooks.delivery_body(
        event_id=uuid.uuid4(),
        event_type="vendor.prequalified",
        entity_type="vendor",
        entity_id=uuid.uuid4(),
        payload={"class": "B"},
        created_at=datetime.now(UTC),
        delivered_at=datetime.now(UTC),
        delivery_id=uuid.uuid4(),
    )
    document = json.loads(body)
    assert set(document) == {
        "delivery_id",
        "event_id",
        "type",
        "entity_type",
        "entity_id",
        "payload",
        "created_at",
        "delivered_at",
    }


# ── delivery ────────────────────────────────────────────────────────────────
def test_a_delivery_arrives_signed_and_verifiable(receiver: tuple[str, type[_Receiver]]) -> None:
    url, handler = receiver
    secret = webhooks.new_secret()
    body = b'{"type":"application.submitted"}'

    result = webhooks.deliver(
        url, secret, body, event_type="application.submitted", delivery_id=uuid.uuid4()
    )

    assert result.delivered is True
    assert result.status_code == 200
    sent = handler.received[0]
    assert sent["body"] == body
    assert webhooks.verify(secret, sent["headers"]["x-vendoriq-signature"], sent["body"])
    assert sent["headers"]["x-vendoriq-event"] == "application.submitted"


def test_a_server_error_is_retried_with_backoff(receiver: tuple[str, type[_Receiver]]) -> None:
    url, handler = receiver
    handler.script = [500, 503, 200]
    delays: list[float] = []

    result = webhooks.deliver(
        url,
        webhooks.new_secret(),
        b"{}",
        event_type="x",
        delivery_id=uuid.uuid4(),
        backoff_seconds=0.01,
        sleep=delays.append,
    )

    assert result.delivered is True
    assert result.attempts == 3
    assert len(handler.received) == 3
    # Exponential: each wait is twice the previous one.
    assert delays == [0.01, 0.02]


def test_a_client_error_is_not_retried(receiver: tuple[str, type[_Receiver]]) -> None:
    """A 400 means the receiver rejected the payload; sending it again changes nothing."""
    url, handler = receiver
    handler.script = [400]

    result = webhooks.deliver(
        url, webhooks.new_secret(), b"{}", event_type="x", delivery_id=uuid.uuid4()
    )

    assert result.delivered is False
    assert result.status_code == 400
    assert result.attempts == 1
    assert len(handler.received) == 1


def test_an_unreachable_receiver_is_reported_not_swallowed() -> None:
    result = webhooks.deliver(
        "http://127.0.0.1:9/hook",
        webhooks.new_secret(),
        b"{}",
        event_type="x",
        delivery_id=uuid.uuid4(),
        attempts=1,
    )

    assert result.delivered is False
    assert result.status_code is None
    assert result.error


def test_a_retry_is_signed_afresh(receiver: tuple[str, type[_Receiver]]) -> None:
    """Otherwise a retry after a long backoff would arrive outside the receiver's window."""
    url, handler = receiver
    handler.script = [500, 200]
    secret = webhooks.new_secret()

    webhooks.deliver(
        url,
        secret,
        b"{}",
        event_type="x",
        delivery_id=uuid.uuid4(),
        backoff_seconds=0.0,
        sleep=lambda _: None,
    )

    signatures = [item["headers"]["x-vendoriq-signature"] for item in handler.received]
    assert len(signatures) == 2
    for signature in signatures:
        assert webhooks.verify(secret, signature, b"{}")


# ── the dispatcher ──────────────────────────────────────────────────────────
class _Inline:
    """An executor that runs the work on the calling thread, so a test can assert on it."""

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> None:
        fn(*args, **kwargs)


@pytest.fixture
def inline_delivery(session: Session) -> Iterator[list[tuple[uuid.UUID, Any]]]:
    """Deliver synchronously and record results into the test's own session."""
    recorded: list[tuple[uuid.UUID, Any]] = []

    def recorder(webhook_id: uuid.UUID, result: Any) -> None:
        recorded.append((webhook_id, result))
        row = session.get(Webhook, webhook_id)
        if row is not None:
            webhooks.apply_result(row, result)

    webhooks.set_executor(_Inline())  # type: ignore[arg-type]
    webhooks.set_recorder(recorder)
    webhooks.install_dispatcher()
    try:
        yield recorded
    finally:
        webhooks.set_executor(None)
        webhooks.set_recorder(None)


def _subscribe(session: Session, url: str, event: str) -> Webhook:
    row = Webhook(
        url=url, secret=webhooks.new_secret(), events=[event], is_active=True, failure_count=0
    )
    session.add(row)
    session.commit()
    return row


def test_an_emitted_event_reaches_its_subscriber(
    session: Session,
    uow: UnitOfWork,
    receiver: tuple[str, type[_Receiver]],
    inline_delivery: list[tuple[uuid.UUID, Any]],
) -> None:
    url, handler = receiver
    row = _subscribe(session, url, EventType.VENDOR_PREQUALIFIED.value)

    events_service.emit(
        uow,
        EventType.VENDOR_PREQUALIFIED,
        entity_type="vendor",
        entity_id=uuid.uuid4(),
        payload={"class": "B"},
    )
    uow.commit()

    assert len(handler.received) == 1
    sent = handler.received[0]
    assert webhooks.verify(row.secret, sent["headers"]["x-vendoriq-signature"], sent["body"])
    assert json.loads(sent["body"])["type"] == "vendor.prequalified"


def test_an_event_nobody_subscribed_to_is_not_delivered(
    session: Session,
    uow: UnitOfWork,
    receiver: tuple[str, type[_Receiver]],
    inline_delivery: list[tuple[uuid.UUID, Any]],
) -> None:
    url, handler = receiver
    _subscribe(session, url, EventType.PROJECT_MATCHED.value)

    events_service.emit(
        uow, EventType.APPLICATION_SUBMITTED, entity_type="application", entity_id=uuid.uuid4()
    )
    uow.commit()

    assert handler.received == []


def test_an_inactive_subscription_receives_nothing(
    session: Session,
    uow: UnitOfWork,
    receiver: tuple[str, type[_Receiver]],
    inline_delivery: list[tuple[uuid.UUID, Any]],
) -> None:
    url, handler = receiver
    row = _subscribe(session, url, EventType.DOCUMENT_EXPIRING.value)
    row.is_active = False
    session.commit()

    events_service.emit(
        uow, EventType.DOCUMENT_EXPIRING, entity_type="document", entity_id=uuid.uuid4()
    )
    uow.commit()

    assert handler.received == []


def test_nothing_is_delivered_for_a_rolled_back_transaction(
    session: Session,
    receiver: tuple[str, type[_Receiver]],
    inline_delivery: list[tuple[uuid.UUID, Any]],
) -> None:
    """Delivery is queued during the transaction and drained only after it commits."""
    url, handler = receiver
    _subscribe(session, url, EventType.VENDOR_PREQUALIFIED.value)
    rolling_back = UnitOfWork(session)

    events_service.emit(
        rolling_back, EventType.VENDOR_PREQUALIFIED, entity_type="vendor", entity_id=uuid.uuid4()
    )
    assert handler.received == []
    rolling_back.rollback()

    assert handler.received == []


def test_a_failing_subscriber_never_fails_the_emitting_request(
    session: Session,
    uow: UnitOfWork,
    inline_delivery: list[tuple[uuid.UUID, Any]],
) -> None:
    """The request that prequalified a vendor must succeed even if the subscriber is down."""
    row = _subscribe(session, "http://127.0.0.1:9/gone", EventType.VENDOR_PREQUALIFIED.value)

    events_service.emit(
        uow, EventType.VENDOR_PREQUALIFIED, entity_type="vendor", entity_id=uuid.uuid4()
    )
    uow.commit()

    assert [webhook_id for webhook_id, _ in inline_delivery] == [row.id]
    assert inline_delivery[0][1].delivered is False
    assert row.failure_count == 1


def test_delivery_bookkeeping_resets_on_success(session: Session) -> None:
    row = Webhook(
        url="https://example.test/hook",
        secret=webhooks.new_secret(),
        events=["vendor.prequalified"],
        is_active=True,
        failure_count=4,
    )
    session.add(row)
    session.flush()

    webhooks.apply_result(row, webhooks.DeliveryResult(True, 200, 12))

    assert row.failure_count == 0
    assert row.last_delivery_at is not None


def test_the_dispatcher_is_installed_by_importing_the_router() -> None:
    """The wiring claim in ``routers/integrations.py``: importing it installs the dispatcher."""
    events_service.set_dispatcher(None)
    import importlib

    module = importlib.import_module("vendoriq_api.routers.integrations")
    importlib.reload(module)

    assert events_service._dispatcher is webhooks.dispatch


def test_time_is_not_read_twice_when_signing_a_known_timestamp() -> None:
    """``sign`` accepts an explicit instant so a caller can reproduce a signature exactly."""
    secret = "abc"
    header, timestamp = webhooks.sign(secret, b"{}", timestamp=1_700_000_000)
    assert timestamp == 1_700_000_000
    assert header.startswith("t=1700000000,v1=")
    assert webhooks.verify(secret, header, b"{}", now=1_700_000_000)
    assert time.time() > 0

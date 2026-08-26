"""Outbound webhooks: signing, delivery, retry and the dispatcher (brief §2, spec §13).

A future product subscribes to ``vendor.prequalified``, ``application.submitted``,
``document.expiring`` or ``project.matched`` and receives a POST. Four properties make that
safe to build on, and each is a decision worth stating:

**The signature covers the raw body, not a re-serialisation of it.** ``X-VendorIQ-Signature``
is ``t=<unix seconds>,v1=<hex>``, where the HMAC-SHA256 is taken over ``b"<t>." + body``
with the subscription's own secret. A receiver verifies against the bytes it read off the
socket, before parsing: any other order lets a body that re-serialises to the same JSON
verify while carrying different bytes.

**The timestamp is signed and also inside the body.** ``t`` is part of the signed message,
so it cannot be moved without breaking the signature, and ``delivered_at`` repeats it in the
payload for a receiver that logs deliveries. A replayed delivery is therefore detectable:
its ``t`` is old, and the receiver rejects it outside its tolerance window.

**Delivery never blocks and never fails the request that caused the event.** ``dispatch`` runs
inside the emitting transaction but does no I/O: it snapshots the matching subscriptions and
queues them, and the queue is drained *after the transaction commits* — so a rolled-back
request delivers nothing — on a background executor. An exception in delivery is logged and
goes no further.

**Retries back off.** A transport failure, a 429 or a 5xx is retried with an exponential
delay; a 4xx is not, because a receiver rejecting the payload will reject it again.

The secret is never returned by the API after creation, never logged and never included in
an error message.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from ..adapters.transport import TransportError
from ..adapters.transport import request as http_request
from ..db import UnitOfWork, session_scope
from ..errors import ApiError
from ..models import Event, Webhook
from ..models.enums import EventType
from ..services import audit
from ..services import events as events_service

logger = logging.getLogger("vendoriq.webhooks")

#: Header carrying the signature, and the scheme version inside it.
SIGNATURE_HEADER = "X-VendorIQ-Signature"
SIGNATURE_VERSION = "v1"
#: How far a delivery's timestamp may be from the receiver's clock before it is a replay.
DEFAULT_TOLERANCE_SECONDS = 300
#: Delivery attempts, and the base of the exponential backoff between them, in seconds.
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0
#: How long one delivery may take before it is abandoned.
DELIVERY_TIMEOUT = 10.0

#: The events a subscription may name — the four of brief §4.2 plus the rest of the log.
SUBSCRIBABLE_EVENTS: frozenset[str] = frozenset(member.value for member in EventType)


# ── signing ─────────────────────────────────────────────────────────────────
def new_secret() -> str:
    """A per-subscription signing secret, shown once at creation and never again."""
    return secrets.token_urlsafe(32)


def signed_message(timestamp: int, body: bytes) -> bytes:
    """``b"<t>." + body`` — the exact bytes both sides run the HMAC over."""
    return f"{timestamp}.".encode("ascii") + body


def sign(secret: str, body: bytes, timestamp: int | None = None) -> tuple[str, int]:
    """Return ``(header value, timestamp)`` for one delivery."""
    moment = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode("utf-8"), signed_message(moment, body), sha256).hexdigest()
    return f"t={moment},{SIGNATURE_VERSION}={digest}", moment


def parse_signature(header: str) -> tuple[int, str] | None:
    """``t=…,v1=…`` → ``(timestamp, digest)``; ``None`` when the header is malformed."""
    timestamp: int | None = None
    digest: str | None = None
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None
        elif key == SIGNATURE_VERSION:
            digest = value
    if timestamp is None or not digest:
        return None
    return timestamp, digest


def verify(
    secret: str,
    header: str,
    body: bytes,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """The receiver's side of the scheme — published verbatim in ``docs/integration-guide.md``.

    Order matters: the timestamp is checked against the tolerance window *and* the digest is
    compared in constant time. A tampered body fails because the digest no longer matches; a
    replayed delivery fails because its ``t`` is outside the window, even though its
    signature is perfectly valid.
    """
    parsed = parse_signature(header)
    if parsed is None:
        return False
    timestamp, digest = parsed
    moment = time.time() if now is None else now
    if abs(moment - timestamp) > tolerance_seconds:
        return False
    expected = hmac.new(secret.encode("utf-8"), signed_message(timestamp, body), sha256).hexdigest()
    return hmac.compare_digest(expected, digest)


# ── payload ─────────────────────────────────────────────────────────────────
def delivery_body(
    *,
    event_id: uuid.UUID,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    payload: dict[str, Any],
    created_at: datetime,
    delivered_at: datetime,
    delivery_id: uuid.UUID,
) -> bytes:
    """The exact bytes that are signed and sent. Serialised once, never twice.

    ``separators`` and ``sort_keys`` are fixed so a receiver that logs the body and a
    developer who re-hashes it by hand get the same string; ``ensure_ascii=False`` keeps
    Azerbaijani legal names readable in a receiver's log.
    """
    document = {
        "delivery_id": str(delivery_id),
        "event_id": str(event_id),
        "type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "payload": payload,
        "created_at": created_at.isoformat(),
        # Repeated from the signed `t` so a receiver can log the delivery instant without
        # parsing the signature header.
        "delivered_at": delivered_at.isoformat(),
    }
    return json.dumps(document, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )


# ── delivery ────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Contract ``WebhookDelivery``: what the endpoint answered, or why it did not."""

    delivered: bool
    status_code: int | None
    duration_ms: int
    error: str | None = None
    attempts: int = 1


@dataclass(frozen=True, slots=True)
class Subscription:
    """A subscription snapshotted out of the session, so delivery holds no ORM state."""

    id: uuid.UUID
    url: str
    secret: str


def _retryable(status: int | None) -> bool:
    """A missing status (transport failure), a 429 or any 5xx is worth trying again."""
    return status is None or status == 429 or status >= 500


def deliver(
    url: str,
    secret: str,
    body: bytes,
    *,
    event_type: str,
    delivery_id: uuid.UUID,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryResult:
    """POST one signed delivery, retrying with exponential backoff.

    Each attempt is signed afresh: a retry an hour after the first attempt must carry a
    current timestamp, or the receiver's own replay window would reject it.
    """
    started = time.perf_counter()
    last: DeliveryResult | None = None
    for attempt in range(1, max(1, attempts) + 1):
        signature, _ = sign(secret, body)
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: signature,
            "X-VendorIQ-Event": event_type,
            "X-VendorIQ-Delivery": str(delivery_id),
            "X-VendorIQ-Attempt": str(attempt),
            "User-Agent": "VendorIQ-Webhook/1.0",
        }
        try:
            response = http_request(
                "POST", url, headers=headers, body=body, timeout=DELIVERY_TIMEOUT
            )
            status: int | None = response.status
            error = None if response.status < 400 else f"HTTP {response.status}"
        except TransportError as exc:
            status, error = None, exc.reason
        elapsed = int((time.perf_counter() - started) * 1000)
        last = DeliveryResult(
            delivered=status is not None and status < 400,
            status_code=status,
            duration_ms=elapsed,
            error=error,
            attempts=attempt,
        )
        if last.delivered or not _retryable(status) or attempt == attempts:
            return last
        sleep(backoff_seconds * (2 ** (attempt - 1)))
    return last or DeliveryResult(False, None, 0, "no attempt was made", 0)


# ── the dispatcher ──────────────────────────────────────────────────────────
_executor: Executor | None = None
_executor_lock = threading.Lock()
#: How a finished delivery is written back. Replaced in tests; see ``set_recorder``.
_recorder: Callable[[uuid.UUID, DeliveryResult], None] | None = None


def _default_executor() -> Executor:
    """Lazily built: importing this module must not start threads in a CLI or a test."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vendoriq-webhook")
        return _executor


def set_executor(executor: Executor | None) -> None:
    """Swap the delivery executor. ``None`` restores the lazily-built thread pool."""
    global _executor
    with _executor_lock:
        _executor = executor


def set_recorder(recorder: Callable[[uuid.UUID, DeliveryResult], None] | None) -> None:
    """Swap how a delivery result is written back. ``None`` restores the default session."""
    global _recorder
    _recorder = recorder


def record_result(webhook_id: uuid.UUID, result: DeliveryResult) -> None:
    """Update ``last_delivery_at`` / ``failure_count`` after a background delivery."""
    if _recorder is not None:
        _recorder(webhook_id, result)
        return
    with session_scope() as session:  # pragma: no cover - exercised by the worker, not tests
        row = session.get(Webhook, webhook_id)
        if row is None:
            return
        apply_result(row, result)


def apply_result(row: Webhook, result: DeliveryResult) -> None:
    """The bookkeeping one delivery leaves on its subscription."""
    row.last_delivery_at = datetime.now(UTC)
    row.failure_count = 0 if result.delivered else row.failure_count + 1


def subscribers_for(session: Session, event_type: str) -> list[Subscription]:
    """Active subscriptions naming this event, snapshotted away from the session."""
    rows = session.scalars(select(Webhook).where(Webhook.is_active.is_(True))).all()
    return [
        Subscription(id=row.id, url=row.url, secret=row.secret)
        for row in rows
        if event_type in [str(name) for name in row.events]
    ]


def _drain(session: Session) -> None:
    """Hand everything queued during the committed transaction to the executor."""
    queued: list[tuple[Subscription, bytes, str, uuid.UUID]] = session.info.pop(
        "vendoriq_webhook_queue", []
    )
    if not queued:
        return
    executor = _default_executor()
    for subscription, body, event_type, delivery_id in queued:
        executor.submit(_deliver_and_record, subscription, body, event_type, delivery_id)


def _deliver_and_record(
    subscription: Subscription, body: bytes, event_type: str, delivery_id: uuid.UUID
) -> None:
    """The background unit of work. Nothing raises out of here — ever."""
    try:
        result = deliver(
            subscription.url,
            subscription.secret,
            body,
            event_type=event_type,
            delivery_id=delivery_id,
        )
        record_result(subscription.id, result)
    # A webhook must never take the process down: everything is logged and stops here.
    except Exception:
        logger.exception("webhook delivery to subscription %s failed", subscription.id)


def dispatch(event: Event) -> None:
    """Installed into ``services.events`` — called for every domain event that is emitted.

    Does no I/O and never raises: it reads the subscriptions inside the caller's transaction
    and queues the deliveries for after the commit. A request that later rolls back
    therefore delivers nothing, and a request that succeeds is never slowed by a subscriber.
    """
    try:
        session = object_session(event)
        if session is None:  # pragma: no cover - an event detached from its session
            return
        subscriptions = subscribers_for(session, event.type)
        if not subscriptions:
            return
        moment = datetime.now(UTC)
        queue: list[tuple[Subscription, bytes, str, uuid.UUID]] = session.info.setdefault(
            "vendoriq_webhook_queue", []
        )
        for subscription in subscriptions:
            delivery_id = uuid.uuid4()
            body = delivery_body(
                event_id=event.id,
                event_type=event.type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                payload=dict(event.payload),
                created_at=event.created_at,
                delivered_at=moment,
                delivery_id=delivery_id,
            )
            queue.append((subscription, body, event.type, delivery_id))
        _arm(session)
    # Emitting a domain event must never fail the request that caused it.
    except Exception:
        logger.exception("could not queue webhook deliveries for event %s", event.type)


def _arm(session: Session) -> None:
    """Attach the after-commit drain to this session, once."""
    if session.info.get("vendoriq_webhook_armed"):
        return
    session.info["vendoriq_webhook_armed"] = True
    sa_event.listen(session, "after_commit", _drain)


def install_dispatcher() -> None:
    """Point ``services.events`` at :func:`dispatch`. Called when the router is imported."""
    events_service.set_dispatcher(dispatch)


def uninstall_dispatcher() -> None:
    events_service.set_dispatcher(None)


# ── subscription management ─────────────────────────────────────────────────
def list_webhooks(session: Session) -> list[Webhook]:
    return list(session.scalars(select(Webhook).order_by(Webhook.created_at.desc())))


def get(session: Session, webhook_id: uuid.UUID) -> Webhook:
    row = session.get(Webhook, webhook_id)
    if row is None:
        raise ApiError(404, "not_found", "No such webhook subscription.")
    return row


def _validate(url: str, event_names: Sequence[str]) -> tuple[str, list[str]]:
    cleaned = url.strip()
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        raise ApiError(
            422, "validation_error", "A webhook URL must be an absolute http(s) URL.", {"url": url}
        )
    unknown = sorted({name for name in event_names if name not in SUBSCRIBABLE_EVENTS})
    if unknown:
        raise ApiError(422, "validation_error", "Unknown event type.", {"events": unknown})
    if not event_names:
        raise ApiError(422, "validation_error", "A subscription must name at least one event.")
    return cleaned, list(dict.fromkeys(event_names))


def create(
    uow: UnitOfWork, *, url: str, events: Sequence[str], is_active: bool = True
) -> tuple[Webhook, str]:
    """Create a subscription. Returns ``(row, secret)`` — the secret is shown once."""
    cleaned_url, names = _validate(url, events)
    secret = new_secret()
    row = Webhook(
        url=cleaned_url,
        secret=secret,
        events=names,
        is_active=is_active,
        failure_count=0,
    )
    uow.session.add(row)
    uow.flush()
    audit.record(
        uow,
        entity_type="webhook",
        entity_id=row.id,
        action="create",
        # The secret is deliberately absent: an audit trail is exportable (spec §13).
        after={"url": row.url, "events": names, "is_active": row.is_active},
    )
    return row, secret


def update(
    uow: UnitOfWork,
    webhook_id: uuid.UUID,
    *,
    url: str,
    events: Sequence[str],
    is_active: bool = True,
) -> Webhook:
    """Replace a subscription's target and events. The secret is never rotated here."""
    row = get(uow.session, webhook_id)
    cleaned_url, names = _validate(url, events)
    before = {"url": row.url, "events": list(row.events), "is_active": row.is_active}
    row.url = cleaned_url
    row.events = names
    row.is_active = is_active
    uow.flush()
    audit.record(
        uow,
        entity_type="webhook",
        entity_id=row.id,
        action="update",
        before=before,
        after={"url": row.url, "events": names, "is_active": row.is_active},
    )
    return row


def delete(uow: UnitOfWork, webhook_id: uuid.UUID) -> None:
    row = get(uow.session, webhook_id)
    audit.record(
        uow,
        entity_type="webhook",
        entity_id=row.id,
        action="delete",
        before={"url": row.url, "events": list(row.events)},
    )
    uow.session.delete(row)
    uow.flush()


def send_test(uow: UnitOfWork, webhook_id: uuid.UUID) -> DeliveryResult:
    """Send one signed test delivery now and report what the endpoint answered.

    Synchronous and single-attempt on purpose: the officer pressed a button and is waiting
    for an answer, and "it failed but we will retry" is not an answer to "does this URL
    work?".
    """
    row = get(uow.session, webhook_id)
    delivery_id = uuid.uuid4()
    moment = datetime.now(UTC)
    body = delivery_body(
        event_id=delivery_id,
        event_type="webhook.test",
        entity_type="webhook",
        entity_id=row.id,
        payload={"message": "VendorIQ test delivery", "webhook_id": str(row.id)},
        created_at=moment,
        delivered_at=moment,
        delivery_id=delivery_id,
    )
    result = deliver(
        row.url,
        row.secret,
        body,
        event_type="webhook.test",
        delivery_id=delivery_id,
        attempts=1,
    )
    apply_result(row, result)
    uow.flush()
    audit.record(
        uow,
        entity_type="webhook",
        entity_id=row.id,
        action="test",
        after={
            "delivered": result.delivered,
            "status_code": result.status_code,
            "duration_ms": result.duration_ms,
        },
    )
    return result

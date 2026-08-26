"""Signed, expiring tokens: the session cookie, the CSRF token and storage URLs.

One primitive — an HMAC-SHA256 signature over a compact payload — carries all three. The
session is stateless so that a horizontally-scaled deployment needs no shared session store,
and revocation rides on ``User.is_active``, which every request checks anyway.
"""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from hashlib import sha256
from typing import Any


class TokenError(Exception):
    """The token is malformed, tampered with or expired. Never says which, to the caller."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict[str, Any], secret: str, *, ttl_seconds: int) -> str:
    """``<base64 payload>.<base64 signature>``; the expiry travels inside the payload."""
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    encoded = _b64encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def unsign(token: str, secret: str, *, now: float | None = None) -> dict[str, Any]:
    """Verify the signature, then the expiry. Raises :class:`TokenError` on any failure."""
    try:
        encoded, signature_b64 = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), sha256).digest()
        if not hmac.compare_digest(_b64decode(signature_b64), expected):
            raise TokenError("bad signature")
        payload = json.loads(_b64decode(encoded))
    except TokenError:
        raise
    except Exception as exc:  # malformed base64, malformed JSON, missing separator
        raise TokenError("malformed token") from exc
    if not isinstance(payload, dict):
        raise TokenError("malformed token")
    moment = time.time() if now is None else now
    if float(payload.get("exp", 0)) < moment:
        raise TokenError("expired")
    return payload


def new_csrf_token() -> str:
    """Random, unguessable, and stored in a *readable* cookie — the double-submit pair."""
    return secrets.token_urlsafe(32)


def csrf_matches(cookie_value: str | None, header_value: str | None) -> bool:
    """Double submit: the header the script sends must equal the cookie the browser holds.

    A cross-site request carries the cookie automatically but cannot read it to build the
    header, so the pair only matches for a request the site's own script made.
    """
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


def new_api_key() -> tuple[str, str]:
    """Return ``(plaintext, prefix)``. The plaintext is shown once and never stored."""
    body = secrets.token_urlsafe(32)
    prefix = body[:8]
    return f"vq_{prefix}_{body[8:]}", f"vq_{prefix}"

"""TOTP (RFC 6238) over HOTP (RFC 4226), implemented on ``hmac`` and ``hashlib``.

``pyotp`` is the declared dependency; it cannot be installed on the build host (ADR-005),
and the algorithm is forty lines, so it lives here. The implementation is the RFC, not an
approximation: 8-byte big-endian counter, HMAC-SHA1, dynamic truncation, modulo 10**digits.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

#: RFC 6238 §4 defaults. The whole system uses one step; there is no per-user override.
DEFAULT_DIGITS = 6
DEFAULT_STEP = 30


def generate_secret(length: int = 20) -> str:
    """A base32 secret of the RFC 4226 recommended strength (160 bits)."""
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padded = secret.strip().replace(" ", "").upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded, casefold=True)


def hotp(secret: str, counter: int, digits: int = DEFAULT_DIGITS) -> str:
    """RFC 4226 §5.3 — HMAC-SHA1, dynamic truncation, decimal modulo."""
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def totp(
    secret: str,
    *,
    at: float | None = None,
    step: int = DEFAULT_STEP,
    digits: int = DEFAULT_DIGITS,
) -> str:
    """The code for the step containing ``at`` (default: now)."""
    moment = time.time() if at is None else at
    return hotp(secret, int(moment // step), digits)


def verify(
    secret: str,
    code: str,
    *,
    at: float | None = None,
    step: int = DEFAULT_STEP,
    window: int = 1,
    digits: int = DEFAULT_DIGITS,
) -> bool:
    """Accept ``code`` for the current step or ±``window`` steps around it.

    The window exists because the user's clock drifts and because they type slowly; RFC 6238
    §5.2 recommends at most one step either side, which is the default.
    """
    candidate = code.strip()
    if not candidate.isdigit() or len(candidate) != digits:
        return False
    moment = time.time() if at is None else at
    counter = int(moment // step)
    return any(
        hmac.compare_digest(hotp(secret, counter + offset, digits), candidate)
        for offset in range(-window, window + 1)
    )


def provisioning_uri(secret: str, account: str, issuer: str = "VendorIQ") -> str:
    """``otpauth://`` URI for an authenticator app — shown once, at enrolment."""
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DEFAULT_DIGITS}&period={DEFAULT_STEP}"
    )

"""Authentication and authorisation primitives (brief §2, spec §3, §13)."""

from __future__ import annotations

from .deps import get_principal, get_uow, require, scope_to_vendor
from .hashing import hash_password, hash_token, tokens_match, verify_password
from .permissions import PERMISSIONS, PUBLIC_OPERATIONS, Permission, permission_for
from .principal import Principal
from .tokens import TokenError, new_api_key, new_csrf_token, sign, unsign

__all__ = [
    "PERMISSIONS",
    "PUBLIC_OPERATIONS",
    "Permission",
    "Principal",
    "TokenError",
    "get_principal",
    "get_uow",
    "hash_password",
    "hash_token",
    "new_api_key",
    "new_csrf_token",
    "permission_for",
    "require",
    "scope_to_vendor",
    "sign",
    "tokens_match",
    "unsign",
    "verify_password",
]

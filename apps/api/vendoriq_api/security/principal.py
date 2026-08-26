"""Who is calling: a person with a role, or a machine with scopes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from ..models.enums import UserRole
from .permissions import Permission, operations_for_role, operations_for_scopes


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated identity for one request.

    A user principal carries a role and, for vendors, the vendor it is confined to. An API
    key principal carries scopes and no role at all — a machine is never "an officer", so
    role-only operations (creating accounts, minting keys) are closed to it by construction.
    """

    kind: Literal["user", "api_key"]
    user_id: uuid.UUID | None = None
    email: str | None = None
    role: UserRole | None = None
    vendor_id: uuid.UUID | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    api_key_id: uuid.UUID | None = None

    @property
    def is_vendor(self) -> bool:
        return self.role is UserRole.VENDOR

    def may(self, permission: Permission) -> bool:
        """Role membership for people, scope membership for machines."""
        if self.kind == "user":
            return self.role is not None and self.role in permission.roles
        return permission.scope is not None and permission.scope in self.scopes

    def permitted_operations(self) -> list[str]:
        if self.kind == "user" and self.role is not None:
            return operations_for_role(self.role)
        return operations_for_scopes(self.scopes)

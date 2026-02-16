from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user


class Role(StrEnum):
    ADMIN = "Admin"
    NETWORK = "Network"
    SECURITY = "Security"
    DC_MANAGER = "DC Manager"
    APPROVER = "Approver"
    VIEWER = "Viewer"


ROLE_ALIASES = {
    "admin": Role.ADMIN.value,
    "network": Role.NETWORK.value,
    "security": Role.SECURITY.value,
    "dc manager": Role.DC_MANAGER.value,
    "dc_manager": Role.DC_MANAGER.value,
    "dcmanager": Role.DC_MANAGER.value,
    "approver": Role.APPROVER.value,
    "viewer": Role.VIEWER.value,
}


def normalize_role(role: str) -> str:
    return ROLE_ALIASES.get(role.strip().lower(), role.strip())


def has_role(user_roles: list[str], required_role: Role) -> bool:
    normalized_roles = {normalize_role(role) for role in user_roles}
    return required_role.value in normalized_roles or Role.ADMIN.value in normalized_roles


def require_role(*roles: Role):
    """FastAPI dependency that checks if the current user has one of the required roles."""

    async def _check(current_user: Any = Depends(get_current_user)):
        user_role = normalize_role(current_user.role)
        if user_role == Role.ADMIN.value:
            return current_user
        if user_role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not authorized. Required: {[r.value for r in roles]}",
            )
        return current_user

    return _check

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
import logging
from .jwt_handler import jwt_handler
from .models import User, Permission, get_user_permissions
from .user_service import user_service

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


class CurrentUser:
    """Current authenticated user context."""

    def __init__(self, user: User, permissions: List[Permission]):
        self.user = user
        self.permissions = permissions

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return self.user.role.value == role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user."""
    try:
        # Verify token
        payload = jwt_handler.verify_token(credentials.credentials)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        await user_service.initialize()
        user = await user_service.get_user_by_id(int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if user.status.value != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is not active",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_context(
    current_user: User = Depends(get_current_user),
) -> CurrentUser:
    """Get the current user with permissions context."""
    permissions = get_user_permissions(current_user.role)
    return CurrentUser(user=current_user, permissions=permissions)


def require_permission(permission: Permission):
    """Dependency factory for requiring specific permissions."""

    async def permission_checker(
        user_context: CurrentUser = Depends(get_current_user_context),
    ):
        if not user_context.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission.value}",
            )
        return user_context

    return permission_checker


def require_role(role: str):
    """Dependency factory for requiring specific roles."""

    async def role_checker(
        user_context: CurrentUser = Depends(get_current_user_context),
    ):
        if not user_context.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Role required: {role}"
            )
        return user_context

    return role_checker


# Common permission dependencies
require_admin = require_permission(Permission.SYSTEM_ADMIN)
require_user_management = require_permission(Permission.USER_MANAGE)
require_inventory_write = require_permission(Permission.INVENTORY_WRITE)
require_operations_write = require_permission(Permission.OPERATIONS_WRITE)
require_safety_write = require_permission(Permission.SAFETY_WRITE)
require_reports_view = require_permission(Permission.REPORTS_VIEW)


# Optional authentication (for endpoints that work with or without auth)
async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Get the current user if authenticated, otherwise return None."""
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def get_optional_user_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[CurrentUser]:
    """Get the current user context if authenticated, otherwise return None."""
    if not credentials:
        return None

    try:
        user = await get_current_user(credentials)
        permissions = get_user_permissions(user.role)
        return CurrentUser(user=user, permissions=permissions)
    except HTTPException:
        return None

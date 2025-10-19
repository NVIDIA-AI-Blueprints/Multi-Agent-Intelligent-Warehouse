from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from typing import List
import logging
from ..services.auth.models import (
    User,
    UserCreate,
    UserUpdate,
    UserLogin,
    Token,
    TokenRefresh,
    PasswordChange,
    UserRole,
    UserStatus,
)
from ..services.auth.user_service import user_service
from ..services.auth.jwt_handler import jwt_handler
from ..services.auth.dependencies import (
    get_current_user,
    get_current_user_context,
    CurrentUser,
    require_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Authentication"])


@router.post("/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate, admin_user: CurrentUser = Depends(require_admin)
):
    """Register a new user (admin only)."""
    try:
        await user_service.initialize()
        user = await user_service.create_user(user_create)
        logger.info(f"User {user.username} created by admin {admin_user.user.username}")
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )


@router.post("/auth/login", response_model=Token)
async def login(user_login: UserLogin):
    """Authenticate user and return tokens."""
    try:
        await user_service.initialize()

        # Get user with hashed password
        user = await user_service.get_user_for_auth(user_login.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Check if user is active
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is not active",
            )

        # Verify password
        if not jwt_handler.verify_password(user_login.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Update last login
        await user_service.update_last_login(user.id)

        # Create tokens
        user_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
        }

        tokens = jwt_handler.create_token_pair(user_data)
        logger.info(f"User {user.username} logged in successfully")

        return Token(**tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed"
        )


@router.post("/auth/refresh", response_model=Token)
async def refresh_token(token_refresh: TokenRefresh):
    """Refresh access token using refresh token."""
    try:
        # Verify refresh token
        payload = jwt_handler.verify_token(
            token_refresh.refresh_token, token_type="refresh"
        )
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        # Get user
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        await user_service.initialize()
        user = await user_service.get_user_by_id(int(user_id))
        if not user or user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Create new tokens
        user_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
        }

        tokens = jwt_handler.create_token_pair(user_data)
        return Token(**tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        )


@router.get("/auth/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.put("/auth/me", response_model=User)
async def update_current_user(
    user_update: UserUpdate, current_user: User = Depends(get_current_user)
):
    """Update current user information."""
    try:
        await user_service.initialize()
        updated_user = await user_service.update_user(current_user.id, user_update)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        logger.info(f"User {current_user.username} updated their profile")
        return updated_user
    except Exception as e:
        logger.error(f"User update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed"
        )


@router.post("/auth/change-password")
async def change_password(
    password_change: PasswordChange, current_user: User = Depends(get_current_user)
):
    """Change current user's password."""
    try:
        await user_service.initialize()
        success = await user_service.change_password(
            current_user.id,
            password_change.current_password,
            password_change.new_password,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        logger.info(f"User {current_user.username} changed their password")
        return {"message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed",
        )


@router.get("/auth/users", response_model=List[User])
async def get_all_users(admin_user: CurrentUser = Depends(require_admin)):
    """Get all users (admin only)."""
    try:
        await user_service.initialize()
        users = await user_service.get_all_users()
        return users
    except Exception as e:
        logger.error(f"Failed to get users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users",
        )


@router.get("/auth/users/{user_id}", response_model=User)
async def get_user(user_id: int, admin_user: CurrentUser = Depends(require_admin)):
    """Get a specific user (admin only)."""
    try:
        await user_service.initialize()
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user",
        )


@router.put("/auth/users/{user_id}", response_model=User)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    admin_user: CurrentUser = Depends(require_admin),
):
    """Update a user (admin only)."""
    try:
        await user_service.initialize()
        updated_user = await user_service.update_user(user_id, user_update)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        logger.info(
            f"Admin {admin_user.user.username} updated user {updated_user.username}"
        )
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed"
        )


@router.get("/auth/roles")
async def get_available_roles():
    """Get available user roles."""
    return {
        "roles": [
            {"value": role.value, "label": role.value.title()} for role in UserRole
        ]
    }


@router.get("/auth/permissions")
async def get_user_permissions(current_user: User = Depends(get_current_user)):
    """Get current user's permissions."""
    from ..services.auth.models import get_user_permissions

    permissions = get_user_permissions(current_user.role)
    return {"permissions": [permission.value for permission in permissions]}

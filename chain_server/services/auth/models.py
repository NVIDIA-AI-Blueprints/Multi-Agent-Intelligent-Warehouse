from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum
from datetime import datetime


class UserRole(str, Enum):
    """User roles in the system."""

    ADMIN = "admin"
    MANAGER = "manager"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class UserBase(BaseModel):
    """Base user model."""

    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE


class UserCreate(UserBase):
    """User creation model."""

    password: str


class UserUpdate(BaseModel):
    """User update model."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserInDB(UserBase):
    """User model for database storage."""

    id: int
    hashed_password: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class User(UserBase):
    """User model for API responses."""

    id: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class UserLogin(BaseModel):
    """User login model."""

    username: str
    password: str


class Token(BaseModel):
    """Token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    """Token refresh model."""

    refresh_token: str


class PasswordChange(BaseModel):
    """Password change model."""

    current_password: str
    new_password: str


class Permission(str, Enum):
    """System permissions."""

    # Inventory permissions
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    INVENTORY_DELETE = "inventory:delete"

    # Operations permissions
    OPERATIONS_READ = "operations:read"
    OPERATIONS_WRITE = "operations:write"
    OPERATIONS_ASSIGN = "operations:assign"

    # Safety permissions
    SAFETY_READ = "safety:read"
    SAFETY_WRITE = "safety:write"
    SAFETY_APPROVE = "safety:approve"

    # System permissions
    SYSTEM_ADMIN = "system:admin"
    USER_MANAGE = "user:manage"
    REPORTS_VIEW = "reports:view"


# Role-based permissions mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        Permission.INVENTORY_READ,
        Permission.INVENTORY_WRITE,
        Permission.INVENTORY_DELETE,
        Permission.OPERATIONS_READ,
        Permission.OPERATIONS_WRITE,
        Permission.OPERATIONS_ASSIGN,
        Permission.SAFETY_READ,
        Permission.SAFETY_WRITE,
        Permission.SAFETY_APPROVE,
        Permission.SYSTEM_ADMIN,
        Permission.USER_MANAGE,
        Permission.REPORTS_VIEW,
    ],
    UserRole.MANAGER: [
        Permission.INVENTORY_READ,
        Permission.INVENTORY_WRITE,
        Permission.OPERATIONS_READ,
        Permission.OPERATIONS_WRITE,
        Permission.OPERATIONS_ASSIGN,
        Permission.SAFETY_READ,
        Permission.SAFETY_WRITE,
        Permission.REPORTS_VIEW,
    ],
    UserRole.SUPERVISOR: [
        Permission.INVENTORY_READ,
        Permission.INVENTORY_WRITE,
        Permission.OPERATIONS_READ,
        Permission.OPERATIONS_WRITE,
        Permission.OPERATIONS_ASSIGN,
        Permission.SAFETY_READ,
        Permission.SAFETY_WRITE,
    ],
    UserRole.OPERATOR: [
        Permission.INVENTORY_READ,
        Permission.OPERATIONS_READ,
        Permission.SAFETY_READ,
        Permission.SAFETY_WRITE,
    ],
    UserRole.VIEWER: [
        Permission.INVENTORY_READ,
        Permission.OPERATIONS_READ,
        Permission.SAFETY_READ,
    ],
}


def get_user_permissions(role: UserRole) -> List[Permission]:
    """Get permissions for a user role."""
    return ROLE_PERMISSIONS.get(role, [])

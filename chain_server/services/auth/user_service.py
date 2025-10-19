from typing import Optional, List
from datetime import datetime
import logging
from inventory_retriever.structured.sql_retriever import get_sql_retriever
from .models import User, UserCreate, UserUpdate, UserInDB, UserRole, UserStatus
from .jwt_handler import jwt_handler

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations."""

    def __init__(self):
        self.sql_retriever = None
        self._initialized = False

    async def initialize(self):
        """Initialize the database connection."""
        if not self._initialized:
            self.sql_retriever = await get_sql_retriever()
            self._initialized = True

    async def create_user(self, user_create: UserCreate) -> User:
        """Create a new user."""
        try:
            # Check if user already exists
            existing_user = await self.get_user_by_username(user_create.username)
            if existing_user:
                raise ValueError(
                    f"User with username {user_create.username} already exists"
                )

            existing_email = await self.get_user_by_email(user_create.email)
            if existing_email:
                raise ValueError(f"User with email {user_create.email} already exists")

            # Hash password
            hashed_password = jwt_handler.hash_password(user_create.password)

            # Insert user
            query = """
                INSERT INTO users (username, email, full_name, role, status, hashed_password, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                RETURNING id, username, email, full_name, role, status, created_at, updated_at, last_login
            """
            result = await self.sql_retriever.fetch_one(
                query,
                user_create.username,
                user_create.email,
                user_create.full_name,
                user_create.role.value,
                user_create.status.value,
                hashed_password,
            )

            return User(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        try:
            query = """
                SELECT id, username, email, full_name, role, status, created_at, updated_at, last_login
                FROM users
                WHERE id = $1
            """
            result = await self.sql_retriever.fetch_one(query, user_id)

            if not result:
                return None

            return User(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {e}")
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        try:
            query = """
                SELECT id, username, email, full_name, role, status, created_at, updated_at, last_login
                FROM users
                WHERE username = $1
            """
            result = await self.sql_retriever.fetch_one(query, username)

            if not result:
                return None

            return User(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to get user by username {username}: {e}")
            return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        try:
            query = """
                SELECT id, username, email, full_name, role, status, created_at, updated_at, last_login
                FROM users
                WHERE email = $1
            """
            result = await self.sql_retriever.fetch_one(query, email)

            if not result:
                return None

            return User(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to get user by email {email}: {e}")
            return None

    async def get_user_for_auth(self, username: str) -> Optional[UserInDB]:
        """Get user with hashed password for authentication."""
        try:
            query = """
                SELECT id, username, email, full_name, role, status, hashed_password, created_at, updated_at, last_login
                FROM users
                WHERE username = $1
            """
            result = await self.sql_retriever.fetch_one(query, username)

            if not result:
                return None

            return UserInDB(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                hashed_password=result["hashed_password"],
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to get user for auth {username}: {e}")
            return None

    async def update_user(
        self, user_id: int, user_update: UserUpdate
    ) -> Optional[User]:
        """Update a user."""
        try:
            # Build update query dynamically
            update_fields = []
            params = []
            param_count = 1

            if user_update.email is not None:
                update_fields.append(f"email = ${param_count}")
                params.append(user_update.email)
                param_count += 1

            if user_update.full_name is not None:
                update_fields.append(f"full_name = ${param_count}")
                params.append(user_update.full_name)
                param_count += 1

            if user_update.role is not None:
                update_fields.append(f"role = ${param_count}")
                params.append(user_update.role.value)
                param_count += 1

            if user_update.status is not None:
                update_fields.append(f"status = ${param_count}")
                params.append(user_update.status.value)
                param_count += 1

            if not update_fields:
                return await self.get_user_by_id(user_id)

            update_fields.append(f"updated_at = NOW()")
            params.append(user_id)

            query = f"""
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE id = ${param_count}
                RETURNING id, username, email, full_name, role, status, created_at, updated_at, last_login
            """

            result = await self.sql_retriever.fetch_one(query, *params)

            if not result:
                return None

            return User(
                id=result["id"],
                username=result["username"],
                email=result["email"],
                full_name=result["full_name"],
                role=UserRole(result["role"]),
                status=UserStatus(result["status"]),
                created_at=result["created_at"],
                updated_at=result["updated_at"],
                last_login=result["last_login"],
            )
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return None

    async def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        try:
            query = """
                UPDATE users 
                SET last_login = NOW()
                WHERE id = $1
            """
            await self.sql_retriever.execute_command(query, user_id)
        except Exception as e:
            logger.error(f"Failed to update last login for user {user_id}: {e}")

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> bool:
        """Change user password."""
        try:
            # Get current user with hashed password
            query = """
                SELECT hashed_password
                FROM users
                WHERE id = $1
            """
            result = await self.sql_retriever.fetch_one(query, user_id)

            if not result:
                return False

            # Verify current password
            if not jwt_handler.verify_password(
                current_password, result["hashed_password"]
            ):
                return False

            # Hash new password
            new_hashed_password = jwt_handler.hash_password(new_password)

            # Update password
            update_query = """
                UPDATE users 
                SET hashed_password = $1, updated_at = NOW()
                WHERE id = $2
            """
            await self.sql_retriever.execute_command(
                update_query, new_hashed_password, user_id
            )

            return True
        except Exception as e:
            logger.error(f"Failed to change password for user {user_id}: {e}")
            return False

    async def get_all_users(self) -> List[User]:
        """Get all users."""
        try:
            query = """
                SELECT id, username, email, full_name, role, status, created_at, updated_at, last_login
                FROM users
                ORDER BY created_at DESC
            """
            results = await self.sql_retriever.fetch_all(query)

            users = []
            for result in results:
                users.append(
                    User(
                        id=result["id"],
                        username=result["username"],
                        email=result["email"],
                        full_name=result["full_name"],
                        role=UserRole(result["role"]),
                        status=UserStatus(result["status"]),
                        created_at=result["created_at"],
                        updated_at=result["updated_at"],
                        last_login=result["last_login"],
                    )
                )

            return users
        except Exception as e:
            logger.error(f"Failed to get all users: {e}")
            return []


# Global instance
user_service = UserService()

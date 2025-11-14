from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt
import os
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class JWTHandler:
    """Handle JWT token creation, validation, and password operations."""

    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.access_token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.access_token_expire_minutes
            )

        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(
        self, token: str, token_type: str = "access"
    ) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Check token type
            if payload.get("type") != token_type:
                logger.warning(
                    f"Invalid token type: expected {token_type}, got {payload.get('type')}"
                )
                return None

            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
                logger.warning("Token has expired")
                return None

            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError as e:
            logger.warning(f"JWT error: {e}")
            return None

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def create_token_pair(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Create both access and refresh tokens for a user."""
        access_token = self.create_access_token(user_data)
        refresh_token = self.create_refresh_token(user_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }


# Global instance
jwt_handler = JWTHandler()

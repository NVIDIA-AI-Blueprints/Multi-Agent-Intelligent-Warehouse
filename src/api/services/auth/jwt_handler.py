from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import bcrypt
import os
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Security: Require JWT_SECRET_KEY in production, allow default in development with warning
if not SECRET_KEY or SECRET_KEY == "your-secret-key-change-in-production":
    if ENVIRONMENT == "production":
        import sys
        logger.error("JWT_SECRET_KEY environment variable must be set with a secure value in production")
        logger.error("Please set JWT_SECRET_KEY in your .env file or environment")
        sys.exit(1)
    else:
        # Development: Use a default but warn
        SECRET_KEY = "dev-secret-key-change-in-production-not-for-production-use"
        logger.warning("⚠️  WARNING: Using default JWT_SECRET_KEY for development. This is NOT secure for production!")
        logger.warning("⚠️  Please set JWT_SECRET_KEY in your .env file for production use")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


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
        # Use bcrypt directly to avoid passlib compatibility issues
        # Bcrypt has a 72-byte limit, so truncate if necessary
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            # Use bcrypt directly to avoid passlib compatibility issues
            # Bcrypt has a 72-byte limit, so truncate if necessary
            password_bytes = plain_password.encode('utf-8')
            if len(password_bytes) > 72:
                password_bytes = password_bytes[:72]
            
            hash_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except (ValueError, TypeError, Exception) as e:
            logger.warning(f"Password verification error: {e}")
            return False

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

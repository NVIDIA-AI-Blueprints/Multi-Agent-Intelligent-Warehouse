from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import bcrypt
import os
import logging
import secrets

logger = logging.getLogger(__name__)

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Security: Minimum key length requirements per algorithm (in bytes)
# HS256 requires minimum 256 bits (32 bytes) per RFC 7518 Section 3.2
# We enforce 32 bytes minimum, recommend 64+ bytes for better security
MIN_KEY_LENGTH_HS256 = 32  # 256 bits minimum
RECOMMENDED_KEY_LENGTH_HS256 = 64  # 512 bits recommended


def validate_jwt_secret_key(secret_key: str, algorithm: str, environment: str) -> bool:
    """
    Validate JWT secret key strength to prevent weak encryption vulnerabilities.
    
    This addresses CVE-2025-45768 (PyJWT weak encryption) by enforcing minimum
    key length requirements per RFC 7518 and NIST SP800-117 standards.
    
    Args:
        secret_key: The JWT secret key to validate
        algorithm: The JWT algorithm (e.g., 'HS256')
        environment: Environment name ('production' or 'development')
    
    Returns:
        True if key is valid, False otherwise
    
    Raises:
        ValueError: If key is too weak (in production) or invalid
    """
    if not secret_key:
        return False
    
    # Calculate key length in bytes (UTF-8 encoding)
    key_bytes = len(secret_key.encode('utf-8'))
    
    # Validate based on algorithm
    if algorithm == "HS256":
        min_length = MIN_KEY_LENGTH_HS256
        recommended_length = RECOMMENDED_KEY_LENGTH_HS256
        
        if key_bytes < min_length:
            error_msg = (
                f"JWT_SECRET_KEY is too weak for {algorithm}. "
                f"Minimum length: {min_length} bytes (256 bits), "
                f"Current length: {key_bytes} bytes. "
                f"This violates RFC 7518 Section 3.2 and NIST SP800-117 standards."
            )
            if environment == "production":
                logger.error(f"❌ SECURITY ERROR: {error_msg}")
                raise ValueError(error_msg)
            else:
                logger.warning(f"⚠️  WARNING: {error_msg}")
                logger.warning("⚠️  This key is too weak and should not be used in production!")
                return False
        
        if key_bytes < recommended_length:
            logger.warning(
                f"⚠️  JWT_SECRET_KEY length ({key_bytes} bytes) is below recommended "
                f"length ({recommended_length} bytes) for {algorithm}. "
                f"Consider using a longer key for better security."
            )
        else:
            logger.info(f"✅ JWT_SECRET_KEY validated: {key_bytes} bytes (meets security requirements)")
    
    return True


# Load and validate JWT secret key
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Security: Require JWT_SECRET_KEY in production, allow default in development with warning
if not SECRET_KEY or SECRET_KEY == "your-secret-key-change-in-production":
    if ENVIRONMENT == "production":
        import sys
        logger.error("JWT_SECRET_KEY environment variable must be set with a secure value in production")
        logger.error("Please set JWT_SECRET_KEY in your .env file or environment")
        logger.error("Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(64))\"")
        sys.exit(1)
    else:
        # Development: Use a default but warn
        SECRET_KEY = "dev-secret-key-change-in-production-not-for-production-use"
        logger.warning("⚠️  WARNING: Using default JWT_SECRET_KEY for development. This is NOT secure for production!")
        logger.warning("⚠️  Please set JWT_SECRET_KEY in your .env file for production use")

# Validate key strength (addresses CVE-2025-45768)
try:
    validate_jwt_secret_key(SECRET_KEY, ALGORITHM, ENVIRONMENT)
except ValueError as e:
    # In production, validation failure is fatal
    if ENVIRONMENT == "production":
        import sys
        logger.error(f"❌ JWT_SECRET_KEY validation failed: {e}")
        logger.error("Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(64))\"")
        sys.exit(1)


class JWTHandler:
    """
    Handle JWT token creation, validation, and password operations.
    
    Security Hardening (Addresses CVE-2025-45768 and algorithm confusion):
    - Enforces strong algorithms: Only HS256 allowed, explicitly rejects 'none'
    - Prevents algorithm confusion: Hardcodes algorithm in decode, ignores token header
    - Strong key validation: Minimum 32 bytes (256 bits) for HS256, recommends 64+ bytes
    - Comprehensive claim validation: Requires 'exp' and 'iat', validates all claims
    - Signature verification: Always verifies signatures, never accepts unsigned tokens
    
    Key Management:
    - Keys must be stored in a secret manager (AWS Secrets Manager, HashiCorp Vault, etc.)
    - Keys should be rotated regularly (recommended: every 90 days)
    - During rotation, support multiple active keys using key IDs (kid) in JWT header
    - Never store keys in plain text environment variables in production
    """

    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.access_token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT access token with security hardening.
        
        Security features:
        - Always includes 'exp' (expiration) and 'iat' (issued at) claims
        - Uses explicit algorithm (HS256) to prevent algorithm confusion
        - Never allows 'none' algorithm
        """
        to_encode = data.copy()
        now = datetime.utcnow()
        
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=self.access_token_expire_minutes)

        # Always include exp and iat for proper validation
        to_encode.update({
            "exp": expire,
            "iat": now,  # Issued at time
            "type": "access"
        })
        
        # Explicitly use algorithm to prevent algorithm confusion attacks
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Create a JWT refresh token with security hardening.
        
        Security features:
        - Always includes 'exp' (expiration) and 'iat' (issued at) claims
        - Uses explicit algorithm (HS256) to prevent algorithm confusion
        - Never allows 'none' algorithm
        """
        to_encode = data.copy()
        now = datetime.utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)
        
        # Always include exp and iat for proper validation
        to_encode.update({
            "exp": expire,
            "iat": now,  # Issued at time
            "type": "refresh"
        })
        
        # Explicitly use algorithm to prevent algorithm confusion attacks
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(
        self, token: str, token_type: str = "access"
    ) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a JWT token with comprehensive security hardening.
        
        Security features:
        - Explicitly rejects 'none' algorithm (algorithm confusion prevention)
        - Hardcodes allowed algorithm (HS256) - never accepts token header's algorithm
        - Requires signature verification
        - Requires 'exp' and 'iat' claims
        - Validates token type
        - Prevents algorithm confusion attacks
        
        This addresses CVE-2025-45768 and algorithm confusion vulnerabilities.
        """
        try:
            # Decode token header first to check algorithm
            # This prevents algorithm confusion attacks
            unverified_header = jwt.get_unverified_header(token)
            token_algorithm = unverified_header.get("alg")
            
            # CRITICAL: Explicitly reject 'none' algorithm
            if token_algorithm == "none":
                logger.warning("❌ SECURITY: Token uses 'none' algorithm - REJECTED")
                return None
            
            # CRITICAL: Only accept our hardcoded algorithm, ignore token header
            # This prevents algorithm confusion attacks where attacker tries to
            # force use of a different algorithm (e.g., HS256 with RSA public key)
            if token_algorithm != self.algorithm:
                logger.warning(
                    f"❌ SECURITY: Token algorithm mismatch - expected {self.algorithm}, "
                    f"got {token_algorithm} - REJECTED"
                )
                return None
            
            # Decode with strict security options
            # - algorithms=[self.algorithm]: Only accept our hardcoded algorithm
            # - verify_signature=True: Explicitly require signature verification
            # - require=["exp", "iat"]: Require expiration and issued-at claims
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],  # Hardcoded - never accept token's algorithm
                options={
                    "verify_signature": True,  # Explicitly require signature verification
                    "require": ["exp", "iat"],  # Require expiration and issued-at
                    "verify_exp": True,  # Verify expiration
                    "verify_iat": True,  # Verify issued-at
                },
            )

            # Additional token type validation
            if payload.get("type") != token_type:
                logger.warning(
                    f"Invalid token type: expected {token_type}, got {payload.get('type')}"
                )
                return None

            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except jwt.JWTError as e:
            logger.warning(f"JWT error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {e}")
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

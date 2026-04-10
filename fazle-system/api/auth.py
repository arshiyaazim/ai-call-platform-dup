# ============================================================
# Fazle API — JWT Authentication Utilities
# Token creation, verification, and password hashing
# ============================================================
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Header
import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from pydantic_settings import BaseSettings

logger = logging.getLogger("fazle-api")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days


class AuthSettings(BaseSettings):
    jwt_secret: str  # Required — fails fast if FAZLE_JWT_SECRET not set

    class Config:
        env_prefix = "FAZLE_"


auth_settings = AuthSettings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, auth_settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, auth_settings.jwt_secret, algorithms=[ALGORITHM])


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> dict:
    """Accept either JWT (Authorization: Bearer) or API key (X-API-Key)."""
    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = decode_access_token(token)
        except PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        from database import get_user_by_id
        user = get_user_by_id(user_id)
        if not user or not user.get("is_active"):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user

    # Fall back to API key
    api_key = os.getenv("FAZLE_API_KEY", "")
    if x_api_key and api_key and hmac.compare_digest(x_api_key.strip(), api_key.strip()):
        return {"id": "api-key", "email": "system", "name": "API Key", "role": "admin", "relationship_to_azim": "self"}

    raise HTTPException(status_code=401, detail="Missing or invalid authorization header")


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Try to extract user from JWT, return None if no auth header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require the current user to have admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

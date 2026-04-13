"""
Auth Dependencies
=================
FastAPI dependencies for extracting authenticated user identity from requests.

Provides two levels of granularity:
    get_current_user_id  — Returns just the user_id (str). Lightweight.
    get_current_user     — Returns full User model. Use when you need email/name/pic.

Both use HTTPBearer for:
    ✅ Automatic Swagger UI "Authorize" button
    ✅ Clean separation from manual header parsing
    ✅ Standard 401 on missing/invalid tokens

Usage:
    from src.core.deps import get_current_user_id, get_current_user

    @router.get("/recommendations")
    def recs(user_id: str = Depends(get_current_user_id)):
        ...

    @router.post("/interact")
    def interact(body: ..., user: User = Depends(get_current_user)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .security import decode_access_token
from ..user_models import User

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
# and auto-generates the 🔒 button in Swagger UI.
_bearer_scheme = HTTPBearer()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """
    Lightweight dependency: decode JWT → return user_id string.

    Raises 401 if token is missing, expired, or malformed.
    """
    payload = decode_access_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user_id",
        )

    return str(user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> User:
    """
    Full dependency: decode JWT → return User model with all profile fields.

    The JWT payload is expected to contain:
        user_id, email, name (optional), profile_pic (optional)
    """
    payload = decode_access_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user_id",
        )

    return User(
        user_id=str(user_id),
        email=payload.get("email", ""),
        name=payload.get("name"),
        profile_pic=payload.get("profile_pic"),
    )

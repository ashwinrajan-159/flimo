"""
JWT Security Utilities
======================
Stateless JWT creation and verification using python-jose.

Token payload convention:
    {
        "user_id": "<uuid-string>",   # Primary identifier
        "email":   "user@example.com",
        "name":    "Display Name",
        "profile_pic": "https://...",
        "exp":     <unix-timestamp>
    }

Usage:
    from src.core.security import create_access_token, decode_access_token

    token = create_access_token("user-uuid-123")
    payload = decode_access_token(token)  # returns dict or None
"""

import os
from datetime import datetime, timedelta
from jose import jwt, JWTError

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
ALGORITHM = "HS256"
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours


def create_access_token(user_id: str, extra_claims: dict = None) -> str:
    """
    Generate a signed JWT containing user_id + optional extra claims.

    Args:
        user_id:      Unique user identifier (UUID string).
        extra_claims: Optional dict merged into payload (email, name, etc.)

    Returns:
        Encoded JWT string.
    """
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """
    Verify signature + expiration and return the decoded payload.

    Returns:
        Decoded dict on success, None on any failure (expired, tampered, malformed).
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

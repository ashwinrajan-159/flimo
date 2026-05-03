"""
JWT Security Utilities
======================
Stateless JWT creation and verification.

Supports two flows:
  1. App-issued JWT (HS256, symmetric key) — used for internal tokens
  2. AWS Cognito JWT (RS256, asymmetric JWKS) — used for verifying Cognito id_tokens

Token payload convention (app JWT):
    {
        "user_id": "<uuid-string>",
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
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError, jwk
import requests as http_requests

logger = logging.getLogger(__name__)

# --- App JWT config (HS256) ---
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
ALGORITHM = "HS256"
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

# --- Cognito JWKS cache ---
_cognito_jwks_cache: Optional[dict] = None


def create_access_token(user_id: str, extra_claims: dict = None) -> str:
    """
    Generate a signed app JWT containing user_id + optional extra claims.
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
    Verify app JWT signature + expiration and return decoded payload.
    Returns None on any failure.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# --- Cognito JWT verification ---

def _get_cognito_jwks(region: str, user_pool_id: str) -> dict:
    """Fetch and cache Cognito JWKS (JSON Web Key Set)."""
    global _cognito_jwks_cache
    if _cognito_jwks_cache:
        return _cognito_jwks_cache

    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{user_pool_id}/.well-known/jwks.json"
    )
    try:
        response = http_requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        _cognito_jwks_cache = response.json()
        logger.info(f"Fetched Cognito JWKS from {jwks_url}")
        return _cognito_jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch Cognito JWKS: {e}")
        return {"keys": []}


def verify_cognito_token(token: str, region: str, user_pool_id: str, client_id: str) -> dict | None:
    """
    Verify an AWS Cognito JWT (id_token) using JWKS.

    Returns decoded payload on success, None on failure.
    Extracts: sub (cognito user id), email, name, etc.
    """
    try:
        # Get the key ID from the token header
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            logger.warning("Cognito token missing kid header")
            return None

        # Fetch JWKS
        jwks = _get_cognito_jwks(region, user_pool_id)
        keys = jwks.get("keys", [])

        # Find the matching key
        matching_key = None
        for key_data in keys:
            if key_data.get("kid") == kid:
                matching_key = key_data
                break

        if not matching_key:
            logger.warning(f"No matching JWKS key found for kid={kid}")
            # Invalidate cache and retry once
            global _cognito_jwks_cache
            _cognito_jwks_cache = None
            jwks = _get_cognito_jwks(region, user_pool_id)
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    matching_key = key_data
                    break

        if not matching_key:
            logger.error("JWKS key not found even after cache refresh")
            return None

        # Construct the public key
        public_key = jwk.construct(matching_key)

        # Verify and decode
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
        )

        # Ensure it's an id_token (not access_token)
        token_use = payload.get("token_use")
        if token_use not in ("id", "access"):
            logger.warning(f"Unexpected token_use: {token_use}")
            return None

        return payload

    except JWTError as e:
        logger.error(f"Cognito JWT verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying Cognito token: {e}")
        return None

"""
Auth Module
===========
Google OAuth integration + JWT token issuance.

JWT logic is delegated to core/security.py.
Route protection dependency is delegated to core/deps.py.

This module re-exports `get_current_user` for backward compatibility —
all existing `from .auth import get_current_user` imports work unchanged.
"""

import os
import sqlite3
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests

from .user_models import User
from .database import DB_PATH

# ─── Delegate to core modules ───────────────────────────────────────
from .core.security import create_access_token, decode_access_token
from .core.deps import get_current_user, get_current_user_id  # re-export

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Config ──────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID")


# ─── Schemas ─────────────────────────────────────────────────────────
class GoogleAuthRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ─── Database Integration ────────────────────────────────────────────
class AuthService:
    """Handles user creation/lookup in SQLite during OAuth flow."""

    def get_or_create_google_user(
        self, google_id: str, email: str, name: str, picture: str
    ) -> User:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Ensure extended columns exist (migration-safe)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN google_id TEXT UNIQUE")
            cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
        except sqlite3.OperationalError:
            pass  # Columns already exist

        cursor.execute(
            "SELECT user_id, email, created_at, google_id, name, profile_pic "
            "FROM users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()

        if row:
            user_id = row[0]
            if not row[3]:  # First Google login for existing email
                cursor.execute(
                    "UPDATE users SET google_id = ?, name = ?, profile_pic = ? WHERE user_id = ?",
                    (google_id, name, picture, user_id),
                )
                conn.commit()

            cursor.execute(
                "SELECT user_id, email, created_at, google_id, name, profile_pic "
                "FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
        else:
            user_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO users (user_id, email, google_id, name, profile_pic) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, email, google_id, name, picture),
            )
            conn.commit()

            cursor.execute(
                "SELECT user_id, email, created_at, google_id, name, profile_pic "
                "FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()

        conn.close()
        return User(
            user_id=row[0],
            email=row[1],
            created_at=row[2],
            google_id=row[3],
            name=row[4],
            profile_pic=row[5],
        )


# ─── Auth Route ──────────────────────────────────────────────────────
@router.post("/auth/google", response_model=TokenResponse)
def google_auth(request: GoogleAuthRequest):
    """
    Exchange a Google ID Token for an application JWT.

    Flow:
        1. Verify Google token via public keys
        2. Create/fetch user in DB
        3. Issue app JWT with user_id + profile info
    """
    if not GOOGLE_CLIENT_ID or GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID":
        logger.warning("Google Client ID not configured.")

    try:
        idinfo = id_token.verify_oauth2_token(
            request.token, requests.Request(), GOOGLE_CLIENT_ID
        )

        if idinfo["iss"] not in [
            "accounts.google.com",
            "https://accounts.google.com",
        ]:
            raise ValueError("Invalid token issuer.")

        google_id = idinfo["sub"]
        email = idinfo.get("email", "")
        name = idinfo.get("name", "")
        picture = idinfo.get("picture", "")

        auth_service = AuthService()
        user = auth_service.get_or_create_google_user(
            google_id, email, name, picture
        )

        # Create JWT using core/security.py
        access_token = create_access_token(
            user_id=user.user_id,
            extra_claims={
                "email": user.email,
                "name": user.name,
                "profile_pic": user.profile_pic,
            },
        )

        return TokenResponse(access_token=access_token, token_type="bearer")

    except ValueError as e:
        logger.error(f"Google Token Validation Failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    except Exception as e:
        logger.error(f"Login pipeline error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

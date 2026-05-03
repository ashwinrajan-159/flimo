"""
Auth Module
===========
AWS Cognito integration + internal JWT issuance.

Supports two flows:
  1. Cognito Hosted UI: redirect -> code exchange -> app JWT
  2. Dev login: email-only (for local development without Cognito)

JWT logic is delegated to core/security.py.
Route protection dependency is delegated to core/deps.py.

This module re-exports `get_current_user` for backward compatibility.
"""

import os
import sqlite3
import uuid
import logging
import base64
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .user_models import User
from .database import DB_PATH
from .config import (
    COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET,
    COGNITO_DOMAIN, COGNITO_REDIRECT_URI, COGNITO_REGION,
    is_cognito_configured,
)

# Delegate to core modules
from .core.security import create_access_token, decode_access_token, verify_cognito_token
from .core.deps import get_current_user, get_current_user_id  # re-export

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---
class DevLoginRequest(BaseModel):
    """Dev-mode email login (no real auth, for local testing only)."""
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: Optional[dict] = None


class CognitoCallbackRequest(BaseModel):
    code: str


# --- User Sync Service ---

class AuthService:
    """Handles user creation/lookup in SQLite for both Cognito and dev login."""

    def get_or_create_user(
        self, cognito_sub: Optional[str], email: str, name: str = "", picture: str = ""
    ) -> User:
        """
        User sync logic:
          - If cognito_sub exists in DB -> return existing user
          - If email exists in DB -> link cognito_sub and return
          - Otherwise -> create new user
        """
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Ensure extended columns exist (safe migration)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN cognito_sub TEXT",
            "ALTER TABLE users ADD COLUMN name TEXT",
            "ALTER TABLE users ADD COLUMN profile_pic TEXT",
        ]:
            try:
                cursor.execute(col_sql)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Try unique index on cognito_sub (idempotent)
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_cognito_sub ON users(cognito_sub)")
        except sqlite3.OperationalError:
            pass

        user_row = None

        # 1. Lookup by cognito_sub first (if provided)
        if cognito_sub:
            cursor.execute(
                "SELECT user_id, email, created_at, cognito_sub, name, profile_pic "
                "FROM users WHERE cognito_sub = ?",
                (cognito_sub,),
            )
            user_row = cursor.fetchone()

        # 2. Fallback to email lookup
        if not user_row:
            cursor.execute(
                "SELECT user_id, email, created_at, cognito_sub, name, profile_pic "
                "FROM users WHERE email = ?",
                (email,),
            )
            user_row = cursor.fetchone()

            if user_row and cognito_sub and not user_row[3]:
                # Link cognito_sub to existing email user
                cursor.execute(
                    "UPDATE users SET cognito_sub = ?, name = COALESCE(?, name), "
                    "profile_pic = COALESCE(?, profile_pic) WHERE user_id = ?",
                    (cognito_sub, name or None, picture or None, user_row[0]),
                )
                conn.commit()
                # Re-fetch
                cursor.execute(
                    "SELECT user_id, email, created_at, cognito_sub, name, profile_pic "
                    "FROM users WHERE user_id = ?",
                    (user_row[0],),
                )
                user_row = cursor.fetchone()

        # 3. Create new user
        if not user_row:
            user_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO users (user_id, email, cognito_sub, name, profile_pic) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, email, cognito_sub, name, picture),
            )
            conn.commit()
            cursor.execute(
                "SELECT user_id, email, created_at, cognito_sub, name, profile_pic "
                "FROM users WHERE user_id = ?",
                (user_id,),
            )
            user_row = cursor.fetchone()

        conn.close()

        return User(
            user_id=user_row[0],
            email=user_row[1],
            created_at=user_row[2],
            cognito_sub=user_row[3],
            name=user_row[4],
            profile_pic=user_row[5],
        )


# --- Cognito Hosted UI Routes ---

@router.get("/auth/login")
def cognito_login_redirect():
    """
    Redirect user to Cognito Hosted UI for login.
    Frontend calls this, user gets redirected to Cognito login page.
    """
    if not is_cognito_configured():
        raise HTTPException(status_code=501, detail="Cognito not configured. Use /auth/dev for local development.")

    auth_url = (
        f"{COGNITO_DOMAIN}/login?"
        f"client_id={COGNITO_CLIENT_ID}&"
        f"response_type=code&"
        f"scope=openid+email+profile&"
        f"redirect_uri={COGNITO_REDIRECT_URI}"
    )
    return RedirectResponse(url=auth_url)


@router.get("/auth/callback")
async def cognito_callback(code: str):
    """
    Cognito redirects here with ?code=xxx after successful login.
    Exchange code for tokens, verify, create/sync user, issue app JWT.
    Returns HTML that posts the token to the parent window.
    """
    import requests as http_requests

    if not is_cognito_configured():
        raise HTTPException(status_code=501, detail="Cognito not configured")

    # Exchange authorization code for tokens
    token_url = f"{COGNITO_DOMAIN}/oauth2/token"

    # Build Basic auth header for client credentials
    auth_string = f"{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}"
    auth_header = base64.b64encode(auth_string.encode()).decode()

    token_response = http_requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": COGNITO_REDIRECT_URI,
            "client_id": COGNITO_CLIENT_ID,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}",
        },
        timeout=10,
    )

    if token_response.status_code != 200:
        logger.error(f"Cognito token exchange failed: {token_response.text}")
        raise HTTPException(status_code=401, detail="Token exchange failed")

    tokens = token_response.json()
    id_token = tokens.get("id_token")

    if not id_token:
        raise HTTPException(status_code=401, detail="No id_token in Cognito response")

    # Verify the id_token using JWKS
    payload = verify_cognito_token(
        id_token, COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
    )

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid Cognito token")

    # Extract user info
    cognito_sub = payload.get("sub")
    email = payload.get("email", "")
    name = payload.get("name", payload.get("cognito:username", ""))
    picture = payload.get("picture", "")

    if not email:
        raise HTTPException(status_code=400, detail="Email not available in Cognito token")

    # Sync user to local DB
    auth_service = AuthService()
    user = auth_service.get_or_create_user(cognito_sub, email, name, picture)

    # Issue app JWT
    access_token = create_access_token(
        user_id=user.user_id,
        extra_claims={
            "email": user.email,
            "name": user.name or "",
            "profile_pic": user.profile_pic or "",
        },
    )

    logger.info(f"Cognito login successful for {email} (sub={cognito_sub})")

    # Return HTML page that stores the token and redirects to app
    return _build_callback_html(access_token, user)


@router.get("/auth/config")
def get_auth_config():
    """
    Return auth configuration for the frontend.
    Frontend uses this to decide whether to show Cognito or dev login.
    """
    cognito_ready = is_cognito_configured()
    return {
        "cognito_configured": cognito_ready,
        "login_url": f"{COGNITO_DOMAIN}/login?client_id={COGNITO_CLIENT_ID}&response_type=code&scope=openid+email+profile&redirect_uri={COGNITO_REDIRECT_URI}" if cognito_ready else None,
        "dev_login_available": True,
    }


# --- Dev Login (for local development without Cognito) ---

@router.post("/auth/dev", response_model=TokenResponse)
def dev_login(request: DevLoginRequest):
    """
    Development-only email login. No real authentication.
    Creates/fetches user by email and issues an app JWT.
    """
    email = request.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")

    auth_service = AuthService()
    user = auth_service.get_or_create_user(
        cognito_sub=None, email=email, name=email.split("@")[0]
    )

    access_token = create_access_token(
        user_id=user.user_id,
        extra_claims={
            "email": user.email,
            "name": user.name or email.split("@")[0],
        },
    )

    logger.info(f"Dev login for {email}")
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
        },
    )


# --- Helper ---

def _build_callback_html(token: str, user: User) -> str:
    """Build a small HTML page that stores auth data and redirects to app."""
    from fastapi.responses import HTMLResponse

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Logging in...</title></head>
    <body>
        <p>Logging you in...</p>
        <script>
            localStorage.setItem('flimo_jwt_token', '{token}');
            localStorage.setItem('flimo_user_email', '{user.email}');
            localStorage.setItem('flimo_user_name', '{user.name or user.email.split("@")[0]}');
            localStorage.setItem('flimo_user_id', '{user.user_id}');
            window.location.href = '/';
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

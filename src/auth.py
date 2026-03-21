import sqlite3
import uuid
from typing import Optional
from fastapi import Header, HTTPException, Depends
from .user_models import User
from .database import DB_PATH

class AuthService:
    """
    Mock Auth Service.
    Authenticates user via 'x-user-email' header.
    If user doesn't exist, auto-creates them (for demo purposes).
    """

    def get_or_create_user(self, email: str) -> User:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT user_id, email, created_at FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if row:
            user = User(user_id=row[0], email=row[1], created_at=row[2])
        else:
            # Create new user
            user_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO users (user_id, email) VALUES (?, ?)", (user_id, email))
            conn.commit()
            
            # Fetch back to get timestamp
            cursor.execute("SELECT user_id, email, created_at FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            user = User(user_id=row[0], email=row[1], created_at=row[2])
            
        conn.close()
        return user

# Dependency for FastAPI
def get_current_user(x_user_email: Optional[str] = Header(None)) -> User:
    if not x_user_email:
        # For development ease, maybe allow a default or error?
        # Let's verify strictness. 
        # "Authentication can be basic (email-only or mock users)."
        # Better to error if not provided so we know who is acting.
        raise HTTPException(status_code=401, detail="Header 'x-user-email' required for auth")
        
    auth_service = AuthService()
    try:
        return auth_service.get_or_create_user(x_user_email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from typing import List, Dict, Any
from pydantic import BaseModel

from .auth import get_current_user
from .user_models import User
from .database import DB_PATH

router = APIRouter(prefix="/api", tags=["user-interactions"])

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Ensure our specific interview tables exist so we don't break on missing columns
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            movie_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, movie_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            movie_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            movie_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # NOTE: The project already has a "likes" table with "content_id". We'll use a new one "user_likes" to strictly match the requested interview schema without breaking existing project code.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            movie_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, movie_id)
        )
    """)
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_likes_user ON user_likes(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_likes_movie ON user_likes(movie_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user ON user_bookmarks(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_comments_movie ON user_comments(movie_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_time ON user_activity_history(user_id, created_at DESC)")
    conn.commit()

    try:
        yield conn
    finally:
        conn.close()


# --- LIKES ---
@router.post("/like/{movie_id}")
def like_movie(movie_id: str, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    try:
        db.execute("INSERT INTO user_likes (user_id, movie_id) VALUES (?, ?)", (user.user_id, movie_id))
        db.execute("INSERT INTO user_activity_history (user_id, movie_id, action_type) VALUES (?, ?, 'like')", (user.user_id, movie_id))
        db.commit()
        return {"status": "success", "message": "Movie liked"}
    except sqlite3.IntegrityError:
        return {"status": "ignored", "message": "Already liked"}

@router.delete("/like/{movie_id}")
def unlike_movie(movie_id: str, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.execute("DELETE FROM user_likes WHERE user_id = ? AND movie_id = ?", (user.user_id, movie_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Like not found")
    return {"status": "success", "message": "Like removed"}

@router.get("/user/likes")
def get_user_likes(user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT movie_id, created_at FROM user_likes WHERE user_id = ? ORDER BY created_at DESC", (user.user_id,)).fetchall()
    return {"likes": [dict(r) for r in rows]}


# --- BOOKMARKS ---
@router.post("/bookmark/{movie_id}")
def bookmark_movie(movie_id: str, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    try:
        db.execute("INSERT INTO user_bookmarks (user_id, movie_id) VALUES (?, ?)", (user.user_id, movie_id))
        db.execute("INSERT INTO user_activity_history (user_id, movie_id, action_type) VALUES (?, ?, 'bookmark')", (user.user_id, movie_id))
        db.commit()
        return {"status": "success", "message": "Movie bookmarked"}
    except sqlite3.IntegrityError:
        return {"status": "ignored", "message": "Already bookmarked"}

@router.delete("/bookmark/{movie_id}")
def remove_bookmark(movie_id: str, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.execute("DELETE FROM user_bookmarks WHERE user_id = ? AND movie_id = ?", (user.user_id, movie_id))
    db.commit()
    return {"status": "success", "message": "Bookmark removed"}

@router.get("/user/bookmarks")
def get_user_bookmarks(user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT movie_id, created_at FROM user_bookmarks WHERE user_id = ? ORDER BY created_at DESC", (user.user_id,)).fetchall()
    return {"bookmarks": [dict(r) for r in rows]}


# --- COMMENTS ---
class CommentPayload(BaseModel):
    content: str

@router.post("/comment/{movie_id}")
def post_comment(movie_id: str, payload: CommentPayload, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    db.execute("INSERT INTO user_comments (user_id, movie_id, content) VALUES (?, ?, ?)", (user.user_id, movie_id, payload.content))
    db.execute("INSERT INTO user_activity_history (user_id, movie_id, action_type) VALUES (?, ?, 'comment')", (user.user_id, movie_id))
    db.commit()
    return {"status": "success", "message": "Comment posted"}

@router.get("/comments/{movie_id}")
def get_movie_comments(movie_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT user_id, content, created_at FROM user_comments WHERE movie_id = ? ORDER BY created_at DESC", (movie_id,)).fetchall()
    return {"comments": [dict(r) for r in rows]}


# --- TRACKING ---
class TrackPayload(BaseModel):
    action_type: str

@router.post("/track/{movie_id}")
def track_activity(movie_id: str, payload: TrackPayload, user: User = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    db.execute("INSERT INTO user_activity_history (user_id, movie_id, action_type) VALUES (?, ?, ?)", (user.user_id, movie_id, payload.action_type))
    db.commit()
    return {"status": "success"}

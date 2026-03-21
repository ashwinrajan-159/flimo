import sqlite3
import uuid
import logging
from typing import List, Optional, Tuple
from .database import DB_PATH
from .user_models import ReviewResponse, WatchlistResponse

logger = logging.getLogger(__name__)

class CommunityService:
    
    # --- Likes ---
    def add_like(self, user_id: str, content_id: str):
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO likes (user_id, content_id) VALUES (?, ?)",
                (user_id, content_id)
            )
            conn.commit()
            logger.info(f"User {user_id} liked {content_id}")
        except sqlite3.IntegrityError:
            logger.info(f"User {user_id} already liked {content_id}")
        finally:
            conn.close()

    def remove_like(self, user_id: str, content_id: str):
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM likes WHERE user_id = ? AND content_id = ?",
            (user_id, content_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} unliked {content_id}")

    # --- Reviews ---
    def add_review(self, user_id: str, content_id: str, rating: int, review_text: str) -> ReviewResponse:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        review_id = str(uuid.uuid4())
        
        try:
            cursor.execute(
                """
                INSERT INTO reviews (review_id, user_id, content_id, rating, review_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (review_id, user_id, content_id, rating, review_text)
            )
            conn.commit()
            
            # Fetch back
            cursor.execute("SELECT created_at FROM reviews WHERE review_id = ?", (review_id,))
            created_at = cursor.fetchone()[0]
            
            return ReviewResponse(
                review_id=review_id,
                user_id=user_id,
                content_id=content_id,
                rating=rating,
                review_text=review_text,
                created_at=created_at
            )
        finally:
            conn.close()

    def get_reviews(self, content_id: str) -> List[ReviewResponse]:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT review_id, user_id, rating, review_text, created_at FROM reviews WHERE content_id = ? ORDER BY created_at DESC",
            (content_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append(ReviewResponse(
                review_id=row[0],
                user_id=row[1],
                content_id=content_id,
                rating=row[2],
                review_text=row[3],
                created_at=row[4]
            ))
        return results

    # --- Watchlists ---
    def create_watchlist(self, user_id: str, name: str) -> WatchlistResponse:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        watchlist_id = str(uuid.uuid4())
        
        cursor.execute(
            "INSERT INTO watchlists (watchlist_id, user_id, name) VALUES (?, ?, ?)",
            (watchlist_id, user_id, name)
        )
        conn.commit()
        
        cursor.execute("SELECT created_at FROM watchlists WHERE watchlist_id = ?", (watchlist_id,))
        created_at = cursor.fetchone()[0]
        conn.close()
        
        return WatchlistResponse(
            watchlist_id=watchlist_id,
            user_id=user_id,
            name=name,
            created_at=created_at
        )

    def add_to_watchlist(self, user_id: str, watchlist_id: str, content_id: str):
        # Verification: does watchlist belong to user?
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM watchlists WHERE watchlist_id = ?", (watchlist_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise ValueError("Watchlist not found")
        if row[0] != user_id:
            conn.close()
            raise PermissionError("Not authorized to modify this watchlist")

        try:
            cursor.execute(
                "INSERT INTO watchlist_items (watchlist_id, content_id) VALUES (?, ?)",
                (watchlist_id, content_id)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass # Already exists
        finally:
            conn.close()

    def get_watchlists(self, user_id: str) -> List[WatchlistResponse]:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT watchlist_id, name, created_at FROM watchlists WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            WatchlistResponse(
                watchlist_id=r[0],
                user_id=user_id,
                name=r[1],
                created_at=r[2]
            ) for r in rows
        ]

    # --- Profile Methods ---
    def get_profile(self, user_id: str, email: str):
        """Get or create user profile."""
        from .user_models import UserProfile
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Check if profile exists
        cursor.execute(
            "SELECT display_name, avatar_color, created_at FROM user_profiles WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if row:
            profile = UserProfile(
                user_id=user_id,
                email=email,
                display_name=row[0],
                avatar_color=row[1] or "#3B82F6",
                created_at=row[2]
            )
        else:
            # Create default profile
            cursor.execute(
                "INSERT INTO user_profiles (user_id, display_name) VALUES (?, ?)",
                (user_id, email.split('@')[0])
            )
            conn.commit()
            profile = UserProfile(
                user_id=user_id,
                email=email,
                display_name=email.split('@')[0],
                avatar_color="#3B82F6"
            )
        
        conn.close()
        return profile

    def update_profile(self, user_id: str, display_name: str = None, avatar_color: str = None):
        """Update user profile."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if avatar_color is not None:
            updates.append("avatar_color = ?")
            params.append(avatar_color)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            cursor.execute(
                f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?",
                params
            )
            conn.commit()
        
        conn.close()
        logger.info(f"Updated profile for user {user_id}")

    # --- Chat Methods ---
    def get_chat_messages(self, limit: int = 50):
        """Get recent global chat messages with user info."""
        from .user_models import ChatMessageResponse
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cm.message_id, cm.user_id, cm.message, cm.created_at,
                   COALESCE(up.display_name, u.email) as display_name,
                   COALESCE(up.avatar_color, '#3B82F6') as avatar_color
            FROM chat_messages cm
            LEFT JOIN users u ON cm.user_id = u.user_id
            LEFT JOIN user_profiles up ON cm.user_id = up.user_id
            ORDER BY cm.created_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Reverse to show oldest first
        return [
            ChatMessageResponse(
                message_id=r[0],
                user_id=r[1],
                message=r[2],
                created_at=r[3],
                display_name=r[4],
                avatar_color=r[5]
            ) for r in reversed(rows)
        ]

    def add_chat_message(self, user_id: str, message: str):
        """Add a new chat message."""
        from .user_models import ChatMessageResponse
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        message_id = str(uuid.uuid4())
        
        cursor.execute(
            "INSERT INTO chat_messages (message_id, user_id, message) VALUES (?, ?, ?)",
            (message_id, user_id, message)
        )
        conn.commit()
        
        # Get user info for response
        cursor.execute("""
            SELECT COALESCE(up.display_name, u.email) as display_name,
                   COALESCE(up.avatar_color, '#3B82F6') as avatar_color,
                   cm.created_at
            FROM chat_messages cm
            LEFT JOIN users u ON cm.user_id = u.user_id
            LEFT JOIN user_profiles up ON cm.user_id = up.user_id
            WHERE cm.message_id = ?
        """, (message_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        logger.info(f"User {user_id} sent chat message")
        return ChatMessageResponse(
            message_id=message_id,
            user_id=user_id,
            message=message,
            created_at=row[2],
            display_name=row[0],
            avatar_color=row[1]
        )

    # --- Comment Methods ---
    def get_comments(self, content_id: str, limit: int = 50):
        """Get comments for a specific content item."""
        from .user_models import CommentResponse
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cc.comment_id, cc.user_id, cc.comment_text, cc.created_at,
                   COALESCE(up.display_name, u.email) as display_name,
                   COALESCE(up.avatar_color, '#3B82F6') as avatar_color
            FROM content_comments cc
            LEFT JOIN users u ON cc.user_id = u.user_id
            LEFT JOIN user_profiles up ON cc.user_id = up.user_id
            WHERE cc.content_id = ?
            ORDER BY cc.created_at DESC
            LIMIT ?
        """, (content_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            CommentResponse(
                comment_id=r[0],
                user_id=r[1],
                content_id=content_id,
                comment_text=r[2],
                created_at=r[3],
                display_name=r[4],
                avatar_color=r[5]
            ) for r in rows
        ]

    def add_comment(self, user_id: str, content_id: str, comment_text: str):
        """Add a comment to a content item."""
        from .user_models import CommentResponse
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        comment_id = str(uuid.uuid4())
        
        cursor.execute(
            "INSERT INTO content_comments (comment_id, user_id, content_id, comment_text) VALUES (?, ?, ?, ?)",
            (comment_id, user_id, content_id, comment_text)
        )
        conn.commit()
        
        # Get user info for response
        cursor.execute("""
            SELECT COALESCE(up.display_name, u.email) as display_name,
                   COALESCE(up.avatar_color, '#3B82F6') as avatar_color,
                   cc.created_at
            FROM content_comments cc
            LEFT JOIN users u ON cc.user_id = u.user_id
            LEFT JOIN user_profiles up ON cc.user_id = up.user_id
            WHERE cc.comment_id = ?
        """, (comment_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        logger.info(f"User {user_id} commented on {content_id}")
        return CommentResponse(
            comment_id=comment_id,
            user_id=user_id,
            content_id=content_id,
            comment_text=comment_text,
            created_at=row[2],
            display_name=row[0],
            avatar_color=row[1]
        )

    # --- History Methods (Personalization) ---
    def add_history(self, user_id: str, content_id: str, progress: float = 0):
        """Add or update watch history."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Check if exists to update progress/timestamp
        cursor.execute(
            "SELECT history_id FROM watched_history WHERE user_id = ? AND content_id = ?",
            (user_id, content_id)
        )
        row = cursor.fetchone()
        
        if row:
            cursor.execute(
                "UPDATE watched_history SET watched_at = CURRENT_TIMESTAMP, progress = ? WHERE history_id = ?",
                (progress, row[0])
            )
        else:
            cursor.execute(
                "INSERT INTO watched_history (user_id, content_id, progress) VALUES (?, ?, ?)",
                (user_id, content_id, progress)
            )
        
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} watched {content_id}")

    def get_history(self, user_id: str, limit: int = 100) -> List[dict]:
        """Get user watch history."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("SELECT content_id, watched_at, progress FROM watched_history WHERE user_id = ? ORDER BY watched_at DESC LIMIT ?", (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {"content_id": r[0], "watched_at": r[1], "progress": r[2]}
            for r in rows
        ]

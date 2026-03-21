import logging
import numpy as np
import sqlite3
from typing import List, Optional
from .database import DB_PATH
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

class UserProfileBuilder:
    """
    Builds a user preference vector based on interaction history.
    """
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        
    def build_user_vector(self, user_id: str) -> Optional[np.ndarray]:
        """
        Aggregates vectors from Likes (0.5), Watchlist (0.3), and Reviews (0.2).
        Returns normalized vector or None if no history.
        """
        likes_vectors = self._get_vectors_from_table(user_id, "likes", "content_id")
        watchlist_vectors = self._get_watchlist_vectors(user_id)
        review_vectors = self._get_vectors_from_table(
            user_id, "reviews", "content_id", condition="rating >= 7"
        )
        
        if not likes_vectors and not watchlist_vectors and not review_vectors:
            return None
            
        # Weighted Aggregation
        # Normalize each group first? Or average then weigh?
        # Plan says: 0.5 * avg(liked) + 0.3 * avg(watchlist) + ...
        
        final_vector = np.zeros(self.vector_store.DIMENSION, dtype=np.float32)
        has_data = False
        
        if likes_vectors:
            avg_likes = np.mean(likes_vectors, axis=0)
            final_vector += 0.5 * avg_likes
            has_data = True
            
        if watchlist_vectors:
            avg_wl = np.mean(watchlist_vectors, axis=0)
            final_vector += 0.3 * avg_wl
            has_data = True
            
        if review_vectors:
            avg_rev = np.mean(review_vectors, axis=0)
            final_vector += 0.2 * avg_rev
            has_data = True
            
        if not has_data:
            return None
            
        # Normalize final vector (L2)
        norm = np.linalg.norm(final_vector)
        if norm > 0:
            final_vector = final_vector / norm
            
        return final_vector

    def _get_vectors_from_table(self, user_id: str, table: str, id_col: str, condition: str = None) -> List[np.ndarray]:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        query = f"SELECT {id_col} FROM {table} WHERE user_id = ?"
        if condition:
            query += f" AND {condition}"
            
        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        vectors = []
        for row in rows:
            content_id = row[0]
            vec = self.vector_store.get_vector(content_id)
            if vec is not None:
                vectors.append(vec)
        return vectors

    def _get_watchlist_vectors(self, user_id: str) -> List[np.ndarray]:
        # Watchlist items are linked via watchlists table
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        query = """
            SELECT wi.content_id 
            FROM watchlist_items wi
            JOIN watchlists w ON wi.watchlist_id = w.watchlist_id
            WHERE w.user_id = ?
        """
        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        vectors = []
        for row in rows:
            content_id = row[0]
            vec = self.vector_store.get_vector(content_id)
            if vec is not None:
                vectors.append(vec)
        return vectors

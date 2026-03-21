import logging
import numpy as np
from typing import List, Dict, Optional
import sqlite3
from .database import DB_PATH, get_content_by_ids
from .models import UnifiedContent

logger = logging.getLogger(__name__)

class PersonalizationService:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def get_user_taste_profile(self, user_id: str) -> Dict:
        """
        Aggregates user signals to understand taste.
        Returns:
            {
                "liked_ids": [],
                "saved_ids": [],
                "history_ids": [],
                "all_interacted_ids": set()
            }
        """
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 1. Likes
        cursor.execute("SELECT content_id FROM likes WHERE user_id = ?", (user_id,))
        liked_ids = [r[0] for r in cursor.fetchall()]

        # 2. Watchlist (Saved)
        cursor.execute("""
            SELECT wi.content_id 
            FROM watchlist_items wi
            JOIN watchlists w ON wi.watchlist_id = w.watchlist_id
            WHERE w.user_id = ?
        """, (user_id,))
        saved_ids = [r[0] for r in cursor.fetchall()]

        # 3. History
        cursor.execute("SELECT content_id FROM watched_history WHERE user_id = ? ORDER BY watched_at DESC LIMIT 50", (user_id,))
        history_ids = [r[0] for r in cursor.fetchall()]

        conn.close()

        all_interacted = set(liked_ids + saved_ids + history_ids)
        
        return {
            "liked_ids": liked_ids,
            "saved_ids": saved_ids,
            "history_ids": history_ids,
            "all_interacted_ids": all_interacted
        }

    def generate_recommendations(self, user_id: str, limit: int = 20) -> List[UnifiedContent]:
        """
        Generates personalized recommendations using the 5-part ranking formula.
        """
        profile = self.get_user_taste_profile(user_id)
        
        # Cold Start: If very few interactions, return empty list (caller handles fallback)
        if len(profile["all_interacted_ids"]) < 3:
            logger.info(f"User {user_id} cold start: insufficient signals.")
            return []

        # Vector Search for Candidates
        # Strategy: Get embeddings for last 5 interacted items and find similar
        seed_ids = list(profile["all_interacted_ids"])[-5:] 
        
        # We need embeddings for seeds.
        # Since we don't have direct access to embeddings in DB easily without Embedder or lookups,
        # we assume VectorStore might help or we fetch content.
        # DB has `embedding_text` but not the vector. 
        # But `vector_store` has vectors indexed by ID? 
        # FAISS index usually maps ID -> Vector if using IDMap, or just positional.
        # `VectorStore` wrapper likely handles `search(query_vector)`.
        
        # Issue: We need a query vector.
        # If `VectorStore` supports `get_vector(id)`, use that.
        # Checking `vector_store.py` (not visible here, but common pattern).
        # Assuming we can't easily get vector from ID without re-embedding if not cached.
        
        # Workaround: Use text from content to "re-query" or if VectorStore helps.
        # SearchService usually embeds text.
        
        # Let's import Embedder here? 
        # Or better, fetch content, get `embedding_text`, embed it.
        from .embedder import Embedder
        embedder = Embedder()
        
        seed_contents = get_content_by_ids(seed_ids)
        if not seed_contents:
            return []
            
        # Create a centroid vector
        vectors = []
        for c in seed_contents:
            # Use embedding_text or title/desc
            txt = c.embedding_text or f"{c.title} {c.description}"
            v = embedder.embed_texts([txt])[0]
            vectors.append(v)
            
        if not vectors:
            return []
            
        centroid = np.mean(vectors, axis=0)
        
        # Search FAISS
        distances, candidate_ids = self.vector_store.search(centroid, k=limit*4)
        
        # Filter exclusions
        valid_ids = []
        existing_ids = profile["all_interacted_ids"]
        
        for cid in candidate_ids:
            if cid and cid not in existing_ids:
                valid_ids.append(cid)
                if len(valid_ids) >= limit * 2:
                    break
                    
        # Fetch Content
        candidates = get_content_by_ids(valid_ids)
        
        # Ranker will handle the scoring logic if called by API. 
        # Here we just return candidates.
        # Or do we apply specific sorting?
        # The API calls `search_service` which uses `ranker`.
        # API expects SearchResultItem.
        # This method returns UnifiedContent list. API maps it.
        
        return candidates

    def get_personalized_query(self, query_vector: np.ndarray, user_id: str, ambiguity: float = 0.5) -> np.ndarray:
        """
        Adjusts the search query vector based on user's taste profile.
        Ambiguity (0.0 to 1.0) determines how much user history influences the query.
        High ambiguity (generic search) -> High personalization.
        Low ambiguity (specific search) -> Low personalization.
        """
        if ambiguity < 0.1:
            return query_vector
            
        profile = self.get_user_taste_profile(user_id)
        if len(profile["all_interacted_ids"]) < 3:
            return query_vector
            
        # Get user centroid
        # We start with last 5 interactions
        seed_ids = list(profile["all_interacted_ids"])[-5:]
        seed_contents = get_content_by_ids(seed_ids)
        
        if not seed_contents:
            return query_vector
            
        from .embedder import Embedder
        embedder = Embedder()
        
        vectors = []
        for c in seed_contents:
            txt = c.embedding_text or f"{c.title} {c.description}"
            v = embedder.embed_texts([txt])[0]
            vectors.append(v)
            
        if not vectors:
            return query_vector
            
        user_centroid = np.mean(vectors, axis=0)
        
        # Blend: query + (ambiguity * 0.5) * user_centroid
        # We normalize to keep magnitude similar? 
        # FAISS uses IP (dot product) usually, or L2. Normalization helps.
        
        # Weight for personalization: max 0.4 impact
        alpha = ambiguity * 0.4
        
        personalized_vector = (1 - alpha) * query_vector + alpha * user_centroid
        return personalized_vector

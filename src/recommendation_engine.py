"""
Recommendation Engine
=====================
Core module for Netflix-style personalized recommendations using:
  - User taste vectors (weighted interaction embeddings with time decay)
  - Hybrid ranking (semantic + rating + popularity + recency)
  - User-to-user collaborative filtering via cosine similarity

Performance:
  - In-memory user vector cache (TTL-based invalidation)
  - Batch vector retrieval from FAISS index
  - Lazy recomputation on interaction
"""

import logging
import time
import math
import numpy as np
import sqlite3
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime

from .database import DB_PATH, get_content_by_ids
from .vector_store import VectorStore
from .models import UnifiedContent

logger = logging.getLogger(__name__)

# ─── Interaction Weights ────────────────────────────────────────────
ACTION_WEIGHTS = {
    "like":     1.0,
    "bookmark": 0.7,
    "view":     0.3,
}

# ─── Time Decay ─────────────────────────────────────────────────────
DECAY_HALF_LIFE_DAYS = 30  # interactions lose half weight every 30 days

# ─── Hybrid Ranking Weights ─────────────────────────────────────────
W_SEMANTIC   = 0.50   # FAISS cosine similarity (normalized)
W_RATING     = 0.20   # movie rating (normalized to 0-1)
W_POPULARITY = 0.20   # popularity (normalized to 0-1)
W_RECENCY    = 0.10   # release year recency boost

# ─── Cache Config ────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 300  # 5 minutes

# ─── Limits ──────────────────────────────────────────────────────────
MAX_INTERACTIONS_FOR_VECTOR = 50
FAISS_CANDIDATE_K = 100
DEFAULT_TOP_K = 20


@dataclass
class CachedVector:
    vector: np.ndarray
    computed_at: float  # time.time()
    interaction_count: int


class RecommendationEngine:
    """
    Stateful recommendation engine. Initialized once at app startup
    and shared across requests via dependency injection.
    """

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self._user_vector_cache: Dict[str, CachedVector] = {}

    # ═══════════════════════════════════════════════════════════════════
    # 1. INTERACTION STORAGE
    # ═══════════════════════════════════════════════════════════════════

    def log_interaction(self, user_id: str, movie_id: str, action: str) -> dict:
        """
        Store an interaction (like/bookmark/view) with duplicate prevention.
        Returns status dict.
        """
        if action not in ACTION_WEIGHTS:
            return {"status": "error", "message": f"Invalid action: {action}. Must be one of {list(ACTION_WEIGHTS.keys())}"}

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO user_interactions (user_id, movie_id, action_type)
                VALUES (?, ?, ?)
            """, (user_id, movie_id, action))
            conn.commit()

            # Invalidate cache for this user (mark dirty)
            self._invalidate_user_cache(user_id)

            return {"status": "success", "message": f"Interaction '{action}' logged for movie {movie_id}"}
        except sqlite3.IntegrityError:
            return {"status": "ignored", "message": f"Duplicate {action} for movie {movie_id}"}
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()

    # ═══════════════════════════════════════════════════════════════════
    # 2. USER TASTE VECTOR COMPUTATION
    # ═══════════════════════════════════════════════════════════════════

    def compute_user_vector(self, user_id: str, force: bool = False) -> Optional[np.ndarray]:
        """
        Compute a user's taste vector as a weighted average of interacted movie embeddings.
        
        Formula:
            user_vector = Σ (w_action × decay(t) × movie_embedding) / Σ (w_action × decay(t))
        
        Where:
            w_action   = weight for like/bookmark/view
            decay(t)   = 0.5 ^ (days_since_interaction / half_life)
        
        Returns normalized 384-dim vector or None if insufficient data.
        """
        # Check cache first
        if not force:
            cached = self._get_cached_vector(user_id)
            if cached is not None:
                return cached

        # Fetch interactions
        interactions = self._fetch_interactions(user_id, limit=MAX_INTERACTIONS_FOR_VECTOR)
        if not interactions:
            logger.info(f"[REC] No interactions found for user {user_id}")
            return None

        now = datetime.utcnow()
        weighted_vectors = []
        total_weight = 0.0

        for movie_id, action_type, created_at_str in interactions:
            # Get movie embedding from FAISS (fast reconstruct)
            movie_vector = self.vector_store.get_vector(movie_id)
            if movie_vector is None:
                continue

            # Action weight
            action_w = ACTION_WEIGHTS.get(action_type, 0.3)

            # Time decay
            try:
                if isinstance(created_at_str, str):
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00").replace("+00:00", ""))
                else:
                    created_at = now
                days_old = max(0, (now - created_at).days)
            except Exception:
                days_old = 0

            decay = math.pow(0.5, days_old / DECAY_HALF_LIFE_DAYS)

            # Combined weight
            combined_w = action_w * decay
            weighted_vectors.append(combined_w * movie_vector)
            total_weight += combined_w

        if total_weight == 0 or not weighted_vectors:
            return None

        # Weighted average
        user_vector = np.sum(weighted_vectors, axis=0) / total_weight

        # L2 normalize (FAISS IndexFlatIP expects normalized vectors for cosine sim)
        norm = np.linalg.norm(user_vector)
        if norm > 0:
            user_vector = user_vector / norm
        else:
            return None

        # Cache it
        self._cache_user_vector(user_id, user_vector, len(interactions))

        logger.info(f"[REC] Computed user vector for {user_id}: {len(interactions)} interactions, norm={np.linalg.norm(user_vector):.4f}")
        return user_vector

    # ═══════════════════════════════════════════════════════════════════
    # 3. PERSONALIZED RECOMMENDATIONS (Hybrid Ranking)
    # ═══════════════════════════════════════════════════════════════════

    def get_recommendations(self, user_id: str, top_k: int = DEFAULT_TOP_K) -> List[dict]:
        """
        Full recommendation pipeline:
        1. Compute/retrieve user taste vector
        2. FAISS search for top candidates
        3. Remove already-interacted movies
        4. Apply hybrid ranking
        5. Return top K results
        """
        # Step 1: User vector
        user_vector = self.compute_user_vector(user_id)
        if user_vector is None:
            logger.info(f"[REC] Cold start for user {user_id} — no taste vector available")
            return []

        # Step 2: FAISS candidate retrieval
        distances, candidate_ids = self.vector_store.search(user_vector, k=FAISS_CANDIDATE_K)

        if not candidate_ids or all(cid is None for cid in candidate_ids):
            return []

        # Build distance map
        distance_map: Dict[str, float] = {}
        valid_candidate_ids = []
        for cid, dist in zip(candidate_ids, distances):
            if cid is not None:
                distance_map[cid] = float(dist)
                valid_candidate_ids.append(cid)

        if not valid_candidate_ids:
            return []

        # Step 3: Remove already interacted
        interacted_ids = self._get_interacted_movie_ids(user_id)
        filtered_ids = [cid for cid in valid_candidate_ids if cid not in interacted_ids]

        if not filtered_ids:
            logger.info(f"[REC] All candidates already interacted for user {user_id}")
            return []

        # Step 4: Fetch content details
        contents = get_content_by_ids(filtered_ids)
        content_map = {c.content_id: c for c in contents}

        # Step 5: Hybrid ranking
        ranked = self._hybrid_rank(filtered_ids, content_map, distance_map)

        # Step 6: Return top K
        return ranked[:top_k]

    def _hybrid_rank(
        self,
        candidate_ids: List[str],
        content_map: Dict[str, UnifiedContent],
        distance_map: Dict[str, float]
    ) -> List[dict]:
        """
        Hybrid Ranking Function:
        
        final_score = 0.5 × semantic_similarity (normalized)
                    + 0.2 × rating (normalized to 0-1)
                    + 0.2 × popularity (normalized to 0-1)
                    + 0.1 × recency (newer movies boosted)
        """
        current_year = datetime.now().year

        # Compute normalization ranges from candidates
        ratings = [content_map[cid].rating for cid in candidate_ids if cid in content_map and content_map[cid].rating]
        popularities = [content_map[cid].popularity for cid in candidate_ids if cid in content_map and content_map[cid].popularity]

        max_rating = max(ratings) if ratings else 10.0
        min_rating = min(ratings) if ratings else 0.0
        rating_range = max_rating - min_rating if max_rating != min_rating else 1.0

        max_pop = max(popularities) if popularities else 1.0
        min_pop = min(popularities) if popularities else 0.0
        pop_range = max_pop - min_pop if max_pop != min_pop else 1.0

        # Normalize FAISS distances (inner product scores are already similarity)
        sim_values = [distance_map.get(cid, 0.0) for cid in candidate_ids if cid in content_map]
        max_sim = max(sim_values) if sim_values else 1.0
        min_sim = min(sim_values) if sim_values else 0.0
        sim_range = max_sim - min_sim if max_sim != min_sim else 1.0

        scored_results = []

        for cid in candidate_ids:
            if cid not in content_map:
                continue

            content = content_map[cid]
            raw_sim = distance_map.get(cid, 0.0)

            # Normalize components
            norm_sim = (raw_sim - min_sim) / sim_range
            norm_rating = ((content.rating or 0) - min_rating) / rating_range
            norm_pop = ((content.popularity or 0) - min_pop) / pop_range

            # Recency score: movies within last 5 years get full boost, older decay linearly
            year = content.release_year or 2000
            years_old = max(0, current_year - year)
            recency_score = max(0.0, 1.0 - (years_old / 25.0))  # Linear decay over 25 years

            # Hybrid score
            final_score = (
                W_SEMANTIC   * norm_sim
              + W_RATING     * norm_rating
              + W_POPULARITY * norm_pop
              + W_RECENCY    * recency_score
            )

            # Build reason string
            reason_parts = []
            if norm_sim > 0.7:
                reason_parts.append("Matches your taste")
            if content.rating and content.rating >= 8.0:
                reason_parts.append(f"Highly rated ({content.rating:.1f})")
            if norm_pop > 0.7:
                reason_parts.append("Popular")
            if recency_score > 0.7:
                reason_parts.append("Recent release")

            scored_results.append({
                "content_id": cid,
                "title": content.title,
                "content_type": content.content_type.value if hasattr(content.content_type, 'value') else str(content.content_type),
                "thumbnail_url": content.thumbnail_url,
                "rating": content.rating,
                "popularity": content.popularity,
                "release_year": content.release_year,
                "score": round(final_score, 4),
                "reason": " • ".join(reason_parts) if reason_parts else "Recommended for you",
                "genres": content.genres,
            })

        # Sort descending by score
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results

    # ═══════════════════════════════════════════════════════════════════
    # 4. USER-TO-USER SIMILARITY (Collaborative Filtering)
    # ═══════════════════════════════════════════════════════════════════

    def find_similar_users(self, user_id: str, top_n: int = 10) -> List[dict]:
        """
        Find users with similar taste profiles using cosine similarity
        on their taste vectors.
        """
        user_vector = self.compute_user_vector(user_id)
        if user_vector is None:
            return []

        # Get all other user IDs that have interactions
        other_user_ids = self._get_all_user_ids_with_interactions(exclude=user_id)
        if not other_user_ids:
            return []

        similarities = []
        for other_id in other_user_ids:
            other_vector = self.compute_user_vector(other_id)
            if other_vector is None:
                continue

            # Cosine similarity (both vectors are L2-normalized, so dot product = cosine)
            cos_sim = float(np.dot(user_vector, other_vector))
            similarities.append({
                "user_id": other_id,
                "similarity": round(cos_sim, 4)
            })

        # Sort by similarity descending
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:top_n]

    def get_collaborative_recommendations(self, user_id: str, top_k: int = DEFAULT_TOP_K) -> List[dict]:
        """
        Recommend movies liked by similar users but not seen by the current user.
        
        Algorithm:
        1. Find top 5 similar users
        2. Collect their liked/bookmarked movies
        3. Remove movies the current user has already interacted with
        4. Rank by: how many similar users liked it × their similarity score
        """
        similar_users = self.find_similar_users(user_id, top_n=5)
        if not similar_users:
            return []

        # Current user's interacted movies
        my_interacted = self._get_interacted_movie_ids(user_id)

        # Collect weighted movie scores from similar users
        movie_scores: Dict[str, float] = {}
        movie_sources: Dict[str, List[str]] = {}

        for su in similar_users:
            su_id = su["user_id"]
            su_sim = su["similarity"]

            # Get their high-signal interactions (likes + bookmarks)
            su_interactions = self._fetch_interactions(su_id, limit=50)
            for movie_id, action_type, _ in su_interactions:
                if movie_id in my_interacted:
                    continue
                if action_type not in ("like", "bookmark"):
                    continue

                weight = ACTION_WEIGHTS.get(action_type, 0.3) * su_sim
                movie_scores[movie_id] = movie_scores.get(movie_id, 0.0) + weight
                if movie_id not in movie_sources:
                    movie_sources[movie_id] = []
                movie_sources[movie_id].append(su_id)

        if not movie_scores:
            return []

        # Sort by weighted score
        sorted_movies = sorted(movie_scores.items(), key=lambda x: x[1], reverse=True)
        top_movie_ids = [mid for mid, _ in sorted_movies[:top_k * 2]]

        # Fetch content details
        contents = get_content_by_ids(top_movie_ids)
        content_map = {c.content_id: c for c in contents}

        results = []
        for mid, score in sorted_movies:
            if mid not in content_map:
                continue

            content = content_map[mid]
            n_sources = len(movie_sources.get(mid, []))

            results.append({
                "content_id": mid,
                "title": content.title,
                "content_type": content.content_type.value if hasattr(content.content_type, 'value') else str(content.content_type),
                "thumbnail_url": content.thumbnail_url,
                "rating": content.rating,
                "popularity": content.popularity,
                "release_year": content.release_year,
                "score": round(score, 4),
                "reason": f"Liked by {n_sources} similar user{'s' if n_sources > 1 else ''}",
                "genres": content.genres,
            })

            if len(results) >= top_k:
                break

        return results

    # ═══════════════════════════════════════════════════════════════════
    # 5. DEBUG / INTROSPECTION
    # ═══════════════════════════════════════════════════════════════════

    def get_user_vector_debug(self, user_id: str) -> dict:
        """
        Debug endpoint data: returns user vector stats and interaction summary.
        """
        interactions = self._fetch_interactions(user_id, limit=MAX_INTERACTIONS_FOR_VECTOR)

        # Action breakdown
        action_counts = {}
        for _, action_type, _ in interactions:
            action_counts[action_type] = action_counts.get(action_type, 0) + 1

        user_vector = self.compute_user_vector(user_id)

        cached = self._user_vector_cache.get(user_id)
        cache_info = None
        if cached:
            cache_info = {
                "cached": True,
                "computed_at": datetime.fromtimestamp(cached.computed_at).isoformat(),
                "interaction_count_at_compute": cached.interaction_count,
                "age_seconds": round(time.time() - cached.computed_at, 1),
            }

        return {
            "user_id": user_id,
            "total_interactions": len(interactions),
            "action_breakdown": action_counts,
            "vector_computed": user_vector is not None,
            "vector_norm": round(float(np.linalg.norm(user_vector)), 4) if user_vector is not None else None,
            "vector_dimension": int(user_vector.shape[0]) if user_vector is not None else None,
            "vector_sample": user_vector[:5].tolist() if user_vector is not None else None,
            "cache": cache_info,
        }

    # ═══════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _fetch_interactions(self, user_id: str, limit: int = 50) -> List[Tuple[str, str, str]]:
        """Fetch recent interactions: [(movie_id, action_type, created_at), ...]"""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT movie_id, action_type, created_at
            FROM user_interactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _get_interacted_movie_ids(self, user_id: str) -> Set[str]:
        """Get set of all movie IDs the user has interacted with."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT movie_id FROM user_interactions WHERE user_id = ?
        """, (user_id,))
        ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return ids

    def _get_all_user_ids_with_interactions(self, exclude: str = None) -> List[str]:
        """Get all user IDs that have at least 3 interactions (minimum for meaningful vector)."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, COUNT(*) as cnt
            FROM user_interactions
            GROUP BY user_id
            HAVING cnt >= 3
        """)
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows if row[0] != exclude]

    # ─── Cache Management ───────────────────────────────────────────

    def _get_cached_vector(self, user_id: str) -> Optional[np.ndarray]:
        """Return cached vector if still valid (within TTL)."""
        cached = self._user_vector_cache.get(user_id)
        if cached is None:
            return None
        if time.time() - cached.computed_at > CACHE_TTL_SECONDS:
            del self._user_vector_cache[user_id]
            return None
        return cached.vector

    def _cache_user_vector(self, user_id: str, vector: np.ndarray, interaction_count: int):
        """Store computed vector in cache."""
        self._user_vector_cache[user_id] = CachedVector(
            vector=vector,
            computed_at=time.time(),
            interaction_count=interaction_count
        )

    def _invalidate_user_cache(self, user_id: str):
        """Remove cached vector for user (forces recomputation on next request)."""
        self._user_vector_cache.pop(user_id, None)

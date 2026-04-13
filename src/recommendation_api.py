"""
Recommendation API
==================
FastAPI router providing personalized recommendation endpoints:
  - POST /interact        — Log user interactions (like/bookmark/view)
  - GET  /recommendations — Personalized movie recommendations
  - GET  /user/vector     — Debug: inspect user taste vector
  - GET  /user/similar    — Find similar users (collaborative filtering)
  - GET  /recommendations/collaborative — Recommendations from similar users
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import get_current_user
from .user_models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Recommendations"])

# ─── Request / Response Schemas ──────────────────────────────────────

class InteractionRequest(BaseModel):
    """POST /interact body"""
    movie_id: str = Field(..., description="Content ID of the movie (e.g. 'movie:12345')")
    action: str = Field(..., description="Interaction type: 'like', 'bookmark', or 'view'")

class InteractionResponse(BaseModel):
    status: str
    message: str

class RecommendationItem(BaseModel):
    content_id: str
    title: str
    content_type: str
    thumbnail_url: Optional[str] = None
    rating: Optional[float] = None
    popularity: Optional[float] = None
    release_year: Optional[int] = None
    score: float
    reason: str
    genres: Optional[List[str]] = None

class RecommendationResponse(BaseModel):
    results: List[RecommendationItem]
    total: int
    source: str  # "content-based" | "collaborative" | "hybrid"

class UserVectorResponse(BaseModel):
    user_id: str
    total_interactions: int
    action_breakdown: dict
    vector_computed: bool
    vector_norm: Optional[float] = None
    vector_dimension: Optional[int] = None
    vector_sample: Optional[List[float]] = None
    cache: Optional[dict] = None

class SimilarUserItem(BaseModel):
    user_id: str
    similarity: float

class SimilarUsersResponse(BaseModel):
    similar_users: List[SimilarUserItem]
    total: int


# ─── Singleton Engine (initialized at startup via api.py) ────────────

_engine_instance = None

def get_engine():
    """Dependency: returns the shared RecommendationEngine singleton."""
    if _engine_instance is None:
        raise HTTPException(status_code=503, detail="Recommendation engine not initialized")
    return _engine_instance

def initialize_engine(vector_store):
    """Called once at app startup from api.py"""
    global _engine_instance
    from .recommendation_engine import RecommendationEngine
    _engine_instance = RecommendationEngine(vector_store)
    logger.info("[REC-API] Recommendation engine initialized")
    return _engine_instance


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/interact", response_model=InteractionResponse)
def log_interaction(
    request: InteractionRequest,
    user: User = Depends(get_current_user)
):
    """
    Log a user interaction (like/bookmark/view).
    
    - Stores interaction with duplicate prevention (unique user_id + movie_id + action_type)
    - Invalidates cached user taste vector to trigger recomputation
    
    Example:
        POST /interact
        Headers: Authorization: Bearer <jwt>
        Body: {"movie_id": "movie:12345", "action": "like"}
        
        Response: {"status": "success", "message": "Interaction 'like' logged for movie movie:12345"}
    """
    engine = get_engine()
    result = engine.log_interaction(user.user_id, request.movie_id, request.action)
    return InteractionResponse(**result)


@router.get("/recommendations", response_model=RecommendationResponse)
def get_recommendations(
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100, description="Number of recommendations"),
    mode: str = Query(default="hybrid", description="'content' for content-based, 'collaborative' for user-similarity, 'hybrid' for both merged")
):
    """
    Get personalized movie recommendations.
    
    Uses the user's interaction history to build a taste vector,
    then retrieves and ranks candidates using hybrid scoring:
    
        final_score = 0.5 × semantic_similarity
                    + 0.2 × rating (normalized)
                    + 0.2 × popularity (normalized)
                    + 0.1 × recency (newer movies boosted)
    
    Modes:
    - content: Pure content-based (user vector → FAISS → hybrid rank)
    - collaborative: Movies liked by similar users
    - hybrid: Merged results from both, de-duplicated
    
    Example:
        GET /recommendations?limit=20&mode=hybrid
        Headers: Authorization: Bearer <jwt>
    """
    engine = get_engine()

    if mode == "content":
        results = engine.get_recommendations(user.user_id, top_k=limit)
        source = "content-based"
    elif mode == "collaborative":
        results = engine.get_collaborative_recommendations(user.user_id, top_k=limit)
        source = "collaborative"
    else:
        # Hybrid: merge content-based + collaborative
        content_results = engine.get_recommendations(user.user_id, top_k=limit)
        collab_results = engine.get_collaborative_recommendations(user.user_id, top_k=limit)

        # Merge with de-duplication (content-based results take priority)
        seen_ids = set()
        merged = []
        for r in content_results:
            if r["content_id"] not in seen_ids:
                merged.append(r)
                seen_ids.add(r["content_id"])
        for r in collab_results:
            if r["content_id"] not in seen_ids:
                merged.append(r)
                seen_ids.add(r["content_id"])

        # Re-sort by score
        merged.sort(key=lambda x: x["score"], reverse=True)
        results = merged[:limit]
        source = "hybrid"

    return RecommendationResponse(
        results=[RecommendationItem(**r) for r in results],
        total=len(results),
        source=source
    )


@router.get("/user/vector", response_model=UserVectorResponse)
def get_user_vector(user: User = Depends(get_current_user)):
    """
    Debug endpoint: inspect the user's computed taste vector.
    
    Returns:
    - Interaction counts by action type
    - Whether a vector was computed
    - Vector norm, dimension, and first 5 components
    - Cache info (age, TTL status)
    
    Example:
        GET /user/vector
        Headers: Authorization: Bearer <jwt>
    """
    engine = get_engine()
    debug_data = engine.get_user_vector_debug(user.user_id)
    return UserVectorResponse(**debug_data)


@router.get("/user/similar", response_model=SimilarUsersResponse)
def get_similar_users(
    user: User = Depends(get_current_user),
    limit: int = Query(default=10, ge=1, le=50, description="Number of similar users to return")
):
    """
    Find users with similar taste profiles (cosine similarity on taste vectors).
    
    Example:
        GET /user/similar?limit=5
        Headers: Authorization: Bearer <jwt>
    """
    engine = get_engine()
    similar = engine.find_similar_users(user.user_id, top_n=limit)
    return SimilarUsersResponse(
        similar_users=[SimilarUserItem(**s) for s in similar],
        total=len(similar)
    )


@router.get("/recommendations/collaborative", response_model=RecommendationResponse)
def get_collaborative_recommendations(
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100, description="Number of recommendations")
):
    """
    Recommendations based on user-to-user similarity.
    
    Algorithm:
    1. Find top 5 users with similar taste vectors
    2. Collect their liked/bookmarked movies  
    3. Remove movies the current user has already seen
    4. Rank by: (similar_user_count × similarity_score × action_weight)
    
    Example:
        GET /recommendations/collaborative?limit=10
        Headers: Authorization: Bearer <jwt>
    """
    engine = get_engine()
    results = engine.get_collaborative_recommendations(user.user_id, top_k=limit)
    return RecommendationResponse(
        results=[RecommendationItem(**r) for r in results],
        total=len(results),
        source="collaborative"
    )

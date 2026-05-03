from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os

from .schemas import SearchRequest, SearchResponse, DiscoverRequest, SearchResultItem, PersonalRecommendationRequest
from .search_service import SearchService
from .browse_api import router as browse_router
from .community_api import router as community_router
from .auth import router as auth_router
from .config import TMDB_API_KEY
from .monitoring import MonitoringMiddleware, RateLimitMiddleware, METRICS
from .database import DB_PATH

# Configure Logging
import logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log") if os.path.exists("logs") else logging.NullHandler()
    ]
)
logger = logging.getLogger("API")

from fastapi.staticfiles import StaticFiles

# ... imports ...

app = FastAPI(title="Recommendation Platform API", version="1.0")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Middleware
app.add_middleware(MonitoringMiddleware)
app.add_middleware(RateLimitMiddleware, limit=60, window=60)

app.include_router(browse_router)
app.include_router(community_router)
app.include_router(auth_router)
from .user_api import router as user_router
app.include_router(user_router)
from .recommendation_api import router as recommendation_router
app.include_router(recommendation_router)

# Singleton instance
search_service_instance: Optional[SearchService] = None

def get_search_service():
    global search_service_instance
    if search_service_instance is None:
        try:
            search_service_instance = SearchService()
        except Exception as e:
            logger.error(f"Failed to initialize Search Service: {e}")
            raise HTTPException(status_code=500, detail="Search Service initialization failed")
    return search_service_instance

@app.on_event("startup")
async def startup_event():
    # Ensure logs directory exists if running locally without docker volume mapping
    if not os.path.exists("logs"):
        os.makedirs("logs", exist_ok=True)
        # Re-configure logging to add file handler if it wasn't there
        file_handler = logging.FileHandler("logs/app.log")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
        
    logger.info("Application startup: Initializing services...")
    
    # --- Create community tables if they don't exist ---
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            cognito_sub TEXT,
            name TEXT,
            profile_pic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            avatar_color TEXT DEFAULT '#3B82F6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS content_comments (
            comment_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            comment_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS likes (
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, content_id)
        );
        
        CREATE TABLE IF NOT EXISTS reviews (
            review_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS watchlist_items (
            watchlist_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (watchlist_id, content_id)
        );
        
        CREATE TABLE IF NOT EXISTS watch_history (
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            progress REAL DEFAULT 0,
            last_watched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, content_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_chat_messages_time ON chat_messages(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_content_comments_content ON content_comments(content_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    
    conn.commit()
    conn.close()
    logger.info("Community tables initialized.")
    
    search_svc = get_search_service()
    
    # Initialize Recommendation Engine (uses the same VectorStore)
    from .recommendation_api import initialize_engine
    initialize_engine(search_svc.vector_store)
    logger.info("Recommendation Engine initialized.")

from fastapi.responses import FileResponse
import time

_startup_time = time.time()

@app.get("/health")
async def health_check():
    """Health check for Docker, ALB, and monitoring."""
    uptime = int(time.time() - _startup_time)
    status = {
        "status": "healthy",
        "uptime_seconds": uptime,
        "search_engine": search_service_instance is not None,
        "database": os.path.exists(str(DB_PATH)),
    }
    return status

@app.get("/")
async def read_index():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

# Catch-all for SPA client-side routing (e.g., /search, /saved, /community, /profile)
# This must be defined BEFORE api routes to avoid conflicts
@app.get("/search")
@app.get("/saved") 
@app.get("/community")
@app.get("/profile")
@app.get("/trending")
@app.get("/latest")
async def spa_routes():
    """Serve index.html for SPA client-side routes."""
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.post("/search", response_model=SearchResponse)
def search_content(
    request: SearchRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Search with optional personalization.
    If a valid JWT is provided, personalizes results using user history.
    """
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        from .core.security import decode_access_token
        payload = decode_access_token(authorization.split(" ", 1)[1])
        if payload:
            user_id = payload.get("user_id")

    try:
        if not search_service_instance:
             raise HTTPException(status_code=500, detail="Service not initialized")

        results = search_service_instance.search(request, user_id=user_id)
        return SearchResponse(results=results)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/discover")
def discover_content_endpoint(request: DiscoverRequest):
    """
    Discover content by mode (trending/popular/latest) with mood and genre filters.
    Quality gate: rating >= 7.0
    """
    from .schemas import DiscoverRequest, SearchResultItem, SearchResponse
    from .database import discover_content
    
    try:
        contents = discover_content(
            mode=request.mode,
            mood=request.mood,
            genres=request.genres,
            query=request.query,
            quality_threshold=6.0,
            limit=30
        )
        
        # Convert to SearchResultItem format
        results = []
        for c in contents:
            reason_parts = []
            if request.mode == "trending":
                reason_parts.append("Trending now")
            elif request.mode == "latest":
                reason_parts.append("Recently released")
            else:
                reason_parts.append("Popular choice")
            
            if request.mood:
                reason_parts.append(f"• {request.mood.title()} mood")
            if c.rating:
                reason_parts.append(f"• Rated {c.rating:.1f}")
            
            results.append(SearchResultItem(
                content_id=c.content_id,
                title=c.title,
                content_type=str(c.content_type.value) if hasattr(c.content_type, 'value') else str(c.content_type),
                thumbnail_url=c.thumbnail_url,
                rating=c.rating,
                score=c.popularity or 0.0,
                reason=" ".join(reason_parts)
            ))
        
        return SearchResponse(results=results[:20])
    except Exception as e:
        logger.error(f"Discover failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/ready")
def ready():
    """
    Readiness probe: Checks DB and VectorStore.
    """
    status = {
        "database": "unknown",
        "vector_store": "unknown"
    }
    
    # Check DB
    try:
        if os.path.exists(DB_PATH):
            status["database"] = "connected"
        else:
             status["database"] = "missing"
    except Exception:
        status["database"] = "error"
        
    # Check Vector Store
    if search_service_instance and search_service_instance.vector_store.index:
         status["vector_store"] = f"loaded ({search_service_instance.vector_store.index.ntotal} vectors)"
    else:
         status["vector_store"] = "not loaded"
         
    if status["database"] == "connected" and "loaded" in status["vector_store"]:
        return status
    else:
        raise HTTPException(status_code=503, detail=status)

@app.get("/metrics")
def metrics():
    return METRICS

@app.get("/debug/embedding-status")
def debug_embedding_status():
    """
    Debug endpoint to verify embedding status.
    """
    if not search_service_instance:
        raise HTTPException(status_code=503, detail="Search Service not ready")
    return search_service_instance.vector_store.get_debug_stats()

@app.post("/debug/search")
def debug_search(request: SearchRequest):
    """
    Debug endpoint that returns detailed search processing info.
    Now includes hybrid search mode detection.
    """
    import numpy as np
    from .database import get_content_by_ids
    
    if not search_service_instance:
        raise HTTPException(status_code=503, detail="Search Service not ready")
    
    base_query = request.base_prompt.strip()
    
    # Detect search mode (using same logic as SearchService)
    search_mode = search_service_instance._detect_search_mode(base_query)
    
    # Build the query
    query_text = search_service_instance.prompt_builder.build_query(request)
    
    # Get embedding
    query_vector = search_service_instance.embedder.embed_texts([query_text])[0]
    query_norm = float(np.linalg.norm(query_vector))
    
    # Get FAISS results (for semantic mode preview)
    distances, content_ids = search_service_instance.vector_store.search(query_vector, k=20)
    
    # Filter valid results
    valid_results = [(cid, float(dist)) for cid, dist in zip(content_ids, distances) if cid is not None]
    
    # Get content details for top results
    if valid_results:
        top_ids = [r[0] for r in valid_results[:10]]
        contents = get_content_by_ids(top_ids)
        content_map = {c.content_id: c for c in contents}
    else:
        content_map = {}
    
    # Build detailed results
    top_faiss_results = []
    genre_boosts_count = 0
    query_lower = query_text.lower()
    
    for cid, score in valid_results[:10]:
        if cid in content_map:
            c = content_map[cid]
            genres = c.genres
            
            # Check for genre boost
            has_genre_match = any(g.lower() in query_lower for g in genres)
            if has_genre_match:
                genre_boosts_count += 1
            
            top_faiss_results.append({
                "content_id": cid,
                "title": c.title,
                "similarity_score": round(score, 4),
                "genres": genres,
                "genre_match": has_genre_match
            })
    
    # Mood genre filter info
    mood_genre_filter = []
    if request.mood and request.mood.lower() in search_service_instance.MOOD_GENRE_MAP:
        mood_genre_filter = search_service_instance.MOOD_GENRE_MAP[request.mood.lower()]
    
    # Detect compound concepts
    detected_concepts = search_service_instance.ranker.detect_concepts(base_query)
    is_compound = len(detected_concepts) >= 2
    
    # Get parsed intent from prompt parser
    parsed_intent_info = None
    if hasattr(search_service_instance, 'prompt_parser'):
        parsed = search_service_instance.prompt_parser.parse(base_query)
        parsed_intent_info = {
            "mode": parsed.mode,
            "themes": parsed.themes,
            "entities": parsed.entities,
            "emotional_tone": parsed.emotional_tone,
            "is_story": parsed.is_story,
            "story_confidence": parsed.story_confidence,
            "normalized_query": parsed.normalized_query
        }
    
    return {
        "input": {
            "base_prompt": request.base_prompt,
            "mood": request.mood,
            "refinements": request.refinements
        },
        "parsed_intent": parsed_intent_info,  # NEW: 6-stage parsing output
        "hybrid_search": {
            "detected_mode": search_mode,
            "mode_explanation": {
                "exact": "SQL title search (short query, not a genre)",
                "genre": "SQL genre browse (pure genre keyword)",
                "semantic": "FAISS vector search (descriptive query)"
            }.get(search_mode, "unknown")
        },
        "compound_intent": {
            "detected_concepts": detected_concepts,
            "compound_mode": is_compound,
            "explanation": "Multi-concept queries get soft-AND scoring" if is_compound else None
        },
        "processing": {
            "final_prompt": query_text,
            "query_embedding_norm": round(query_norm, 4),
            "mood_genre_filter": mood_genre_filter
        },
        "semantic_preview": {
            "top_faiss_results": top_faiss_results,
            "genre_boosts_applied": genre_boosts_count,
            "total_faiss_matches": len(valid_results)
        },
        "pipeline_stages": search_service_instance.last_stage_counts if hasattr(search_service_instance, 'last_stage_counts') else None
    }

@app.get("/content/{content_id}")
def get_content_detail(content_id: str):
    """
    Get full details for a single content item, including cast/director from TMDB.
    """
    from .database import get_content_by_ids
    from .tmdb_client import TMDBClient
    
    results = get_content_by_ids([content_id])
    if not results:
        raise HTTPException(status_code=404, detail="Content not found")
    
    content = results[0]
    
    # Fetch extended details from TMDB
    credits = {"cast": [], "director": None, "creators": [], "trailer_url": None, "watch_providers": []}
    try:
        tmdb = TMDBClient()
        credits = tmdb.get_extended_details(content.content_type.value, content.source_id)
    except Exception as e:
        logger.warning(f"Failed to fetch extended details for {content_id}: {e}")
    
    return {
        "content_id": content.content_id,
        "title": content.title,
        "description": content.description,
        "genres": content.genres,
        "rating": content.rating,
        "release_year": content.release_year,
        "thumbnail_url": content.thumbnail_url,
        "content_type": content.content_type.value,
        "language": content.language,
        "source_url": content.source_url,
        "cast": credits.get("cast", []),
        "director": credits.get("director"),
        "creators": credits.get("creators", []),
        "trailer_url": credits.get("trailer_url"),
        "watch_providers": credits.get("watch_providers", [])
    }

@app.get("/content/{content_id}/similar", response_model=SearchResponse)
def get_similar_content_endpoint(content_id: str):
    """
    Get 'More Like This' recommendations for a specific content item.
    """
    if not search_service_instance:
         raise HTTPException(status_code=503, detail="Search Service not ready")
         
    try:
        results = search_service_instance.get_similar_content(content_id, limit=10)
        return SearchResponse(results=results)
    except Exception as e:
        logger.error(f"Similar content search failed: {e}")
        return SearchResponse(results=[])

@app.post("/recommendations/personal", response_model=SearchResponse)
def get_personal_recommendations(
    request: PersonalRecommendationRequest,
    x_user_email: Optional[str] = Header(None)
):
    """
    Get personalized recommendations based on watch history (seed IDs).
    """
    search_service = get_search_service()
    if not search_service:
         raise HTTPException(status_code=503, detail="Search Service not ready")
         
    try:
        results = search_service.get_personal_recommendations(request.seed_ids, limit=request.limit)
        return SearchResponse(results=results)
    except Exception as e:
        logger.error(f"Personal recommendations failed: {e}")
        return SearchResponse(results=[])

from typing import List
@app.post("/content/batch", response_model=List[SearchResultItem])
def get_content_batch(
    content_ids: List[str]
):
    """
    Fetch details for a list of content IDs.
    """
    try:
        # Import here to avoid circular dependency
        from .database import get_content_by_ids
        contents = get_content_by_ids(content_ids)
        
        results = []
        for c in contents:
             results.append(SearchResultItem(
                content_id=c.content_id,
                title=c.title,
                content_type=c.content_type.value,
                thumbnail_url=c.thumbnail_url,
                rating=c.rating,
                popularity=c.popularity,
                score=1.0, 
                reason="Continue Watching"
            ))
        return results
    except Exception as e:
        logger.error(f"Batch fetch failed: {e}")
        return []

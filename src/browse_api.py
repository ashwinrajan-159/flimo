from fastapi import APIRouter, Query
from typing import List, Optional
from pydantic import BaseModel
from .browse_service import BrowseService
from .schemas import SearchResultItem # We can reuse this or simple unified model
from .config import YOUTUBE_API_KEY
import requests
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/browse", tags=["browse"])
service = BrowseService()

# Response Model for Browse (with pagination)
class BrowseResponse(BaseModel):
    page: int
    page_size: int
    total: int
    results: List[dict] # Simplified for now, or reuse schemas

# Helper to format response
def _format_content(c):
    return {
        "content_id": c.content_id,
        "title": c.title,
        "thumbnail_url": c.thumbnail_url,
        "rating": c.rating,
        "content_type": c.content_type.value,
        "release_year": c.release_year
    }

@router.get("/trending")
def get_trending(page: int = 1, limit: int = 20, content_type: Optional[str] = Query(None)):
    items = service.get_trending(page, limit, content_type)
    return {"results": [_format_content(i) for i in items]}

@router.get("/latest")
def get_latest(page: int = 1, limit: int = 20, content_type: Optional[str] = Query(None)):
    items = service.get_latest(page, limit, content_type)
    return {"results": [_format_content(i) for i in items]}

@router.get("/top-rated")
def get_top_rated(page: int = 1, limit: int = 20, content_type: Optional[str] = Query(None)):
    items = service.get_top_rated(page, limit, content_type)
    return {"results": [_format_content(i) for i in items]}

@router.get("")
def browse(
    page: int = 1,
    page_size: int = 20,
    content_type: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_rating: Optional[float] = None
):
    items, total = service.browse(
        page, page_size, content_type, genre, language, min_year, max_year, min_rating
    )
    
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "results": [_format_content(i) for i in items]
    }

# --- YouTube Trending Trailers ---
_yt_cache = {"data": None, "ts": 0}

@router.get("/youtube-trending")
def get_youtube_trending(limit: int = 6):
    """
    Fetch trending movie trailers from YouTube.
    Caches results for 30 minutes to conserve API quota.
    """
    import time

    # Return cached data if fresh (30 min)
    if _yt_cache["data"] and (time.time() - _yt_cache["ts"]) < 1800:
        return {"results": _yt_cache["data"][:limit]}

    if not YOUTUBE_API_KEY:
        return {"results": []}

    try:
        # Step 1: Search for trending movie trailers
        search_url = "https://www.googleapis.com/youtube/v3/search"
        search_params = {
            "part": "snippet",
            "q": "new official movie trailer 2025 2026",
            "type": "video",
            "order": "relevance",
            "maxResults": limit,
            "videoCategoryId": "1",  # Film & Animation
            "publishedAfter": "2025-06-01T00:00:00Z",
            "key": YOUTUBE_API_KEY
        }
        search_res = requests.get(search_url, params=search_params, timeout=10)
        search_res.raise_for_status()
        search_data = search_res.json()
        items = search_data.get("items", [])

        if not items:
            return {"results": []}

        # Step 2: Get video statistics (view counts)
        video_ids = [item["id"]["videoId"] for item in items]
        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_params = {
            "part": "statistics",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY
        }
        stats_res = requests.get(stats_url, params=stats_params, timeout=10)
        stats_data = stats_res.json() if stats_res.ok else {}
        stats_map = {}
        for v in stats_data.get("items", []):
            stats_map[v["id"]] = v.get("statistics", {})

        # Step 3: Format results
        results = []
        for item in items:
            snippet = item.get("snippet", {})
            video_id = item["id"]["videoId"]
            views = int(stats_map.get(video_id, {}).get("viewCount", 0))

            # Format view count
            if views >= 1_000_000:
                view_str = f"{views / 1_000_000:.1f}M views"
            elif views >= 1_000:
                view_str = f"{views / 1_000:.0f}K views"
            else:
                view_str = f"{views} views"

            results.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "channel": snippet.get("channelTitle", ""),
                "views": view_str,
                "url": f"https://www.youtube.com/embed/{video_id}?autoplay=1"
            })

        _yt_cache["data"] = results
        _yt_cache["ts"] = time.time()
        return {"results": results[:limit]}

    except Exception as e:
        logger.error(f"YouTube trending fetch failed: {e}")
        return {"results": []}

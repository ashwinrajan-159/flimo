import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from typing import List, Dict, Any
from datetime import datetime
from .models import UnifiedContent, ContentType
from .config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

class YouTubeClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        if not YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY not found in configuration.")
        
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _get(self, endpoint: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        params["key"] = YOUTUBE_API_KEY
        try:
            response = self.session.get(f"{self.BASE_URL}{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"YouTube Request failed for {endpoint}: {e}")
            return {}

    def search_videos(self, query: str, max_results: int = 50) -> List[UnifiedContent]:
        """Search for videos using a query."""
        params = {
            "part": "snippet,statistics",
            "q": query,
            "type": "video",
            "maxResults": max_results
        }
        # Note: 'statistics' part is not available in search endpoint directly.
        # We search first, get IDs, then call videos endpoint to get stats (likes, views) and tags.
        
        # 1. Search
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results
        }
        search_data = self._get("/search", search_params)
        items = search_data.get("items", [])
        
        if not items:
            return []
            
        video_ids = [item["id"]["videoId"] for item in items]
        
        # 2. Get Details (Stats, Tags)
        return self._fetch_video_details(video_ids)

    def _fetch_video_details(self, video_ids: List[str]) -> List[UnifiedContent]:
        if not video_ids:
            return []
            
        params = {
            "part": "snippet,statistics,status",
            "id": ",".join(video_ids)
        }
        
        data = self._get("/videos", params)
        return self._transform_results(data.get("items", []))

    def _transform_results(self, items: List[Dict]) -> List[UnifiedContent]:
        unified_list = []
        for item in items:
            try:
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                
                source_id = item.get("id")
                title = snippet.get("title")
                description = snippet.get("description", "")
                
                # Tags
                tags = snippet.get("tags", [])
                
                # Release Year
                published_at = snippet.get("publishedAt")
                release_year = int(published_at[:4]) if published_at else None
                
                # Rating/Popularity (Simulation)
                # YouTube doesn't have 0-10 rating. We can use like count or view count as proxy or just normalize.
                # Prompt asks for "Rating" and "Popularity".
                # I will map view_count to popularity directly (though scale is different from TMDB).
                # I will map like_count/view_count ratio to rating? Or just leave None?
                # The user prompt: "Required fields to fetch: ... View count, Like count ... Rating: number, Popularity: number"
                # Since schema enforces 'rating', I should try to fill it. 
                # TMDB rating is 0-10. 
                # YouTube: maybe (likes / views) * 100? Or just 0 if unknown.
                
                view_count = int(statistics.get("viewCount", 0))
                like_count = int(statistics.get("likeCount", 0))
                
                rating = 0.0
                if view_count > 0:
                    rating = (like_count / view_count) * 100 # Rough percentage score? 
                    if rating > 10: rating = 10 # Cap at 10 to match TMDB scale roughly? Or just raw.
                    # Actually standard TMDB is 0-10. 
                    # Let's just leave it as is or 0.
                
                thumbnail_url = snippet.get("thumbnails", {}).get("high", {}).get("url")
                
                # Embedding Text: Title + Description + Keywords
                tags_str = ", ".join(tags)
                embedding_text = f"{title}. {description}. Keywords: {tags_str}"
                
                content = UnifiedContent(
                    content_id=f"{ContentType.YOUTUBE.value}:{source_id}",
                    source_id=source_id,
                    content_type=ContentType.YOUTUBE,
                    title=title,
                    description=description,
                    genres=tags[:3], # Use first few tags as genres? Or empty.
                    language=snippet.get("defaultAudioLanguage", "en"),
                    release_year=release_year,
                    rating=rating,
                    popularity=float(view_count), # Using view count as popularity
                    thumbnail_url=thumbnail_url,
                    source_url=f"https://www.youtube.com/watch?v={source_id}",
                    embedding_text=embedding_text
                )
                unified_list.append(content)
            except Exception as e:
                logger.warning(f"Failed to transform YouTube item {item.get('id')}: {e}")
                
        return unified_list

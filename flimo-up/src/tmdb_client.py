import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from typing import List, Dict, Any
from .models import UnifiedContent, ContentType
from .config import TMDB_API_KEY

logger = logging.getLogger(__name__)

class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

    def __init__(self):
        if not TMDB_API_KEY:
            raise ValueError("TMDB_API_KEY not found in configuration.")
        
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.movie_genres = {}
        self.series_genres = {}
        self._fetch_genres()

    def _fetch_genres(self):
        """Fetch and cache genre maps."""
        try:
            m_data = self._get("/genre/movie/list")
            for g in m_data.get("genres", []):
                self.movie_genres[g["id"]] = g["name"]
                
            s_data = self._get("/genre/tv/list")
            for g in s_data.get("genres", []):
                self.series_genres[g["id"]] = g["name"]
        except Exception as e:
            logger.warning(f"Failed to fetch genres: {e}")

    def _get(self, endpoint: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        import time
        # Rate limiting: 4 requests/sec = 40/10s (TMDB limit)
        time.sleep(0.25)
        
        headers = {}
        # Simple check: JWTs are usually long (> 60 chars) and contain dots.
        # v3 keys are 32 chars hex.
        if len(TMDB_API_KEY) > 60:
            headers["Authorization"] = f"Bearer {TMDB_API_KEY}"
        else:
            params["api_key"] = TMDB_API_KEY
            
        try:
            response = self.session.get(
                f"{self.BASE_URL}{endpoint}", 
                params=params, 
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"TMDB Request failed for {endpoint}: {e}")
            return {}

    def fetch_popular_movies(self, page: int = 1) -> List[UnifiedContent]:
        data = self._get("/movie/popular", {"page": page})
        return self._transform_results(data.get("results", []), ContentType.MOVIE)

    def fetch_top_rated_movies(self, page: int = 1) -> List[UnifiedContent]:
        """Fetch top rated movies - includes classics like Star Wars."""
        data = self._get("/movie/top_rated", {"page": page})
        return self._transform_results(data.get("results", []), ContentType.MOVIE)

    def discover_movies(self, page: int = 1, sort_by: str = "popularity.desc",
                        vote_count_gte: int = 50, year: int = None, 
                        with_original_language: str = None) -> List[UnifiedContent]:
        """
        Use discover endpoint for large-scale ingestion.
        Supports 500 pages = 10,000 movies per run.
        """
        params = {
            "page": page,
            "sort_by": sort_by,
            "vote_count.gte": vote_count_gte
        }
        if year:
            params["primary_release_year"] = year
        if with_original_language:
            params["with_original_language"] = with_original_language
            
        data = self._get("/discover/movie", params)
        return self._transform_results(data.get("results", []), ContentType.MOVIE)

    def fetch_popular_series(self, page: int = 1) -> List[UnifiedContent]:
        data = self._get("/tv/popular", {"page": page})
        return self._transform_results(data.get("results", []), ContentType.SERIES)

    def fetch_top_rated_series(self, page: int = 1) -> List[UnifiedContent]:
        """Fetch top rated series - includes classics like Breaking Bad."""
        data = self._get("/tv/top_rated", {"page": page})
        return self._transform_results(data.get("results", []), ContentType.SERIES)

    def _transform_results(self, results: List[Dict], content_type: ContentType) -> List[UnifiedContent]:
        unified_list = []
        genre_map = self.movie_genres if content_type == ContentType.MOVIE else self.series_genres
        
        for item in results:
            try:
                title = item.get("title") if content_type == ContentType.MOVIE else item.get("name")
                if not title:
                    continue

                release_date = item.get("release_date") if content_type == ContentType.MOVIE else item.get("first_air_date")
                release_year = int(release_date.split("-")[0]) if release_date else None

                source_id = str(item.get("id"))
                genre_ids = item.get("genre_ids", [])
                genres = [genre_map.get(gid, str(gid)) for gid in genre_ids]
                
                description = item.get("overview", "")
                
                # Embedding Text: Title + Description + Genres (repeated for strong semantic anchor)
                genre_str = ", ".join(genres)
                # FIX 1: Repeat genres 3x for stronger semantic anchor to reduce genre leakage
                genre_anchor = f"Genres: {genre_str}. This is a {genre_str} content. Category: {genre_str}."
                embedding_text = f"{title}. {description} {genre_anchor}"
                
                content = UnifiedContent(
                    content_id=f"{content_type.value}:{source_id}",
                    source_id=source_id,
                    content_type=content_type,
                    title=title,
                    description=description,
                    genres=genres,
                    language=item.get("original_language", "en"),
                    release_year=release_year,
                    rating=item.get("vote_average"),
                    popularity=item.get("popularity"),
                    thumbnail_url=f"{self.IMAGE_BASE_URL}{item.get('poster_path')}" if item.get("poster_path") else None,
                    source_url=f"https://www.themoviedb.org/{content_type.value}/{source_id}",
                    embedding_text=embedding_text
                )
                unified_list.append(content)
            except Exception as e:
                logger.warning(f"Failed to transform TMDB item {item.get('id')}: {e}")
                
        return unified_list

    def get_extended_details(self, content_type: str, source_id: str) -> Dict[str, Any]:
        """
        Fetch extended details including credits, videos (trailers), and watch providers.
        """
        endpoint = "/movie" if content_type == "movie" else "/tv"
        params = {"append_to_response": "videos,watch/providers,credits"}
        data = self._get(f"{endpoint}/{source_id}", params=params)
        
        # Extract cast (top 10)
        cast_list = []
        credits_data = data.get("credits", {})
        for person in credits_data.get("cast", [])[:10]:
            cast_list.append({
                "name": person.get("name"),
                "character": person.get("character"),
                "profile_path": f"{self.IMAGE_BASE_URL}{person.get('profile_path')}" if person.get("profile_path") else None
            })
        
        # Extract director(s) for movies
        director = None
        creators = []
        
        for crew in credits_data.get("crew", []):
            if crew.get("job") == "Director":
                director = crew.get("name")
                break
        
        # For series, get created_by
        if content_type == "series":
            creators = [c.get("name") for c in data.get("created_by", [])]
            
        # Extract Trailer (YouTube)
        trailer_url = None
        for video in data.get("videos", {}).get("results", []):
            if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                trailer_url = f"https://www.youtube.com/embed/{video.get('key')}"
                break
                
        # Extract Watch Providers (US by default, or fallback to first available)
        providers_data = data.get("watch/providers", {}).get("results", {})
        us_providers = providers_data.get("US", {})
        
        # If no US providers, try to grab the first country's providers
        if not us_providers and providers_data:
            first_country = list(providers_data.keys())[0]
            us_providers = providers_data[first_country]
            
        flatrate_providers = us_providers.get("flatrate", [])
        watch_providers = []
        for p in flatrate_providers:
            watch_providers.append({
                "provider_id": p.get("provider_id"),
                "provider_name": p.get("provider_name"),
                "logo_path": f"{self.IMAGE_BASE_URL}{p.get('logo_path')}" if p.get("logo_path") else None
            })
        
        return {
            "cast": cast_list,
            "director": director,
            "creators": creators,
            "trailer_url": trailer_url,
            "watch_providers": watch_providers
        }

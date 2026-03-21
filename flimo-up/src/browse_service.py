from typing import List, Optional, Tuple
from .database import get_trending, get_latest, get_top_rated, browse_all
from .models import UnifiedContent

class BrowseService:
    """
    Service to handle browsing logic.
    Currently a thin wrapper around DB queries, but placeholder for caching/extra logic.
    """
    
    def get_trending(self, page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
        return get_trending(page, limit, content_type)
        
    def get_latest(self, page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
        return get_latest(page, limit, content_type)
        
    def get_top_rated(self, page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
        return get_top_rated(page, limit, content_type)
        
    def browse(
        self,
        page: int = 1,
        page_size: int = 20,
        content_type: Optional[str] = None,
        genre: Optional[str] = None,
        language: Optional[str] = None,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        min_rating: Optional[float] = None
    ) -> Tuple[List[UnifiedContent], int]:
        return browse_all(
            page=page,
            page_size=page_size,
            content_type=content_type,
            genre=genre,
            language=language,
            min_year=min_year,
            max_year=max_year,
            min_rating=min_rating
        )

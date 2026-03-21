from typing import List, Optional
from pydantic import BaseModel, Field

class SearchFilters(BaseModel):
    content_type: Optional[List[str]] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None  # Added support for range
    language: Optional[str] = None
    min_rating: Optional[float] = None

class SearchRequest(BaseModel):
    base_prompt: str
    refinements: List[str] = Field(default_factory=list)
    mood: Optional[str] = None
    genres: Optional[List[str]] = None  # NEW: Genre filters
    filters: Optional[SearchFilters] = None

class DiscoverRequest(BaseModel):
    """Request for discover endpoints (trending/popular/latest)"""
    mode: str = "popular"  # trending, popular, latest
    mood: Optional[str] = None
    genres: Optional[List[str]] = None
    query: Optional[str] = None

class PersonalRecommendationRequest(BaseModel):
    """Request for personalized recommendations based on watch history"""
    seed_ids: List[str]
    limit: int = 10

class SearchResultItem(BaseModel):
    content_id: str
    title: str
    content_type: str
    thumbnail_url: Optional[str] = None
    rating: Optional[float] = None
    popularity: Optional[float] = None  # Added for debugging/boosters
    score: float
    reason: str

class SearchResponse(BaseModel):
    results: List[SearchResultItem]


from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator

class ContentType(str, Enum):
    MOVIE = "movie"
    SERIES = "series"
    YOUTUBE = "youtube"

class UnifiedContent(BaseModel):
    content_id: str = Field(..., description="Unique ID in format '{content_type}:{source_id}'")
    source_id: str = Field(..., description="Original ID from the source (TMDB ID or YouTube Video ID)")
    content_type: ContentType
    
    title: str
    description: str
    genres: List[str] = Field(default_factory=list)
    language: str
    
    release_year: Optional[int] = None
    rating: Optional[float] = None
    popularity: Optional[float] = None
    
    thumbnail_url: Optional[str] = None
    source_url: str
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    embedding_text: str = Field(..., description="Text optimized for semantic embedding: Title + Description + Genres + Keywords")

    @validator('content_id')
    def validate_content_id(cls, v, values):
        if 'content_type' in values and 'source_id' in values:
            expected = f"{values['content_type'].value}:{values['source_id']}"
            if v != expected:
                raise ValueError(f"content_id must be '{expected}', got '{v}'")
        return v

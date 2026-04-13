from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    user_id: str
    email: str
    created_at: Optional[datetime] = None
    google_id: Optional[str] = None
    name: Optional[str] = None
    profile_pic: Optional[str] = None

class LikeRequest(BaseModel):
    content_id: str

class ReviewRequest(BaseModel):
    content_id: str
    rating: int = Field(..., ge=1, le=10)
    review_text: str

class ReviewResponse(BaseModel):
    review_id: str
    user_id: str
    content_id: str
    rating: int
    review_text: str
    created_at: datetime
    # Could expand to include content details or user details

class WatchlistCreate(BaseModel):
    name: str

class WatchlistAddItem(BaseModel):
    content_id: str

class WatchlistResponse(BaseModel):
    watchlist_id: str
    user_id: str
    name: str
    created_at: datetime

# --- Profile Models ---
class UserProfile(BaseModel):
    user_id: str
    email: str
    display_name: Optional[str] = None
    avatar_color: str = "#3B82F6"
    created_at: Optional[datetime] = None

class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    avatar_color: Optional[str] = None

# --- Chat Models ---
class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)

class ChatMessageResponse(BaseModel):
    message_id: str
    user_id: str
    display_name: Optional[str] = None
    avatar_color: str = "#3B82F6"
    message: str
    created_at: datetime

# --- Comment Models ---
class CommentRequest(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=1000)

class CommentResponse(BaseModel):
    comment_id: str
    user_id: str
    display_name: Optional[str] = None
    avatar_color: str = "#3B82F6"
    content_id: str
    comment_text: str
    created_at: datetime

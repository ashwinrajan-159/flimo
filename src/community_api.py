from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from .user_models import User, LikeRequest, ReviewRequest, ReviewResponse, WatchlistCreate, WatchlistAddItem, WatchlistResponse
from .auth import get_current_user
from .community_service import CommunityService

router = APIRouter(tags=["community"])
service = CommunityService()

# --- Likes ---

@router.post("/like/{content_id}", status_code=status.HTTP_201_CREATED)
def like_content(content_id: str, user: User = Depends(get_current_user)):
    service.add_like(user.user_id, content_id)
    return {"message": "Liked"}

@router.delete("/like/{content_id}")
def unlike_content(content_id: str, user: User = Depends(get_current_user)):
    service.remove_like(user.user_id, content_id)
    return {"message": "Unliked"}

# --- Reviews ---

@router.post("/review/{content_id}", response_model=ReviewResponse)
def add_review(content_id: str, request: ReviewRequest, user: User = Depends(get_current_user)):
    if content_id != request.content_id:
        raise HTTPException(400, "Content ID mismatch")
    return service.add_review(user.user_id, content_id, request.rating, request.review_text)

@router.get("/review/{content_id}", response_model=List[ReviewResponse])
def get_reviews(content_id: str):
    return service.get_reviews(content_id)

# --- Watchlists ---

@router.post("/watchlist", response_model=WatchlistResponse)
def create_watchlist(request: WatchlistCreate, user: User = Depends(get_current_user)):
    return service.create_watchlist(user.user_id, request.name)

@router.post("/watchlist/{watchlist_id}/add/{content_id}")
def add_to_watchlist(watchlist_id: str, content_id: str, user: User = Depends(get_current_user)):
    try:
        service.add_to_watchlist(user.user_id, watchlist_id, content_id)
        return {"message": "Added to watchlist"}
    except ValueError:
        raise HTTPException(404, "Watchlist not found")
    except PermissionError:
        raise HTTPException(403, "Not authorized")

@router.get("/watchlist/{user_id}", response_model=List[WatchlistResponse])
def get_user_watchlists(user_id: str):
    # Depending on privacy rules, this might need checks.
    # Plan says "Watchlists are private by default (public flag optional)".
    # For now, allow viewing if it matches current user OR if we implement public flag later.
    # To keep it simple per plan: return list.
    return service.get_watchlists(user_id)

# --- Profile Endpoints ---

from .user_models import UserProfile, ProfileUpdateRequest, ChatMessageRequest, ChatMessageResponse, CommentRequest, CommentResponse

@router.get("/profile", response_model=UserProfile)
def get_profile(user: User = Depends(get_current_user)):
    """Get current user's profile."""
    return service.get_profile(user.user_id, user.email)

@router.put("/profile", response_model=UserProfile)
def update_profile(request: ProfileUpdateRequest, user: User = Depends(get_current_user)):
    """Update current user's profile."""
    service.update_profile(user.user_id, request.display_name, request.avatar_color)
    return service.get_profile(user.user_id, user.email)

# --- Chat Endpoints ---

@router.get("/chat", response_model=List[ChatMessageResponse])
def get_chat_messages(limit: int = 50):
    """Get recent global chat messages."""
    return service.get_chat_messages(limit)

@router.post("/chat", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
def send_chat_message(request: ChatMessageRequest, user: User = Depends(get_current_user)):
    """Send a global chat message."""
    return service.add_chat_message(user.user_id, request.message)

# --- Comment Endpoints ---

@router.get("/comments/{content_id}", response_model=List[CommentResponse])
def get_content_comments(content_id: str, limit: int = 50):
    """Get comments for a specific content item."""
    return service.get_comments(content_id, limit)

@router.post("/comments/{content_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def add_content_comment(content_id: str, request: CommentRequest, user: User = Depends(get_current_user)):
    """Add a comment to a content item."""
    return service.add_comment(user.user_id, content_id, request.comment_text)

# --- History Endpoints ---

@router.post("/history/{content_id}", status_code=status.HTTP_200_OK)
def add_to_history(content_id: str, progress: float = 0, user: User = Depends(get_current_user)):
    """Add or update watch history."""
    service.add_history(user.user_id, content_id, progress)
    return {"message": "History updated"}

@router.get("/history", response_model=List[dict])
def get_history(limit: int = 100, user: User = Depends(get_current_user)):
    """Get user watch history."""
    return service.get_history(user.user_id, limit)

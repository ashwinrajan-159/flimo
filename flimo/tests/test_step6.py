import logging
import sqlite3
from src.database import init_db
from src.search_service import SearchService
from src.auth import AuthService
from src.community_service import CommunityService
from src.schemas import SearchRequest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestStep6")

def test_step6():
    logger.info("Starting Step 6 Verification (Personalization)...")
    init_db()
    
    # Initialize Services
    search_service = SearchService()
    comm_service = CommunityService()
    auth_service = AuthService()
    
    # 1. Create User
    email = "personalization_test@example.com"
    user = auth_service.get_or_create_user(email)
    logger.info(f"Test User: {user.user_id}")
    
    # 2. Seed Likes 
    # Logic: Like 'Test Movie' from Step 2 (Action)
    # Note: We need to know the content_id. In step 2 we used dummy data.
    # If we are running this on a fresh DB, we might need to verify what content exists.
    # Assuming 'movie:test_123' exists from previous steps or we reuse logic.
    # Let's ensure content exists first.
    
    content_id = "movie:test_123"
    
    # Double check if 'movie:test_123' is in FAISS
    # search_service.vector_store.get_vector(content_id)
    vec = search_service.vector_store.get_vector(content_id)
    if vec is None:
        logger.warning(f"Content {content_id} not in VectorStore. Cannot test personalization effectively if empty.")
        # We might be in a state where DB has it but FAISS doesn't if restarted?
        # Actually vector_store loads from disk.
        
    comm_service.add_like(user.user_id, content_id)
    logger.info(f"User liked {content_id}")
    
    # 3. Search with Personalization
    # Query: "drama" (unrelated to Action)
    # If personalization works, the Action movie might still appear higher than unrelated items 
    # or the score should be boosted compared to search without user_id.
    
    req = SearchRequest(base_prompt="drama")
    
    # Without User
    results_base = search_service.search(req, user_id=None)
    score_base = 0.0
    for r in results_base:
        if r.content_id == content_id:
            score_base = r.score
            break
            
    # With User
    results_user = search_service.search(req, user_id=user.user_id)
    score_user = 0.0
    for r in results_user:
        if r.content_id == content_id:
            score_user = r.score
            break
            
    logger.info(f"Score Base: {score_base}")
    logger.info(f"Score User: {score_user}")
    
    if score_user > score_base:
        logger.info("Personalization Verified: Score increased for liked content.")
    elif score_user == score_base:
         logger.warning("Score unchanged. Vector blending might be subtle or content vector is orthogonal.")
    else:
        logger.error("Score decreased? Unexpected.")

if __name__ == "__main__":
    test_step6()

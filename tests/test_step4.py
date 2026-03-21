import logging
import json
from src.browse_service import BrowseService
from src.database import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestStep4")

def test_step4():
    logger.info("Starting Step 4 Verification (Browse)...")
    init_db()
    
    service = BrowseService()
    
    # Test 1: Trending
    trending = service.get_trending(limit=5)
    logger.info(f"Trending ({len(trending)}): {[t.title for t in trending]}")
    
    # Test 2: Latest
    latest = service.get_latest(limit=5)
    logger.info(f"Latest ({len(latest)}): {[t.title for t in latest]}")
    
    # Test 3: Top Rated
    top = service.get_top_rated(limit=5)
    logger.info(f"Top Rated ({len(top)}): {[t.title for t in top]}")
    
    # Test 4: Browse with filters
    # We filter for "Test Movie" using min_year=2024 and genre="Action"
    results, total = service.browse(
        min_year=2024,
        genre="Action"
    )
    logger.info(f"Browse Result: Found {total} items.")
    for r in results:
        logger.info(f" - {r.title} ({r.release_year})")
        
    if total > 0 and results[0].title == "Test Movie":
        logger.info("Step 4 Verification Successful!")
    else:
        logger.warning("Did not find expected 'Test Movie'. Ensure dummy data is present.")

if __name__ == "__main__":
    test_step4()
